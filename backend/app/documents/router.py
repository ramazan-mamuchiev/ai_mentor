"""REST API router for document ingestion and management."""

import hashlib
import logging
import os
import time

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import select

from app.database import async_session
from app.documents.schemas import (
    DeleteResponse,
    DocumentDownload,
    DocumentListItem,
    DocumentStatus,
    IngestResponse,
)
from app.models import Chunk, Device, Document, FirmwareVersion
from app.s3 import delete_file, generate_presigned_url, s3_key_for_document, upload_file
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

ALLOWED_EXTENSIONS = {".md", ".json", ".yaml", ".yml", ".pdf"}
MAX_UPLOAD_BYTES = settings.max_upload_size_mb * 1024 * 1024


@router.post("/ingest", response_model=IngestResponse)
async def ingest_document(
    request: Request,
    file: UploadFile = File(...),
    device_name: str = Form(...),
    firmware_version: str = Form(default="1.0"),
    manufacturer: str = Form(default=""),
    format: str = Form(default="auto"),
    force: bool = Form(default=False),
):
    """Upload a documentation file and trigger background ingestion.

    Supported formats: Markdown (.md), Swagger/OpenAPI (.yaml, .json), PDF (.pdf).
    Returns immediately with document_id and task_id for status polling.

    If a document with identical content already exists, returns 200 with
    status "skipped" and information about the existing document.
    Use force=True to bypass deduplication and re-upload anyway.
    """
    original_filename = file.filename or "unknown"
    ext = os.path.splitext(original_filename)[1].lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file extension '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    file_data = await file.read()
    file_size = len(file_data)

    if file_size > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File too large ({file_size} bytes). Maximum: {MAX_UPLOAD_BYTES} bytes ({settings.max_upload_size_mb} MB)",
        )

    if file_size == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    source_hash = hashlib.sha256(file_data).hexdigest()

    client_ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown")

    logger.info(
        "Document upload received",
        extra={
            "original_filename": original_filename,
            "file_size_bytes": file_size,
            "device_name": device_name,
            "format": format,
            "source_hash": source_hash,
            "force": force,
            "client_ip": client_ip,
        },
    )

    async with async_session() as session:
        if not force:
            existing = await _find_by_hash(session, source_hash)
            if existing is not None:
                logger.info(
                    "Duplicate document skipped",
                    extra={
                        "source_hash": source_hash,
                        "existing_document_id": existing.id,
                        "existing_title": existing.title,
                        "uploaded_filename": original_filename,
                    },
                )
                return IngestResponse(
                    document_id=existing.id,
                    status="skipped",
                    message=(
                        f"Документ с таким содержимым уже загружен: "
                        f"«{existing.title}» (id={existing.id}, "
                        f"файл: {existing.original_filename}). "
                        f"Повторная загрузка пропущена."
                    ),
                    existing_document_id=existing.id,
                    existing_document_title=existing.title,
                )

        device = await _get_or_create_device(session, device_name, manufacturer)
        fw = await _get_or_create_firmware(session, device.id, firmware_version)

        doc = Document(
            device_id=device.id,
            firmware_version_id=fw.id,
            format=format,
            original_filename=original_filename,
            file_size_bytes=file_size,
            title=os.path.splitext(original_filename)[0],
            status="pending",
            source_hash=source_hash,
        )
        session.add(doc)
        await session.flush()

        s3_key = s3_key_for_document(doc.id, original_filename)
        content_type = file.content_type or "application/octet-stream"
        upload_file(s3_key, file_data, content_type)

        doc.s3_key = s3_key
        await session.commit()

        from app.celery_app import ingest_document_task
        task = ingest_document_task.delay(doc.id)

        logger.info(
            "Document ingestion queued",
            extra={
                "document_id": doc.id,
                "task_id": task.id,
                "s3_key": s3_key,
                "file_size_bytes": file_size,
                "client_ip": client_ip,
            },
        )

        return IngestResponse(
            document_id=doc.id,
            status="pending",
            message="Document uploaded and queued for processing",
            task_id=task.id,
        )


@router.get("", response_model=list[DocumentListItem])
async def list_documents():
    """List all documents with their status."""
    async with async_session() as session:
        result = await session.execute(
            select(
                Document.id,
                Document.title,
                Document.format,
                Document.status,
                Document.original_filename,
                Document.file_size_bytes,
                Document.total_chunks,
                Device.name.label("device_name"),
                FirmwareVersion.version.label("firmware_version"),
                Document.ingested_at,
            )
            .join(Device, Document.device_id == Device.id)
            .join(FirmwareVersion, Document.firmware_version_id == FirmwareVersion.id)
            .order_by(Document.ingested_at.desc())
        )
        rows = result.all()
        return [DocumentListItem(**dict(row._mapping)) for row in rows]


@router.get("/{document_id}", response_model=DocumentStatus)
async def get_document(document_id: int):
    """Get document details and ingestion status."""
    async with async_session() as session:
        doc = await session.get(Document, document_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found")
        return DocumentStatus(
            document_id=doc.id,
            status=doc.status,
            title=doc.title,
            format=doc.format,
            original_filename=doc.original_filename,
            file_size_bytes=doc.file_size_bytes,
            total_chunks=doc.total_chunks,
            error_message=doc.error_message,
            ingested_at=doc.ingested_at,
        )


@router.get("/{document_id}/status", response_model=DocumentStatus)
async def get_document_status(document_id: int):
    """Poll document ingestion status (alias for GET /{id})."""
    return await get_document(document_id)


@router.get("/{document_id}/download", response_model=DocumentDownload)
async def download_document(document_id: int):
    """Get a presigned URL to download the original document file."""
    async with async_session() as session:
        doc = await session.get(Document, document_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found")
        if not doc.s3_key:
            raise HTTPException(status_code=404, detail="No file stored for this document")

        url = generate_presigned_url(doc.s3_key, expires_in=900)
        return DocumentDownload(
            document_id=doc.id,
            original_filename=doc.original_filename,
            download_url=url,
            expires_in_seconds=900,
        )


@router.delete("/{document_id}", response_model=DeleteResponse)
async def delete_document(document_id: int):
    """Delete a document and all its chunks. Also removes the file from S3."""
    async with async_session() as session:
        doc = await session.get(Document, document_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found")

        if doc.s3_key:
            try:
                delete_file(doc.s3_key)
            except Exception as e:
                logger.warning("Failed to delete S3 file", extra={"s3_key": doc.s3_key, "error": str(e)})

        chunks = (await session.execute(
            select(Chunk).where(Chunk.document_id == doc.id)
        )).scalars().all()
        for chunk in chunks:
            await session.delete(chunk)

        await session.delete(doc)
        await session.commit()

        logger.info("Document deleted", extra={"document_id": document_id})
        return DeleteResponse(
            document_id=document_id,
            deleted=True,
            message="Document and all chunks deleted",
        )


@router.post("/reindex", status_code=202)
async def reindex_all_documents():
    """Re-embed all chunks using the current embedding model.

    Use after switching embedding models to regenerate all vectors.
    Runs synchronously — may take several minutes for large document sets.
    """
    from app.ingestion.embedder import embed_texts

    t0 = time.time()
    total_chunks = 0
    total_docs = 0

    async with async_session() as session:
        docs_result = await session.execute(
            select(Document).where(Document.status == "ready")
        )
        docs = docs_result.scalars().all()

        for doc in docs:
            chunks_result = await session.execute(
                select(Chunk)
                .where(Chunk.document_id == doc.id)
                .order_by(Chunk.chunk_index)
            )
            chunks = chunks_result.scalars().all()
            if not chunks:
                continue

            contents = [c.content for c in chunks]
            embeddings = embed_texts(contents)

            for chunk, emb in zip(chunks, embeddings):
                chunk.embedding = emb

            total_chunks += len(chunks)
            total_docs += 1

            logger.info(
                "Document reindexed",
                extra={"document_id": doc.id, "title": doc.title, "chunks": len(chunks)},
            )

        await session.commit()

    duration = round(time.time() - t0, 1)
    logger.info(
        "Reindex completed",
        extra={"total_docs": total_docs, "total_chunks": total_chunks, "duration_sec": duration},
    )
    return {
        "status": "completed",
        "documents_reindexed": total_docs,
        "chunks_reindexed": total_chunks,
        "duration_sec": duration,
    }


async def _find_by_hash(session, source_hash: str) -> Document | None:
    """Find an existing document with the same content hash."""
    result = await session.execute(
        select(Document).where(Document.source_hash == source_hash).limit(1)
    )
    return result.scalar_one_or_none()


async def _get_or_create_device(session, name: str, manufacturer: str):
    result = await session.execute(select(Device).where(Device.name == name))
    device = result.scalar_one_or_none()
    if device:
        return device
    device = Device(name=name, manufacturer=manufacturer)
    session.add(device)
    await session.flush()
    return device


async def _get_or_create_firmware(session, device_id: int, version: str):
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
