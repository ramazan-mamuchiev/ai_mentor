"""Ingestion pipeline: detect format -> convert -> parse -> chunk -> embed -> store."""

import hashlib
import logging
import os
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.chunker import ChunkData, chunk_sections
from app.ingestion.converters.pdf import convert_pdf
from app.ingestion.converters.proto import convert_proto_file
from app.ingestion.converters.swagger import convert_swagger_file, is_swagger_file
from app.ingestion.converters.web import convert_url
from app.ingestion.embedder import embed_texts
from app.config import settings as _settings
from app.ingestion.parsers.markdown import parse_markdown
from app.ingestion.parsers.swagger import parse_swagger
from app.ingestion.text_cleaner import clean_for_embedding as _clean_md
from app.models import Chunk, Product, Document, FirmwareVersion

logger = logging.getLogger(__name__)


def _embedding_model_name() -> str:
    return _settings.embedding_model_gemini


MAX_EMBEDDING_TOKENS = 500

def enrich_for_embedding(chunks: list[ChunkData]) -> list[str]:
    """Clean Markdown artifacts and prepend heading_path for better embeddings.

    Two-step enrichment:
    1. Strip Markdown formatting noise (bold, links, images, HTML) so the
       embedding model sees clean semantic text.
    2. Prepend the heading hierarchy so the model knows *what* the chunk
       describes (e.g. "API Reference > GET /doors > Parameters").

    Warns and truncates if enriched text exceeds model max_seq_length.
    Truncation preserves the heading prefix and only cuts content.
    """
    from app.ingestion.chunker import _estimate_tokens

    enriched: list[str] = []
    for c in chunks:
        cleaned = _clean_md(c.content)
        heading_prefix = ""
        if c.heading_path:
            heading_prefix = f"[{c.heading_path}]\n"

        text = heading_prefix + cleaned

        token_count = _estimate_tokens(text)
        if token_count > MAX_EMBEDDING_TOKENS:
            logger.warning(
                "Enriched text exceeds embedding model limit, truncating",
                extra={
                    "heading_path": c.heading_path,
                    "token_count": token_count,
                    "max_tokens": MAX_EMBEDDING_TOKENS,
                },
            )
            prefix_tokens = _estimate_tokens(heading_prefix) if heading_prefix else 0
            content_budget = max(1, int((MAX_EMBEDDING_TOKENS - prefix_tokens) / 1.3))
            words = cleaned.split()
            text = heading_prefix + " ".join(words[:content_budget])

        enriched.append(text)
    return enriched


def _replace_generic_headings(sections: list, title: str) -> list:
    """Replace 'Document' and 'Preamble' heading_paths with the actual document title."""
    for s in sections:
        hp = getattr(s, "heading_path", None)
        if hp == "Document":
            s.heading_path = title
        elif hp == "Preamble":
            s.heading_path = f"{title} > Preamble"
    return sections


def _log_chunk_stats(chunks: list[ChunkData], file_path: str) -> None:
    """Log distribution metrics for chunk quality monitoring."""
    if not chunks:
        return
    token_counts = [c.token_count for c in chunks]
    with_parent = sum(1 for c in chunks if c.parent_content is not None)
    logger.info(
        "Chunk quality stats",
        extra={
            "file": os.path.basename(file_path),
            "total_chunks": len(chunks),
            "min_tokens": min(token_counts),
            "max_tokens": max(token_counts),
            "avg_tokens": round(sum(token_counts) / len(token_counts), 1),
            "median_tokens": sorted(token_counts)[len(token_counts) // 2],
            "chunks_with_parent": with_parent,
            "chunks_without_parent": len(chunks) - with_parent,
        },
    )


def _file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(8192), b""):
            h.update(block)
    return h.hexdigest()


def detect_format(file_path: str) -> str:
    """Auto-detect document format by extension and content."""
    ext = os.path.splitext(file_path)[1].lower()

    if ext in (".md", ".txt"):
        return "markdown"
    if ext == ".pdf":
        return "pdf"
    if ext == ".proto":
        return "proto"
    if ext in (".wsdl", ".xml"):
        return "markdown"
    if ext in (".yaml", ".yml", ".json"):
        if is_swagger_file(file_path):
            return "swagger"
        if ext == ".json":
            return "markdown"
        return "swagger"

    return "markdown"


def _parse_content(text: str, fmt: str, file_path: str):
    if fmt == "swagger":
        return parse_swagger(text, file_path)
    return parse_markdown(text)


async def ingest_file(
    session: AsyncSession,
    file_path: str,
    product_name: str,
    firmware_version: str = "1.0",
    manufacturer: str = "",
    fmt: str = "auto",
) -> dict:
    """Full ingestion pipeline: file -> convert -> parse -> chunk -> embed -> DB.

    Returns dict with status, document_id, chunks count, duration, stage timings.
    """
    t0 = time.perf_counter()
    file_path = os.path.normpath(file_path)

    file_size = 0
    try:
        file_size = os.path.getsize(file_path)
    except OSError:
        pass

    if not os.path.isfile(file_path):
        logger.error(
            "File not found",
            extra={"file_path": file_path, "error_type": "FileNotFoundError"},
        )
        return {"status": "error", "error": f"File not found: {file_path}"}

    if fmt == "auto":
        fmt = detect_format(file_path)

    logger.info(
        "Ingestion started",
        extra={
            "file_path": file_path, "format": fmt,
            "product": product_name, "firmware_version": firmware_version,
            "file_size_bytes": file_size,
        },
    )

    convert_ms = 0.0
    convert_metadata: dict = {}

    t_read = time.perf_counter()
    if fmt == "pdf":
        try:
            text, convert_metadata = convert_pdf(file_path)
            convert_ms = convert_metadata.get("convert_ms", 0.0)
        except Exception as e:
            logger.error(
                "PDF conversion failed",
                extra={"file_path": file_path, "error_type": type(e).__name__},
                exc_info=True,
            )
            return {"status": "error", "error": f"PDF conversion failed: {e}"}
        fmt_effective = "markdown"
    elif fmt == "swagger":
        try:
            text, convert_metadata = convert_swagger_file(file_path)
            convert_ms = convert_metadata.get("total_ms", 0.0)
        except Exception as e:
            logger.error(
                "Swagger conversion failed",
                extra={"file_path": file_path, "error_type": type(e).__name__},
                exc_info=True,
            )
            return {"status": "error", "error": f"Swagger conversion failed: {e}"}
        fmt_effective = "markdown"
    elif fmt == "proto":
        try:
            text, convert_metadata = convert_proto_file(file_path)
            convert_ms = convert_metadata.get("total_ms", 0.0)
        except Exception as e:
            logger.error(
                "Proto conversion failed",
                extra={"file_path": file_path, "error_type": type(e).__name__},
                exc_info=True,
            )
            return {"status": "error", "error": f"Proto conversion failed: {e}"}
        fmt_effective = "markdown"
    else:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception as e:
            logger.error(
                "Failed to read file",
                extra={"file_path": file_path, "error_type": type(e).__name__},
                exc_info=True,
            )
            return {"status": "error", "error": f"Failed to read file: {e}"}
        fmt_effective = fmt

    read_ms = round((time.perf_counter() - t_read) * 1000, 1)

    source_hash = _file_hash(file_path)

    product = await _get_or_create_product(session, product_name, manufacturer)
    fw = await _get_or_create_firmware(session, product.id, firmware_version)

    existing = await session.execute(
        select(Document).where(
            Document.product_id == product.id,
            Document.firmware_version_id == fw.id,
            Document.source_hash == source_hash,
        )
    )
    existing_doc = existing.scalar_one_or_none()
    if existing_doc and existing_doc.status == "ready":
        logger.warning(
            "Document already ingested (same hash)",
            extra={"file_path": file_path, "document_id": existing_doc.id},
        )
        return {
            "status": "skipped",
            "document_id": existing_doc.id,
            "message": "Document already ingested (same hash)",
        }

    if existing_doc:
        for chunk in (await session.execute(
            select(Chunk).where(Chunk.document_id == existing_doc.id)
        )).scalars().all():
            await session.delete(chunk)
        await session.delete(existing_doc)
        await session.flush()

    title = os.path.splitext(os.path.basename(file_path))[0]
    doc = Document(
        product_id=product.id,
        firmware_version_id=fw.id,
        format=fmt,
        source_path=file_path,
        source_hash=source_hash,
        title=title,
        status="processing",
    )
    session.add(doc)
    await session.flush()

    try:
        t_parse = time.perf_counter()
        sections = _parse_content(text, fmt_effective, file_path)
        _replace_generic_headings(sections, title)
        chunks = chunk_sections(sections)
        parse_ms = round((time.perf_counter() - t_parse) * 1000, 1)

        if not chunks:
            doc.status = "error"
            doc.error_message = "No content extracted"
            await session.commit()
            logger.warning(
                "No content extracted (0 chunks)",
                extra={"file_path": file_path, "document_id": doc.id, "sections": len(sections)},
            )
            return {"status": "error", "error": "No content extracted", "document_id": doc.id}

        _log_chunk_stats(chunks, file_path)

        logger.debug(
            "Parsing completed",
            extra={
                "sections": len(sections), "chunks": len(chunks),
                "parse_ms": parse_ms, "read_ms": read_ms,
            },
        )

        t_embed = time.perf_counter()
        enriched = enrich_for_embedding(chunks)
        embeddings = embed_texts(enriched)
        embed_ms = round((time.perf_counter() - t_embed) * 1000, 1)

        t_db = time.perf_counter()
        for i, (chunk_data, embedding) in enumerate(zip(chunks, embeddings)):
            db_chunk = Chunk(
                document_id=doc.id,
                chunk_index=i,
                heading_path=chunk_data.heading_path,
                heading_level=chunk_data.heading_level,
                content=chunk_data.content,
                content_clean=_clean_md(chunk_data.content),
                parent_content=chunk_data.parent_content,
                token_count=chunk_data.token_count,
                embedding=embedding,
            )
            session.add(db_chunk)

        doc.total_chunks = len(chunks)
        doc.status = "ready"

        token_counts = [c.token_count for c in chunks]
        doc.total_tokens = sum(token_counts)
        doc.min_chunk_tokens = min(token_counts)
        doc.max_chunk_tokens = max(token_counts)
        doc.avg_chunk_tokens = round(sum(token_counts) / len(token_counts), 1)
        doc.embedding_tokens = sum(token_counts)

        await session.flush()
        db_ms = round((time.perf_counter() - t_db) * 1000, 1)

        duration = time.perf_counter() - t0
        doc.ingest_duration_ms = round(duration * 1000, 1)
        doc.read_ms = read_ms
        doc.convert_ms = convert_ms
        doc.parse_ms = parse_ms
        doc.embed_ms = embed_ms
        doc.db_ms = db_ms
        doc.embedding_model = _embedding_model_name()
        doc.embedding_dims = _settings.embedding_dims

        if convert_metadata.get("ocr_applied"):
            doc.ocr_ms = convert_metadata.get("ocr_ms")
            doc.detected_language = convert_metadata.get("detected_languages_str")
            ocr_stats = convert_metadata.get("ocr_stats", {})
            doc.ocr_images_total = ocr_stats.get("ocr_images_total")
            doc.ocr_images_success = ocr_stats.get("ocr_images_success")
            doc.ocr_images_empty = ocr_stats.get("ocr_images_empty")
            doc.ocr_images_failed = ocr_stats.get("ocr_images_failed")

        await session.commit()

        logger.info(
            "Ingestion completed",
            extra={
                "file": os.path.basename(file_path),
                "chunks": len(chunks), "duration_sec": round(duration, 2),
                "read_ms": read_ms, "convert_ms": convert_ms,
                "parse_ms": parse_ms, "embed_ms": embed_ms, "db_ms": db_ms,
                "product": product_name, "format": fmt,
                "file_size_bytes": file_size,
                "ocr_applied": convert_metadata.get("ocr_applied", False),
            },
        )
        result = {
            "status": "ok",
            "document_id": doc.id,
            "product": product_name,
            "firmware_version": firmware_version,
            "format": fmt,
            "chunks": len(chunks),
            "duration_sec": round(duration, 2),
        }
        if convert_metadata:
            result["convert_metadata"] = convert_metadata
        return result

    except Exception as e:
        doc.status = "error"
        doc.error_message = str(e)[:2000]
        await session.commit()
        logger.error(
            "Ingestion failed",
            extra={
                "file_path": file_path, "document_id": doc.id,
                "error_type": type(e).__name__,
            },
            exc_info=True,
        )
        return {"status": "error", "error": str(e), "document_id": doc.id}


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def ingest_url(
    session: AsyncSession,
    url: str,
    product_name: str,
    firmware_version: str = "1.0",
    manufacturer: str = "",
) -> dict:
    """Ingest documentation from a URL: fetch -> convert -> parse -> chunk -> embed -> DB.

    Auto-detects: direct OpenAPI spec, Swagger UI page, or generic web page.

    Returns dict with status, document_id, chunks count, duration.
    """
    t0 = time.perf_counter()

    logger.info(
        "URL ingestion started",
        extra={"url": url, "product": product_name, "firmware_version": firmware_version},
    )

    try:
        text, convert_metadata = await convert_url(url)
    except Exception as e:
        logger.error(
            "URL conversion failed",
            extra={"url": url, "error_type": type(e).__name__},
            exc_info=True,
        )
        return {"status": "error", "error": f"URL conversion failed: {e}"}

    convert_ms = convert_metadata.get("total_ms", 0.0)
    detection = convert_metadata.get("detection_method", "unknown")

    source_hash = _text_hash(text)

    product = await _get_or_create_product(session, product_name, manufacturer)
    fw = await _get_or_create_firmware(session, product.id, firmware_version)

    existing = await session.execute(
        select(Document).where(
            Document.product_id == product.id,
            Document.firmware_version_id == fw.id,
            Document.source_hash == source_hash,
        )
    )
    existing_doc = existing.scalar_one_or_none()
    if existing_doc and existing_doc.status == "ready":
        logger.warning(
            "URL content already ingested (same hash)",
            extra={"url": url, "document_id": existing_doc.id},
        )
        return {
            "status": "skipped",
            "document_id": existing_doc.id,
            "message": "Content already ingested (same hash)",
        }

    if existing_doc:
        for chunk in (await session.execute(
            select(Chunk).where(Chunk.document_id == existing_doc.id)
        )).scalars().all():
            await session.delete(chunk)
        await session.delete(existing_doc)
        await session.flush()

    title = convert_metadata.get("page_title") or convert_metadata.get("api_title") or url
    doc = Document(
        product_id=product.id,
        firmware_version_id=fw.id,
        format="url",
        source_path=url,
        source_hash=source_hash,
        title=title,
        status="processing",
    )
    session.add(doc)
    await session.flush()

    try:
        t_parse = time.perf_counter()
        sections = parse_markdown(text)
        _replace_generic_headings(sections, title)
        chunks = chunk_sections(sections)
        parse_ms = round((time.perf_counter() - t_parse) * 1000, 1)

        if not chunks:
            doc.status = "error"
            doc.error_message = "No content extracted from URL"
            await session.commit()
            logger.warning(
                "No content extracted from URL (0 chunks)",
                extra={"url": url, "document_id": doc.id},
            )
            return {"status": "error", "error": "No content extracted", "document_id": doc.id}

        _log_chunk_stats(chunks, url)

        t_embed = time.perf_counter()
        enriched = enrich_for_embedding(chunks)
        embeddings = embed_texts(enriched)
        embed_ms = round((time.perf_counter() - t_embed) * 1000, 1)

        t_db = time.perf_counter()
        for i, (chunk_data, embedding) in enumerate(zip(chunks, embeddings)):
            db_chunk = Chunk(
                document_id=doc.id,
                chunk_index=i,
                heading_path=chunk_data.heading_path,
                heading_level=chunk_data.heading_level,
                content=chunk_data.content,
                content_clean=_clean_md(chunk_data.content),
                parent_content=chunk_data.parent_content,
                token_count=chunk_data.token_count,
                embedding=embedding,
            )
            session.add(db_chunk)

        doc.total_chunks = len(chunks)
        doc.status = "ready"

        token_counts = [c.token_count for c in chunks]
        doc.total_tokens = sum(token_counts)
        doc.min_chunk_tokens = min(token_counts)
        doc.max_chunk_tokens = max(token_counts)
        doc.avg_chunk_tokens = round(sum(token_counts) / len(token_counts), 1)
        doc.embedding_tokens = sum(token_counts)

        await session.flush()
        db_ms = round((time.perf_counter() - t_db) * 1000, 1)

        duration = time.perf_counter() - t0
        doc.ingest_duration_ms = round(duration * 1000, 1)
        doc.read_ms = 0
        doc.convert_ms = convert_ms
        doc.parse_ms = parse_ms
        doc.embed_ms = embed_ms
        doc.db_ms = db_ms
        doc.embedding_model = _embedding_model_name()
        doc.embedding_dims = _settings.embedding_dims
        await session.commit()

        logger.info(
            "URL ingestion completed",
            extra={
                "url": url, "chunks": len(chunks),
                "duration_sec": round(duration, 2),
                "convert_ms": convert_ms, "parse_ms": parse_ms,
                "embed_ms": embed_ms, "db_ms": db_ms,
                "detection": detection, "product": product_name,
            },
        )
        result = {
            "status": "ok",
            "document_id": doc.id,
            "product": product_name,
            "firmware_version": firmware_version,
            "format": "url",
            "detection_method": detection,
            "chunks": len(chunks),
            "duration_sec": round(duration, 2),
        }
        if convert_metadata:
            result["convert_metadata"] = convert_metadata
        return result

    except Exception as e:
        doc.status = "error"
        doc.error_message = str(e)[:2000]
        await session.commit()
        logger.error(
            "URL ingestion failed",
            extra={
                "url": url, "document_id": doc.id,
                "error_type": type(e).__name__,
            },
            exc_info=True,
        )
        return {"status": "error", "error": str(e), "document_id": doc.id}


def _update_progress(session, document: "Document", percent: int, stage: str) -> None:
    """Persist ingestion progress so the UI can poll it."""
    document.progress_percent = percent
    document.progress_stage = stage
    session.commit()


def ingest_from_bytes(
    session,
    document: "Document",
    file_path: str,
    original_filename: str,
) -> dict:
    """Synchronous ingestion for Celery worker: file already on disk, Document already in DB.

    Runs convert -> parse -> chunk -> embed -> store. Updates document status in-place.
    """
    t0 = time.perf_counter()
    fmt = document.format
    if fmt == "auto":
        fmt = detect_format(original_filename) if original_filename else detect_format(file_path)
        document.format = fmt

    logger.info(
        "Worker ingestion started",
        extra={
            "document_id": document.id,
            "format": fmt,
            "file_path": original_filename,
            "file_size_bytes": document.file_size_bytes,
        },
    )

    _update_progress(session, document, 0, "converting")

    convert_ms = 0.0
    convert_metadata: dict = {}

    t_read = time.perf_counter()
    if fmt == "pdf":
        try:

            def _pdf_convert_progress(frac: float, stage: str) -> None:
                _update_progress(session, document, int(frac * 40), stage)

            text, convert_metadata = convert_pdf(
                file_path,
                progress_callback=_pdf_convert_progress,
            )
            convert_ms = convert_metadata.get("convert_ms", 0.0)
        except Exception as e:
            document.status = "error"
            document.error_message = f"PDF conversion failed: {e}"
            document.progress_percent = 0
            document.progress_stage = ""
            session.commit()
            return {"status": "error", "error": str(e)}
        fmt_effective = "markdown"
    elif fmt == "swagger":
        try:
            text, convert_metadata = convert_swagger_file(file_path)
            convert_ms = convert_metadata.get("total_ms", 0.0)
        except Exception as e:
            document.status = "error"
            document.error_message = f"Swagger conversion failed: {e}"
            document.progress_percent = 0
            document.progress_stage = ""
            session.commit()
            return {"status": "error", "error": str(e)}
        fmt_effective = "markdown"
    elif fmt == "proto":
        try:
            text, convert_metadata = convert_proto_file(file_path, original_filename=original_filename)
            convert_ms = convert_metadata.get("total_ms", 0.0)
        except Exception as e:
            document.status = "error"
            document.error_message = f"Proto conversion failed: {e}"
            document.progress_percent = 0
            document.progress_stage = ""
            session.commit()
            return {"status": "error", "error": str(e)}
        fmt_effective = "markdown"
    else:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception as e:
            document.status = "error"
            document.error_message = f"Failed to read file: {e}"
            document.progress_percent = 0
            document.progress_stage = ""
            session.commit()
            return {"status": "error", "error": str(e)}
        fmt_effective = fmt

    read_ms = round((time.perf_counter() - t_read) * 1000, 1)

    _update_progress(session, document, 40, "chunking")

    try:
        t_parse = time.perf_counter()
        sections = _parse_content(text, fmt_effective, file_path)
        doc_title = document.title or os.path.splitext(os.path.basename(original_filename or file_path))[0]
        _replace_generic_headings(sections, doc_title)
        chunks = chunk_sections(sections)
        parse_ms = round((time.perf_counter() - t_parse) * 1000, 1)

        if not chunks:
            document.status = "error"
            document.error_message = "No content extracted"
            document.progress_percent = 0
            document.progress_stage = ""
            session.commit()
            return {"status": "error", "error": "No content extracted", "document_id": document.id}

        _log_chunk_stats(chunks, file_path)

        _update_progress(session, document, 50, "embedding")

        t_embed = time.perf_counter()
        enriched = enrich_for_embedding(chunks)
        embeddings = embed_texts(
            enriched,
            progress_callback=lambda pct: _update_progress(
                session, document, 50 + int(pct * 40), "embedding",
            ),
        )
        embed_ms = round((time.perf_counter() - t_embed) * 1000, 1)

        _update_progress(session, document, 92, "storing")

        t_db = time.perf_counter()
        from sqlalchemy import select as sa_select
        existing_chunks = session.execute(
            sa_select(Chunk).where(Chunk.document_id == document.id)
        ).scalars().all()
        for c in existing_chunks:
            session.delete(c)
        session.flush()

        for i, (chunk_data, embedding) in enumerate(zip(chunks, embeddings)):
            db_chunk = Chunk(
                document_id=document.id,
                chunk_index=i,
                heading_path=chunk_data.heading_path,
                heading_level=chunk_data.heading_level,
                content=chunk_data.content,
                content_clean=_clean_md(chunk_data.content),
                parent_content=chunk_data.parent_content,
                token_count=chunk_data.token_count,
                embedding=embedding,
            )
            session.add(db_chunk)

        document.total_chunks = len(chunks)
        document.status = "ready"
        document.progress_percent = 100
        document.progress_stage = ""
        document.indexed_at = datetime.now(timezone.utc)

        token_counts = [c.token_count for c in chunks]
        document.total_tokens = sum(token_counts)
        document.min_chunk_tokens = min(token_counts)
        document.max_chunk_tokens = max(token_counts)
        document.avg_chunk_tokens = round(sum(token_counts) / len(token_counts), 1)
        document.embedding_tokens = sum(token_counts)

        session.flush()
        db_ms = round((time.perf_counter() - t_db) * 1000, 1)

        duration = time.perf_counter() - t0
        document.ingest_duration_ms = round(duration * 1000, 1)
        document.read_ms = read_ms
        document.convert_ms = convert_ms
        document.parse_ms = parse_ms
        document.embed_ms = embed_ms
        document.db_ms = db_ms
        document.embedding_model = _embedding_model_name()
        document.embedding_dims = _settings.embedding_dims

        if convert_metadata.get("ocr_applied"):
            document.ocr_ms = convert_metadata.get("ocr_ms")
            document.detected_language = convert_metadata.get("detected_languages_str")
            ocr_stats = convert_metadata.get("ocr_stats", {})
            document.ocr_images_total = ocr_stats.get("ocr_images_total")
            document.ocr_images_success = ocr_stats.get("ocr_images_success")
            document.ocr_images_empty = ocr_stats.get("ocr_images_empty")
            document.ocr_images_failed = ocr_stats.get("ocr_images_failed")

        session.commit()

        logger.info(
            "Worker ingestion completed",
            extra={
                "document_id": document.id,
                "file": original_filename,
                "chunks": len(chunks),
                "duration_sec": round(duration, 2),
                "read_ms": read_ms,
                "convert_ms": convert_ms,
                "parse_ms": parse_ms,
                "embed_ms": embed_ms,
                "db_ms": db_ms,
                "format": fmt,
                "file_size_bytes": document.file_size_bytes,
                "ocr_applied": convert_metadata.get("ocr_applied", False),
            },
        )
        result = {
            "status": "ok",
            "document_id": document.id,
            "format": fmt,
            "chunks": len(chunks),
            "duration_sec": round(duration, 2),
        }
        if convert_metadata:
            result["convert_metadata"] = convert_metadata
        return result

    except Exception as e:
        document.status = "error"
        document.error_message = str(e)[:2000]
        document.progress_percent = 0
        document.progress_stage = ""
        session.commit()
        return {"status": "error", "error": str(e), "document_id": document.id}


async def _get_or_create_product(session: AsyncSession, name: str, manufacturer: str) -> Product:
    result = await session.execute(
        select(Product).where(Product.name == name)
    )
    product = result.scalar_one_or_none()
    if product:
        return product

    product = Product(name=name, manufacturer=manufacturer)
    session.add(product)
    await session.flush()
    return product


async def _get_or_create_firmware(session: AsyncSession, product_id: int, version: str) -> FirmwareVersion:
    result = await session.execute(
        select(FirmwareVersion).where(
            FirmwareVersion.product_id == product_id,
            FirmwareVersion.version == version,
        )
    )
    fw = result.scalar_one_or_none()
    if fw:
        return fw

    fw = FirmwareVersion(product_id=product_id, version=version)
    session.add(fw)
    await session.flush()
    return fw
