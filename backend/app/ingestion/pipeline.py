"""Ingestion pipeline: detect format -> parse -> chunk -> embed -> store."""

import hashlib
import logging
import os
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.chunker import chunk_sections
from app.ingestion.embedder import embed_texts
from app.ingestion.parsers.markdown import parse_markdown
from app.ingestion.parsers.swagger import parse_swagger
from app.models import Chunk, Device, Document, FirmwareVersion

logger = logging.getLogger(__name__)


def _file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(8192), b""):
            h.update(block)
    return h.hexdigest()


def detect_format(file_path: str) -> str:
    """Auto-detect document format by extension and content."""
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".md":
        return "markdown"
    if ext == ".pdf":
        return "pdf"
    if ext in (".yaml", ".yml"):
        return "swagger"
    if ext == ".json":
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                start = f.read(512)
            if '"swagger"' in start or '"openapi"' in start:
                return "swagger"
        except Exception:
            pass
        return "markdown"

    return "markdown"


def _parse_content(text: str, fmt: str, file_path: str):
    if fmt == "swagger":
        return parse_swagger(text, file_path)
    return parse_markdown(text)


async def ingest_file(
    session: AsyncSession,
    file_path: str,
    device_name: str,
    firmware_version: str = "1.0",
    manufacturer: str = "",
    fmt: str = "auto",
) -> dict:
    """Full ingestion pipeline: file -> parse -> chunk -> embed -> DB.

    Returns dict with status, document_id, chunks count, duration.
    """
    t0 = time.perf_counter()
    file_path = os.path.normpath(file_path)

    if not os.path.isfile(file_path):
        return {"status": "error", "error": f"File not found: {file_path}"}

    if fmt == "auto":
        fmt = detect_format(file_path)

    logger.info("Ingesting %s (format=%s, device=%s, fw=%s)", file_path, fmt, device_name, firmware_version)

    if fmt == "pdf":
        try:
            import pymupdf4llm
            text = pymupdf4llm.to_markdown(file_path)
        except Exception as e:
            return {"status": "error", "error": f"PDF conversion failed: {e}"}
        fmt_effective = "markdown"
    else:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception as e:
            return {"status": "error", "error": f"Failed to read file: {e}"}
        fmt_effective = fmt

    source_hash = _file_hash(file_path)

    device = await _get_or_create_device(session, device_name, manufacturer)
    fw = await _get_or_create_firmware(session, device.id, firmware_version)

    existing = await session.execute(
        select(Document).where(
            Document.device_id == device.id,
            Document.firmware_version_id == fw.id,
            Document.source_hash == source_hash,
        )
    )
    existing_doc = existing.scalar_one_or_none()
    if existing_doc and existing_doc.status == "ready":
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
        device_id=device.id,
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
        sections = _parse_content(text, fmt_effective, file_path)
        chunks = chunk_sections(sections)

        if not chunks:
            doc.status = "error"
            doc.error_message = "No content extracted"
            await session.commit()
            return {"status": "error", "error": "No content extracted", "document_id": doc.id}

        logger.info("Parsed %d sections -> %d chunks, embedding...", len(sections), len(chunks))

        contents = [c.content for c in chunks]
        embeddings = embed_texts(contents)

        for i, (chunk_data, embedding) in enumerate(zip(chunks, embeddings)):
            db_chunk = Chunk(
                document_id=doc.id,
                chunk_index=i,
                heading_path=chunk_data.heading_path,
                heading_level=chunk_data.heading_level,
                content=chunk_data.content,
                token_count=chunk_data.token_count,
                embedding=embedding,
            )
            session.add(db_chunk)

        doc.total_chunks = len(chunks)
        doc.status = "ready"
        await session.commit()

        duration = time.perf_counter() - t0
        logger.info(
            "Ingested %s: %d chunks, %.1fs",
            os.path.basename(file_path), len(chunks), duration,
        )
        return {
            "status": "ok",
            "document_id": doc.id,
            "device": device_name,
            "firmware_version": firmware_version,
            "format": fmt,
            "chunks": len(chunks),
            "duration_sec": round(duration, 2),
        }

    except Exception as e:
        doc.status = "error"
        doc.error_message = str(e)[:2000]
        await session.commit()
        logger.exception("Ingestion failed for %s", file_path)
        return {"status": "error", "error": str(e), "document_id": doc.id}


async def _get_or_create_device(session: AsyncSession, name: str, manufacturer: str) -> Device:
    result = await session.execute(
        select(Device).where(Device.name == name)
    )
    device = result.scalar_one_or_none()
    if device:
        return device

    device = Device(name=name, manufacturer=manufacturer)
    session.add(device)
    await session.flush()
    return device


async def _get_or_create_firmware(session: AsyncSession, device_id: int, version: str) -> FirmwareVersion:
    result = await session.execute(
        select(FirmwareVersion).where(
            FirmwareVersion.device_id == device_id,
            FirmwareVersion.version == version,
        )
    )
    fw = result.scalar_one_or_none()
    if fw:
        return fw

    fw = FirmwareVersion(device_id=device_id, version=version)
    session.add(fw)
    await session.flush()
    return fw
