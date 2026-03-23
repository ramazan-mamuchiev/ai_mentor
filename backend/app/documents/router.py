"""REST API router for document ingestion and management."""

import hashlib
import logging
import os
import time

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import func, select

from app.database import async_session
from app.documents.schemas import (
    ArchiveFileResult,
    ArchiveIngestResponse,
    DeleteResponse,
    DocumentDebugInfo,
    DocumentDownload,
    DocumentListItem,
    DocumentStatus,
    IngestResponse,
    UrlIngestRequest,
    UrlIngestResponse,
)
from app.models import Chunk, Product, Document, FirmwareVersion
from app.s3 import delete_file, generate_presigned_url, s3_key_for_document, upload_file
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

ALLOWED_EXTENSIONS = {".md", ".json", ".yaml", ".yml", ".pdf", ".proto", ".txt", ".wsdl", ".xml"}
MAX_UPLOAD_BYTES = settings.max_upload_size_mb * 1024 * 1024


@router.post("/ingest", response_model=IngestResponse)
async def ingest_document(
    request: Request,
    file: UploadFile = File(...),
    product_name: str = Form(...),
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
            "product_name": product_name,
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

        product = await _get_or_create_product(session, product_name, manufacturer)
        fw = await _get_or_create_firmware(session, product.id, firmware_version)

        doc = Document(
            product_id=product.id,
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

        doc.celery_task_id = task.id
        await session.commit()

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


@router.post("/ingest-url", response_model=UrlIngestResponse)
async def ingest_url(request: Request, body: UrlIngestRequest):
    """Import documentation from a web URL.

    Supports Confluence page trees (auto-detected by URL pattern) and
    single web pages. For Confluence, recursively crawls all child pages
    and ingests each as a separate document.

    Processing runs in background via Celery.
    """
    from app.ingestion.converters.confluence import parse_confluence_url

    url = body.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    client_ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown")

    logger.info("URL ingest request received", extra={
        "url": url,
        "product_name": body.product_name,
        "client_ip": client_ip,
    })

    is_confluence = False
    try:
        parse_confluence_url(url)
        is_confluence = True
    except ValueError:
        pass

    if is_confluence:
        from app.celery_app import ingest_confluence_task
        task = ingest_confluence_task.delay(
            url=url,
            product_name=body.product_name,
            firmware_version=body.firmware_version,
            manufacturer=body.manufacturer,
        )
        logger.info("Confluence crawl task queued", extra={
            "url": url, "task_id": task.id, "client_ip": client_ip,
        })
        return UrlIngestResponse(
            status="pending",
            message="Confluence documentation crawl queued for processing",
            url=url,
            product_name=body.product_name,
            task_id=task.id,
        )

    from app.celery_app import ingest_single_url_task
    task = ingest_single_url_task.delay(
        url=url,
        product_name=body.product_name,
        firmware_version=body.firmware_version,
        manufacturer=body.manufacturer,
    )
    logger.info("Single URL ingest task queued", extra={
        "url": url, "task_id": task.id, "client_ip": client_ip,
    })
    return UrlIngestResponse(
        status="pending",
        message="Web page queued for processing",
        url=url,
        product_name=body.product_name,
        task_id=task.id,
    )


from app.documents.archive import (
    ARCHIVE_ALLOWED_EXTENSIONS,
    SUPPORTED_ARCHIVE_EXTENSIONS,
    _archive_ext,
    extract_archive,
)

MAX_ARCHIVE_BYTES = settings.max_archive_size_mb * 1024 * 1024


@router.post("/ingest-archive", response_model=ArchiveIngestResponse)
async def ingest_archive(
    request: Request,
    file: UploadFile = File(...),
    product_name: str = Form(...),
    firmware_version: str = Form(default="1.0"),
    manufacturer: str = Form(default=""),
    force: bool = Form(default=False),
):
    """Upload an archive containing multiple documentation files for a single product.

    Each file inside the archive is ingested separately and linked to the same product.
    Supported archive formats: .zip, .7z, .tar, .tar.gz, .tgz, .tar.bz2, .tar.xz, .rar
    Supported inner file types: .md, .json, .yaml, .yml, .pdf, .proto, .txt, .wsdl, .xml
    """
    original_filename = file.filename or "archive.zip"
    archive_ext = _archive_ext(original_filename)

    if archive_ext not in SUPPORTED_ARCHIVE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported archive format '{archive_ext}'. Supported: {', '.join(sorted(SUPPORTED_ARCHIVE_EXTENSIONS))}",
        )

    file_data = await file.read()
    file_size = len(file_data)

    if file_size > MAX_ARCHIVE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Archive too large ({file_size} bytes). Maximum: {MAX_ARCHIVE_BYTES} bytes",
        )

    if file_size == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    client_ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown")
    logger.info(
        "Archive upload received",
        extra={
            "original_filename": original_filename,
            "file_size_bytes": file_size,
            "product_name": product_name,
            "archive_format": archive_ext,
            "client_ip": client_ip,
        },
    )

    entries = extract_archive(file_data, original_filename)

    if not entries:
        raise HTTPException(status_code=400, detail="No supported files found in archive")

    results: list[ArchiveFileResult] = []
    accepted = 0
    skipped = 0
    errors = 0

    async with async_session() as session:
        product = await _get_or_create_product(session, product_name, manufacturer)
        fw = await _get_or_create_firmware(session, product.id, firmware_version)

        for arc_path, entry_data in entries:
            entry_filename = os.path.basename(arc_path)

            try:
                entry_hash = hashlib.sha256(entry_data).hexdigest()

                if not force:
                    existing = await _find_by_hash(session, entry_hash)
                    if existing is not None:
                        skipped += 1
                        results.append(ArchiveFileResult(
                            filename=arc_path,
                            status="skipped",
                            document_id=existing.id,
                            message=f"Duplicate of «{existing.title}» (id={existing.id})",
                        ))
                        continue

                doc = Document(
                    product_id=product.id,
                    firmware_version_id=fw.id,
                    format="auto",
                    original_filename=entry_filename,
                    file_size_bytes=len(entry_data),
                    title=os.path.splitext(entry_filename)[0],
                    status="pending",
                    source_hash=entry_hash,
                    source_container=original_filename,
                )
                session.add(doc)
                await session.flush()

                s3_key = s3_key_for_document(doc.id, entry_filename)
                content_type = "application/octet-stream"
                upload_file(s3_key, entry_data, content_type)
                doc.s3_key = s3_key

                await session.commit()

                from app.celery_app import ingest_document_task
                task = ingest_document_task.delay(doc.id)

                accepted += 1
                results.append(ArchiveFileResult(
                    filename=arc_path,
                    status="pending",
                    document_id=doc.id,
                    task_id=task.id,
                    message="Queued for processing",
                ))

            except Exception as e:
                errors += 1
                results.append(ArchiveFileResult(
                    filename=arc_path,
                    status="error",
                    message=str(e)[:500],
                ))
                logger.error(
                    "Archive entry ingestion failed",
                    extra={"entry": arc_path, "error_type": type(e).__name__},
                    exc_info=True,
                )

    logger.info(
        "Archive ingestion completed",
        extra={
            "product_name": product_name,
            "total_files": len(entries),
            "accepted": accepted,
            "skipped": skipped,
            "errors": errors,
        },
    )

    return ArchiveIngestResponse(
        product_name=product_name,
        total_files=len(entries),
        accepted=accepted,
        skipped=skipped,
        errors=errors,
        files=results,
    )


@router.get("", response_model=list[DocumentListItem])
async def list_documents(product_id: int | None = None):
    """List all documents with their status. Optionally filter by product_id."""
    async with async_session() as session:
        query = (
            select(
                Document.id,
                Document.title,
                Document.format,
                Document.status,
                Document.original_filename,
                Document.file_size_bytes,
                Document.total_chunks,
                Product.name.label("product_name"),
                FirmwareVersion.version.label("firmware_version"),
                Document.error_message,
                Document.uploaded_at,
                Document.indexed_at,
                Document.progress_percent,
                Document.progress_stage,
                Document.detected_language,
                Document.source_container,
            )
            .join(Product, Document.product_id == Product.id)
            .join(FirmwareVersion, Document.firmware_version_id == FirmwareVersion.id)
            .order_by(Document.uploaded_at.desc())
        )
        if product_id is not None:
            query = query.where(Document.product_id == product_id)
        result = await session.execute(query)
        rows = result.all()
        return [DocumentListItem(**dict(row._mapping)) for row in rows]


@router.patch("/{document_id}", response_model=DocumentStatus)
async def update_document(document_id: int, title: str | None = None, product_id: int | None = None, firmware_version_id: int | None = None):
    """Update document properties (title, product, firmware version)."""
    async with async_session() as session:
        doc = await session.get(Document, document_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found")

        if title is not None:
            doc.title = title
        if product_id is not None:
            product = await session.get(Product, product_id)
            if product is None:
                raise HTTPException(status_code=400, detail="Target product not found")
            doc.product_id = product_id
        if firmware_version_id is not None:
            fw = await session.get(FirmwareVersion, firmware_version_id)
            if fw is None:
                raise HTTPException(status_code=400, detail="Firmware version not found")
            doc.firmware_version_id = firmware_version_id

        await session.commit()
        await session.refresh(doc)

        return DocumentStatus(
            document_id=doc.id,
            status=doc.status,
            title=doc.title,
            format=doc.format,
            original_filename=doc.original_filename,
            file_size_bytes=doc.file_size_bytes,
            total_chunks=doc.total_chunks,
            error_message=doc.error_message,
            uploaded_at=doc.uploaded_at,
            indexed_at=doc.indexed_at,
        )


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
            uploaded_at=doc.uploaded_at,
            indexed_at=doc.indexed_at,
        )


@router.get("/{document_id}/status", response_model=DocumentStatus)
async def get_document_status(document_id: int):
    """Poll document ingestion status (alias for GET /{id})."""
    return await get_document(document_id)


@router.get("/{document_id}/debug", response_model=DocumentDebugInfo)
async def get_document_debug(document_id: int):
    """Get detailed debug/analytics info for a document (indexing timings, token stats, RAG usage)."""
    async with async_session() as session:
        result = await session.execute(
            select(
                Document.id.label("document_id"),
                Document.title,
                Document.original_filename,
                Document.format,
                Document.status,
                Document.source_hash,
                Document.file_size_bytes,
                Document.uploaded_at,
                Document.indexed_at,
                Document.ingest_duration_ms,
                Document.read_ms,
                Document.convert_ms,
                Document.parse_ms,
                Document.embed_ms,
                Document.db_ms,
                Document.total_chunks,
                Document.total_tokens,
                Document.min_chunk_tokens,
                Document.max_chunk_tokens,
                Document.avg_chunk_tokens,
                Document.embedding_model,
                Document.embedding_dims,
                Document.embedding_tokens,
                Document.rag_hit_count,
                Document.rag_avg_similarity,
                Document.rag_last_used_at,
                Document.ocr_ms,
                Document.ocr_images_total,
                Document.ocr_images_success,
                Document.ocr_images_empty,
                Document.ocr_images_failed,
                Document.detected_language,
                Product.name.label("product_name"),
                FirmwareVersion.version.label("firmware_version"),
            )
            .join(Product, Document.product_id == Product.id)
            .join(FirmwareVersion, Document.firmware_version_id == FirmwareVersion.id)
            .where(Document.id == document_id)
        )
        row = result.one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Document not found")
        return DocumentDebugInfo(**dict(row._mapping))


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


@router.post("/{document_id}/cancel", status_code=200)
async def cancel_document(document_id: int):
    """Cancel ingestion of a pending or processing document.

    Sets status to 'cancelled', revokes the Celery task, and cleans up any partial chunks.
    """
    async with async_session() as session:
        doc = await session.get(Document, document_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found")

        if doc.status not in ("pending", "processing"):
            raise HTTPException(status_code=400, detail=f"Cannot cancel document with status '{doc.status}'")

        celery_task_id = doc.celery_task_id

        doc.status = "cancelled"
        doc.progress_percent = 0
        doc.progress_stage = ""
        doc.error_message = None

        chunks = (await session.execute(
            select(Chunk).where(Chunk.document_id == doc.id)
        )).scalars().all()
        for chunk in chunks:
            await session.delete(chunk)
        doc.total_chunks = 0

        await session.commit()

    if celery_task_id:
        try:
            from app.celery_app import celery
            celery.control.revoke(celery_task_id, terminate=True)
        except Exception:
            logger.warning("Failed to revoke Celery task", extra={"task_id": celery_task_id, "document_id": document_id})

    logger.info("Document ingestion cancelled", extra={"document_id": document_id, "celery_task_id": celery_task_id})
    return {"document_id": document_id, "status": "cancelled", "message": "Ingestion cancelled"}


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


@router.post("/{document_id}/reingest", status_code=202)
async def reingest_single_document(document_id: int):
    """Re-run full ingestion for a single document.

    Resets the document to 'pending', clears existing chunks, and queues
    a new Celery ingestion task. The original file in S3 is preserved.
    """
    from app.celery_app import ingest_document_task

    async with async_session() as session:
        doc = await session.get(Document, document_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found")

        if not doc.s3_key:
            raise HTTPException(status_code=400, detail="No source file stored — cannot reingest")

        chunks = (await session.execute(
            select(Chunk).where(Chunk.document_id == doc.id)
        )).scalars().all()
        for chunk in chunks:
            await session.delete(chunk)

        doc.status = "pending"
        doc.total_chunks = 0
        doc.error_message = None
        doc.progress_percent = 0
        doc.progress_stage = ""
        await session.flush()

        task = ingest_document_task.delay(document_id)
        doc.celery_task_id = task.id
        await session.commit()

    logger.info("Single document reingest queued", extra={
        "document_id": document_id, "task_id": task.id,
    })
    return {
        "document_id": document_id,
        "status": "pending",
        "task_id": task.id,
        "message": "Document queued for reingestion",
    }


@router.get("/queue-stats")
async def get_queue_stats():
    """Current queue state from DB (pending/processing counts). For dashboards and monitoring."""
    async with async_session() as session:
        result = await session.execute(
            select(Document.status, func.count())
            .where(Document.status.in_(["pending", "processing", "ready"]))
            .group_by(Document.status)
        )
        rows = result.all()

    counts = {status: cnt for status, cnt in rows}
    return {
        "pending": counts.get("pending", 0),
        "processing": counts.get("processing", 0),
        "ready": counts.get("ready", 0),
        "total_queued": counts.get("pending", 0) + counts.get("processing", 0),
    }


@router.post("/requeue-pending", status_code=202)
async def requeue_pending_documents():
    """Re-queue ingestion for all documents with status 'pending'.

    Use when tasks were lost (e.g. worker crash) and pending documents never processed.
    """
    from app.celery_app import ingest_document_task

    async with async_session() as session:
        result = await session.execute(
            select(Document).where(Document.status == "pending")
        )
        pending = result.scalars().all()

    queued = 0
    for doc in pending:
        ingest_document_task.delay(doc.id)
        queued += 1

    logger.info("Requeued pending documents", extra={"count": queued, "document_ids": [d.id for d in pending[:10]]})
    return {"status": "accepted", "documents_queued": queued}


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


@router.post("/reingest", status_code=202)
async def reingest_documents(
    product_name: str = Form(default=""),
    format_filter: str = Form(default=""),
):
    """Re-run full ingestion (convert + parse + chunk + embed) for existing documents.

    Resets matching documents to 'pending' and queues them for Celery processing.
    Useful after fixing converters (e.g. proto filename bug).

    Filters (all optional, combined with AND):
        product_name: Only reingest documents for this product.
        format_filter: Only reingest documents with this format (e.g. "proto").
    """
    from app.celery_app import ingest_document_task

    async with async_session() as session:
        query = select(Document).where(Document.status == "ready")

        if product_name:
            product_result = await session.execute(
                select(Product).where(Product.name == product_name)
            )
            product = product_result.scalar_one_or_none()
            if product is None:
                raise HTTPException(status_code=404, detail=f"Product '{product_name}' not found")
            query = query.where(Document.product_id == product.id)

        if format_filter:
            query = query.where(Document.format == format_filter)

        docs_result = await session.execute(query)
        docs = docs_result.scalars().all()

        queued = 0
        for doc in docs:
            doc.status = "pending"
            queued += 1

        await session.commit()

    for doc in docs:
        ingest_document_task.delay(doc.id)

    logger.info(
        "Reingest queued",
        extra={"product_name": product_name, "format_filter": format_filter, "documents_queued": queued},
    )
    return {
        "status": "accepted",
        "documents_queued": queued,
        "product_name": product_name or "(all)",
        "format_filter": format_filter or "(all)",
    }


async def _find_by_hash(session, source_hash: str) -> Document | None:
    """Find an existing document with the same content hash."""
    result = await session.execute(
        select(Document).where(Document.source_hash == source_hash).limit(1)
    )
    return result.scalar_one_or_none()


async def _get_or_create_product(session, name: str, manufacturer: str):
    from app.slugify import slugify

    result = await session.execute(select(Product).where(Product.name == name))
    product = result.scalar_one_or_none()
    if product:
        if not product.slug:
            product.slug = slugify(name)
            product.manufacturer_slug = slugify(manufacturer) if manufacturer else "default"
            await session.flush()
        return product
    product = Product(
        name=name,
        manufacturer=manufacturer,
        slug=slugify(name),
        manufacturer_slug=slugify(manufacturer) if manufacturer else "default",
    )
    session.add(product)
    await session.flush()
    return product


async def _get_or_create_firmware(session, product_id: int, version: str):
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
