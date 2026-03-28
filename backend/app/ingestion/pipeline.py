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
from app.ingestion.converters.postman import convert_postman_file, is_postman_collection
from app.ingestion.converters.web import convert_url
from app.ingestion.embedder import embed_texts
from app.config import settings as _settings
from app.ingestion.parsers.markdown import parse_markdown
from app.ingestion.parsers.swagger import parse_swagger
from app.ingestion.text_cleaner import clean_for_embedding as _clean_md
from app.models import Chunk, Product, Document, FirmwareVersion

logger = logging.getLogger(__name__)


class IngestionCancelled(Exception):
    """Raised when a document's ingestion is cancelled mid-flight."""


def _embedding_model_name() -> str:
    return _settings.embedding_model_gemini


MAX_EMBEDDING_TOKENS = 500

def enrich_for_embedding(
    chunks: list[ChunkData],
    chunk_metadata: list[dict] | None = None,
) -> list[str]:
    """Clean Markdown artifacts and prepend heading_path + metadata for better embeddings.

    Enrichment steps:
    1. Strip Markdown formatting noise (bold, links, images, HTML).
    2. Prepend heading hierarchy.
    3. Prepend doc_type and flattened entities (if metadata is available).

    Warns and truncates if enriched text exceeds model max_seq_length.
    """
    from app.ingestion.chunker import _estimate_tokens

    enriched: list[str] = []
    for idx, c in enumerate(chunks):
        cleaned = _clean_md(c.content)
        prefix_parts: list[str] = []
        if c.heading_path:
            prefix_parts.append(f"[{c.heading_path}]")

        if chunk_metadata and idx < len(chunk_metadata):
            meta = chunk_metadata[idx]
            doc_type = meta.get("doc_type", "other")
            if doc_type and doc_type != "other":
                prefix_parts.append(f"[type: {doc_type}]")
            entities = meta.get("entities", {})
            if entities:
                flat = []
                for vals in entities.values():
                    if isinstance(vals, list):
                        flat.extend(str(v) for v in vals if v)
                if flat:
                    prefix_parts.append(f"[entities: {', '.join(flat[:20])}]")

        heading_prefix = "\n".join(prefix_parts) + "\n" if prefix_parts else ""
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


def detect_format(file_path: str, content_path: str | None = None) -> str:
    """Auto-detect document format by extension and content.

    ``file_path`` is used for its extension.  ``content_path``, when given,
    is the actual file on disk whose bytes will be inspected (e.g. the temp
    file downloaded from S3).  When omitted, *file_path* is used for both.
    """
    ext = os.path.splitext(file_path)[1].lower()
    probe = content_path or file_path

    if ext in (".md", ".txt"):
        return "markdown"
    if ext == ".pdf":
        return "pdf"
    if ext == ".proto":
        return "proto"
    if ext in (".wsdl", ".xml"):
        return "markdown"
    if ext in (".yaml", ".yml", ".json"):
        if ext == ".json" and is_postman_collection(probe):
            return "postman"
        if is_swagger_file(probe):
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
    elif fmt == "postman":
        try:
            text, convert_metadata = convert_postman_file(file_path)
            convert_ms = convert_metadata.get("total_ms", 0.0)
        except Exception as e:
            logger.error(
                "Postman conversion failed",
                extra={"file_path": file_path, "error_type": type(e).__name__},
                exc_info=True,
            )
            return {"status": "error", "error": f"Postman conversion failed: {e}"}
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

        from app.ingestion.metadata_extractor import extract_metadata_batch_async
        extraction_result = await extract_metadata_batch_async(
            [c.content for c in chunks]
        )
        chunk_meta_dicts = [
            {"doc_type": m.doc_type, "entities": m.entities}
            for m in extraction_result.metadata
        ]

        t_embed = time.perf_counter()
        enriched = enrich_for_embedding(chunks, chunk_metadata=chunk_meta_dicts)
        embeddings, embedding_api_tokens = embed_texts(enriched)
        embed_ms = round((time.perf_counter() - t_embed) * 1000, 1)

        t_db = time.perf_counter()
        for i, (chunk_data, embedding) in enumerate(zip(chunks, embeddings)):
            meta = chunk_meta_dicts[i] if i < len(chunk_meta_dicts) else {}
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
                doc_type=meta.get("doc_type", "other"),
                entities=meta.get("entities", {}),
            )
            session.add(db_chunk)

        doc.total_chunks = len(chunks)
        doc.status = "ready"

        token_counts = [c.token_count for c in chunks]
        doc.total_tokens = sum(token_counts)
        doc.min_chunk_tokens = min(token_counts)
        doc.max_chunk_tokens = max(token_counts)
        doc.avg_chunk_tokens = round(sum(token_counts) / len(token_counts), 1)
        doc.embedding_tokens = embedding_api_tokens or sum(token_counts)

        await session.flush()
        db_ms = round((time.perf_counter() - t_db) * 1000, 1)

        duration = time.perf_counter() - t0
        doc.ingest_duration_ms = round(duration * 1000, 1)
        doc.read_ms = read_ms
        doc.convert_ms = convert_ms
        doc.parse_ms = parse_ms
        doc.embed_ms = embed_ms
        doc.db_ms = db_ms
        doc.extract_ms = extraction_result.usage.extract_ms
        doc.extract_prompt_tokens = extraction_result.usage.prompt_tokens
        doc.extract_completion_tokens = extraction_result.usage.completion_tokens
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
            doc.ocr_prompt_tokens = ocr_stats.get("ocr_prompt_tokens", 0)
            doc.ocr_completion_tokens = ocr_stats.get("ocr_completion_tokens", 0)
            doc.ocr_model = _settings.ocr_vision_model

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
        source_container=url,
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

        from app.ingestion.metadata_extractor import extract_metadata_batch_async
        extraction_result = await extract_metadata_batch_async(
            [c.content for c in chunks]
        )
        chunk_meta_dicts = [
            {"doc_type": m.doc_type, "entities": m.entities}
            for m in extraction_result.metadata
        ]

        t_embed = time.perf_counter()
        enriched = enrich_for_embedding(chunks, chunk_metadata=chunk_meta_dicts)
        embeddings, embedding_api_tokens = embed_texts(enriched)
        embed_ms = round((time.perf_counter() - t_embed) * 1000, 1)

        t_db = time.perf_counter()
        for i, (chunk_data, embedding) in enumerate(zip(chunks, embeddings)):
            meta = chunk_meta_dicts[i] if i < len(chunk_meta_dicts) else {}
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
                doc_type=meta.get("doc_type", "other"),
                entities=meta.get("entities", {}),
            )
            session.add(db_chunk)

        doc.total_chunks = len(chunks)
        doc.status = "ready"

        token_counts = [c.token_count for c in chunks]
        doc.total_tokens = sum(token_counts)
        doc.min_chunk_tokens = min(token_counts)
        doc.max_chunk_tokens = max(token_counts)
        doc.avg_chunk_tokens = round(sum(token_counts) / len(token_counts), 1)
        doc.embedding_tokens = embedding_api_tokens or sum(token_counts)

        await session.flush()
        db_ms = round((time.perf_counter() - t_db) * 1000, 1)

        duration = time.perf_counter() - t0
        doc.ingest_duration_ms = round(duration * 1000, 1)
        doc.read_ms = 0
        doc.convert_ms = convert_ms
        doc.parse_ms = parse_ms
        doc.embed_ms = embed_ms
        doc.db_ms = db_ms
        doc.extract_ms = extraction_result.usage.extract_ms
        doc.extract_prompt_tokens = extraction_result.usage.prompt_tokens
        doc.extract_completion_tokens = extraction_result.usage.completion_tokens
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


class _ProgressThrottle:
    """Throttle DB commits for progress updates to at most once per second."""
    __slots__ = ("_last_commit", "_last_stage")

    def __init__(self) -> None:
        self._last_commit = 0.0
        self._last_stage = ""

    def should_commit(self, stage: str) -> bool:
        now = time.perf_counter()
        if stage != self._last_stage or (now - self._last_commit) >= 1.0:
            self._last_commit = now
            self._last_stage = stage
            return True
        return False

_progress_throttle = _ProgressThrottle()

def _update_progress(session, document: "Document", percent: int, stage: str) -> None:
    """Persist ingestion progress so the UI can poll it.

    Throttled to commit at most once per second, unless the stage changes.
    """
    document.progress_percent = percent
    document.progress_stage = stage
    if _progress_throttle.should_commit(stage):
        session.commit()


def _check_cancelled(session, document: "Document") -> None:
    """Re-read document status from DB; raise IngestionCancelled if cancelled."""
    session.commit()
    session.expire(document, ["status"])
    session.refresh(document, ["status"])
    if document.status == "cancelled":
        logger.info("Ingestion cancelled", extra={"document_id": document.id})
        raise IngestionCancelled(f"Document {document.id} cancelled")


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
        fmt = detect_format(original_filename, content_path=file_path) if original_filename else detect_format(file_path)
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

    _check_cancelled(session, document)
    _update_progress(session, document, 5, "converting")

    convert_ms = 0.0
    convert_metadata: dict = {}

    t_read = time.perf_counter()
    if fmt == "pdf":
        try:

            def _pdf_convert_progress(frac: float, stage: str) -> None:
                _update_progress(session, document, 5 + int(frac * 40), stage)

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
    elif fmt == "postman":
        try:
            text, convert_metadata = convert_postman_file(file_path)
            convert_ms = convert_metadata.get("total_ms", 0.0)
        except Exception as e:
            document.status = "error"
            document.error_message = f"Postman conversion failed: {e}"
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

    if fmt in ("pdf", "swagger", "postman", "proto"):
        try:
            from app.s3 import upload_file as _s3_upload
            converted_key = f"documents/{document.id}/converted.md"
            _s3_upload(converted_key, text.encode("utf-8"), content_type="text/markdown")
            document.converted_s3_key = converted_key
            session.commit()
        except Exception:
            logger.warning("Failed to save converted MD to S3", extra={"document_id": document.id}, exc_info=True)

    _check_cancelled(session, document)
    _update_progress(session, document, 45, "chunking")

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

        _check_cancelled(session, document)
        _update_progress(session, document, 50, "extracting_metadata")

        from app.ingestion.metadata_extractor import extract_metadata_batch_sync
        extraction_result = extract_metadata_batch_sync(
            [c.content for c in chunks]
        )
        chunk_meta_dicts = [
            {"doc_type": m.doc_type, "entities": m.entities}
            for m in extraction_result.metadata
        ]

        _check_cancelled(session, document)
        _update_progress(session, document, 55, "embedding")

        t_embed = time.perf_counter()
        enriched = enrich_for_embedding(chunks, chunk_metadata=chunk_meta_dicts)
        embeddings, embedding_api_tokens = embed_texts(
            enriched,
            progress_callback=lambda pct: _update_progress(
                session, document, 55 + int(pct * 37), "embedding",
            ),
        )
        embed_ms = round((time.perf_counter() - t_embed) * 1000, 1)

        _check_cancelled(session, document)
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
            meta = chunk_meta_dicts[i] if i < len(chunk_meta_dicts) else {}
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
                doc_type=meta.get("doc_type", "other"),
                entities=meta.get("entities", {}),
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
        document.embedding_tokens = embedding_api_tokens or sum(token_counts)

        session.flush()
        db_ms = round((time.perf_counter() - t_db) * 1000, 1)

        duration = time.perf_counter() - t0
        document.ingest_duration_ms = round(duration * 1000, 1)
        document.read_ms = read_ms
        document.convert_ms = convert_ms
        document.parse_ms = parse_ms
        document.embed_ms = embed_ms
        document.db_ms = db_ms
        document.extract_ms = extraction_result.usage.extract_ms
        document.extract_prompt_tokens = extraction_result.usage.prompt_tokens
        document.extract_completion_tokens = extraction_result.usage.completion_tokens
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
            document.ocr_prompt_tokens = ocr_stats.get("ocr_prompt_tokens", 0)
            document.ocr_completion_tokens = ocr_stats.get("ocr_completion_tokens", 0)
            document.ocr_model = _settings.ocr_vision_model

        if convert_metadata.get("ocr_error"):
            document.error_message = f"OCR failed: {convert_metadata['ocr_error']}"

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


async def _get_or_create_product(session: AsyncSession, name: str, manufacturer: str, *, tenant_id=None) -> Product:
    from app.slugify import slugify

    result = await session.execute(
        select(Product).where(Product.name == name, Product.manufacturer == manufacturer)
    )
    product = result.scalar_one_or_none()
    if product:
        if not product.slug:
            product.slug = slugify(name)
            product.manufacturer_slug = slugify(manufacturer) if manufacturer else "default"
            await session.flush()
        return product

    slug = slugify(name)
    mfr_slug = slugify(manufacturer) if manufacturer else "default"
    product = Product(
        name=name,
        manufacturer=manufacturer,
        model=name,
        slug=slug,
        manufacturer_slug=mfr_slug,
        tenant_id=tenant_id,
    )
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
