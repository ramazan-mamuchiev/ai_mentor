"""REST API router for document ingestion and management."""

import hashlib
import logging
import os
import time

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import func, select

from app.auth.dependencies import get_current_tenant, require_permission
from app.database import async_session
from app.documents.schemas import (
    ArchiveFileResult,
    ArchiveIngestResponse,
    DeleteResponse,
    DocumentDebugInfo,
    DocumentDownload,
    DocumentListItem,
    DocumentMarkdownPreview,
    DocumentSearchKeysResponse,
    DocumentStatus,
    DocumentUsageEntry,
    DocumentUsageStats,
    GitHubIngestRequest,
    IngestResponse,
    SearchKeyItem,
    SiteIngestRequest,
    UrlIngestRequest,
    UrlIngestResponse,
)
from app.models import ChatMessage, Chunk, DocumentUsageLog, Product, Document, FirmwareVersion, ProductSearchKey, Tenant
from app.s3 import delete_file, generate_presigned_url, s3_key_for_document, upload_file
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

ALLOWED_EXTENSIONS = {".md", ".json", ".yaml", ".yml", ".pdf", ".proto", ".txt", ".wsdl", ".xml"}
MAX_UPLOAD_BYTES = settings.max_upload_size_mb * 1024 * 1024


@router.post("/ingest", response_model=IngestResponse, dependencies=[Depends(require_permission("documents.upload"))])
async def ingest_document(
    request: Request,
    file: UploadFile = File(...),
    product_name: str = Form(...),
    firmware_version: str = Form(default="1.0"),
    manufacturer: str = Form(default=""),
    format: str = Form(default="auto"),
    force: bool = Form(default=False),
    tenant: Tenant = Depends(get_current_tenant),
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
        product = await _get_or_create_product(session, product_name, manufacturer, tenant_id=tenant.id)
        fw = await _get_or_create_firmware(session, product.id, firmware_version)

        if not force:
            existing = await _find_by_hash(session, source_hash, product.id, fw.id)
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

        doc = Document(
            product_id=product.id,
            firmware_version_id=fw.id,
            format=format,
            original_filename=original_filename,
            file_size_bytes=file_size,
            title=os.path.splitext(original_filename)[0],
            status="pending",
            source_hash=source_hash,
            tenant_id=tenant.id,
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


@router.post("/ingest-url", response_model=UrlIngestResponse, dependencies=[Depends(require_permission("documents.upload"))])
async def ingest_url(request: Request, body: UrlIngestRequest, tenant: Tenant = Depends(get_current_tenant)):
    """Import documentation from a web URL.

    Creates Product + FirmwareVersion + Document placeholder synchronously,
    then dispatches a Celery task for background crawl/ingestion.
    The placeholder tracks overall progress visible to the frontend via polling.
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

    doc_format = "confluence" if is_confluence else "url"

    async with async_session() as session:
        product = await _get_or_create_product(session, body.product_name, body.manufacturer, tenant_id=tenant.id)
        fw = await _get_or_create_firmware(session, product.id, body.firmware_version)

        crawl_checkpoint = None
        if is_confluence and body.confluence_username and body.confluence_password:
            from app.utils.crypto import encrypt_credentials
            encrypted = encrypt_credentials(body.confluence_username, body.confluence_password)
            if encrypted:
                crawl_checkpoint = {"auth": encrypted}
        elif not is_confluence and body.http_username and body.http_password:
            from app.utils.crypto import encrypt_credentials
            encrypted = encrypt_credentials(body.http_username, body.http_password)
            if encrypted:
                crawl_checkpoint = {"http_auth": encrypted}

        placeholder = Document(
            product_id=product.id,
            firmware_version_id=fw.id,
            format=doc_format,
            original_filename=url[:200],
            title=url[:200],
            status="pending",
            source_path=url,
            source_container=url,
            progress_stage="queued",
            tenant_id=tenant.id,
            crawl_checkpoint=crawl_checkpoint,
        )
        session.add(placeholder)
        await session.flush()

        try:
            if is_confluence:
                from app.celery_app import ingest_confluence_task
                task = ingest_confluence_task.delay(
                    document_id=placeholder.id,
                    max_pages=body.max_pages,
                    max_depth=body.max_depth,
                )
            else:
                from app.celery_app import ingest_single_url_task
                task = ingest_single_url_task.delay(document_id=placeholder.id)

            placeholder.celery_task_id = task.id
            await session.commit()

            logger.info("URL ingest task queued", extra={
                "url": url, "task_id": task.id, "document_id": placeholder.id,
                "product_id": product.id, "is_confluence": is_confluence,
                "client_ip": client_ip,
            })

            return UrlIngestResponse(
                status="pending",
                message="Confluence documentation crawl queued" if is_confluence else "Web page queued for processing",
                url=url,
                product_name=body.product_name,
                task_id=task.id,
                product_id=product.id,
                document_id=placeholder.id,
            )
        except Exception as exc:
            await session.rollback()
            logger.error("Failed to queue URL ingest task", extra={
                "url": url, "error_type": type(exc).__name__, "error": str(exc),
            }, exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to queue task: {type(exc).__name__}: {exc}")


@router.post("/ingest-site", response_model=UrlIngestResponse, dependencies=[Depends(require_permission("documents.upload"))])
async def ingest_site(request: Request, body: SiteIngestRequest, tenant: Tenant = Depends(get_current_tenant)):
    """Crawl an entire website and ingest all pages + downloadable files.

    Creates a placeholder Document (format='site') and dispatches a Celery task
    that BFS-crawls the site within the same domain.
    """
    url = body.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    client_ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown")

    logger.info("Site ingest request received", extra={
        "url": url,
        "product_name": body.product_name,
        "max_depth": body.max_depth,
        "max_pages": body.max_pages,
        "client_ip": client_ip,
    })

    async with async_session() as session:
        product = await _get_or_create_product(session, body.product_name, body.manufacturer, tenant_id=tenant.id)
        fw = await _get_or_create_firmware(session, product.id, body.firmware_version)

        from urllib.parse import urlparse as _urlparse
        domain = _urlparse(url).netloc

        placeholder = Document(
            product_id=product.id,
            firmware_version_id=fw.id,
            format="site",
            original_filename=url[:200],
            title=f"Site: {domain}",
            status="pending",
            source_path=url,
            source_container=url,
            progress_stage="queued",
            tenant_id=tenant.id,
        )
        session.add(placeholder)
        await session.flush()

        try:
            from app.celery_app import ingest_site_task
            task = ingest_site_task.delay(
                document_id=placeholder.id,
                max_depth=body.max_depth,
                max_pages=body.max_pages,
                download_resources=body.download_resources,
            )

            placeholder.celery_task_id = task.id
            await session.commit()

            logger.info("Site ingest task queued", extra={
                "url": url, "task_id": task.id, "document_id": placeholder.id,
                "product_id": product.id, "max_depth": body.max_depth,
                "max_pages": body.max_pages, "client_ip": client_ip,
            })

            return UrlIngestResponse(
                status="pending",
                message=f"Site crawl queued for {domain}",
                url=url,
                product_name=body.product_name,
                task_id=task.id,
                product_id=product.id,
                document_id=placeholder.id,
            )
        except Exception as exc:
            await session.rollback()
            logger.error("Failed to queue site ingest task", extra={
                "url": url, "error_type": type(exc).__name__, "error": str(exc),
            }, exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to queue task: {type(exc).__name__}: {exc}")


@router.post("/ingest-github", response_model=UrlIngestResponse, dependencies=[Depends(require_permission("documents.upload"))])
async def ingest_github(request: Request, body: GitHubIngestRequest, tenant: Tenant = Depends(get_current_tenant)):
    """Import documentation files from a public GitHub repository.

    Creates a placeholder Document (format='github') and dispatches a Celery task
    that fetches the repo tree via GitHub API and imports matching files.
    """
    from app.ingestion.converters.github import parse_github_url

    url = body.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    try:
        owner, repo, url_branch = parse_github_url(url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    branch = url_branch or body.branch or "main"

    client_ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown")

    logger.info("GitHub ingest request received", extra={
        "url": url, "owner": owner, "repo": repo, "branch": branch,
        "product_name": body.product_name, "client_ip": client_ip,
    })

    async with async_session() as session:
        product = await _get_or_create_product(session, body.product_name, body.manufacturer, tenant_id=tenant.id)
        fw = await _get_or_create_firmware(session, product.id, body.firmware_version)

        placeholder = Document(
            product_id=product.id,
            firmware_version_id=fw.id,
            format="github",
            original_filename=url[:200],
            title=f"GitHub: {owner}/{repo}",
            status="pending",
            source_path=url,
            source_container=url,
            progress_stage="queued",
            tenant_id=tenant.id,
        )
        session.add(placeholder)
        await session.flush()

        try:
            from app.celery_app import ingest_github_task
            task = ingest_github_task.delay(
                document_id=placeholder.id,
                branch=branch,
            )

            placeholder.celery_task_id = task.id
            await session.commit()

            logger.info("GitHub ingest task queued", extra={
                "url": url, "task_id": task.id, "document_id": placeholder.id,
                "owner": owner, "repo": repo, "branch": branch,
                "product_id": product.id, "client_ip": client_ip,
            })

            return UrlIngestResponse(
                status="pending",
                message=f"GitHub import queued for {owner}/{repo} ({branch})",
                url=url,
                product_name=body.product_name,
                task_id=task.id,
                product_id=product.id,
                document_id=placeholder.id,
            )
        except Exception as exc:
            await session.rollback()
            logger.error("Failed to queue GitHub ingest task", extra={
                "url": url, "error_type": type(exc).__name__, "error": str(exc),
            }, exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to queue task: {type(exc).__name__}: {exc}")


from app.documents.archive import (
    ARCHIVE_ALLOWED_EXTENSIONS,
    SUPPORTED_ARCHIVE_EXTENSIONS,
    _archive_ext,
    extract_archive,
)

MAX_ARCHIVE_BYTES = settings.max_archive_size_mb * 1024 * 1024


async def _create_proto_bundle_docs_async(
    session,
    proto_entries: list[tuple[str, bytes]],
    *,
    product_id: int,
    firmware_version_id: int,
    archive_filename: str,
    tenant_id=None,
    force: bool = False,
) -> list[int]:
    """Async version of proto bundle creation for FastAPI endpoint."""
    from app.ingestion.converters.proto import convert_proto_bundle

    files = []
    for arc_path, data in proto_entries:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        files.append((arc_path.replace("\\", "/"), text))

    bundles = convert_proto_bundle(files)

    doc_ids: list[int] = []
    for domain_name, source_folder, markdown, meta in bundles:
        md_bytes = markdown.encode("utf-8")
        md_hash = hashlib.sha256(md_bytes).hexdigest()

        if not force:
            existing = await _find_by_hash(session, md_hash)
            if existing is not None:
                continue

        title = f"gRPC API: {domain_name}"
        filename = f"{domain_name}.md"

        doc = Document(
            product_id=product_id,
            firmware_version_id=firmware_version_id,
            format="markdown",
            original_filename=filename,
            file_size_bytes=len(md_bytes),
            title=title,
            status="pending",
            source_hash=md_hash,
            source_container=archive_filename,
            source_folder=source_folder,
            tenant_id=tenant_id,
        )
        session.add(doc)
        await session.flush()

        s3_key = s3_key_for_document(doc.id, filename)
        upload_file(s3_key, md_bytes, "text/markdown")
        doc.s3_key = s3_key
        await session.commit()

        doc_ids.append(doc.id)

    return doc_ids


@router.post("/ingest-archive", response_model=ArchiveIngestResponse, dependencies=[Depends(require_permission("documents.upload"))])
async def ingest_archive(
    request: Request,
    file: UploadFile = File(...),
    product_name: str = Form(...),
    firmware_version: str = Form(default="1.0"),
    manufacturer: str = Form(default=""),
    force: bool = Form(default=False),
    tenant: Tenant = Depends(get_current_tenant),
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

    from app.documents.archive import is_proto_heavy, classify_archive_entries

    results: list[ArchiveFileResult] = []
    accepted = 0
    skipped = 0
    errors = 0

    async with async_session() as session:
        product = await _get_or_create_product(session, product_name, manufacturer, tenant_id=tenant.id)
        fw = await _get_or_create_firmware(session, product.id, firmware_version)

        proto_entries, other_entries = classify_archive_entries(entries)
        use_bundle = is_proto_heavy(entries) and len(proto_entries) >= 5

        if use_bundle:
            bundle_ids = await _create_proto_bundle_docs_async(
                session, proto_entries,
                product_id=product.id,
                firmware_version_id=fw.id,
                archive_filename=original_filename,
                tenant_id=tenant.id,
                force=force,
            )
            for doc_id in bundle_ids:
                from app.celery_app import ingest_document_task
                task = ingest_document_task.delay(doc_id)
                accepted += 1
                results.append(ArchiveFileResult(
                    filename=f"[proto-bundle-{doc_id}]",
                    status="pending",
                    document_id=doc_id,
                    task_id=task.id,
                    message="Proto bundle queued for processing",
                ))
            remaining_entries = other_entries
        else:
            remaining_entries = entries

        for arc_path, entry_data in remaining_entries:
            entry_filename = os.path.basename(arc_path)
            entry_folder = os.path.dirname(arc_path).replace("\\", "/")

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
                    source_folder=entry_folder,
                    tenant_id=tenant.id,
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
    import orjson
    from starlette.responses import Response

    async with async_session() as session:
        _base_cols = [
            Document.id,
            Document.title,
            Document.format,
            Document.status,
            Document.original_filename,
            Document.file_size_bytes,
            Document.total_chunks,
            Document.error_message,
            Document.uploaded_at,
            Document.indexed_at,
            Document.progress_percent,
            Document.progress_stage,
            Document.detected_language,
            Document.source_container,
            Document.source_path,
            Document.lifecycle_status,
        ]

        if product_id is not None:
            query = (
                select(*_base_cols)
                .where(Document.product_id == product_id)
                .order_by(Document.uploaded_at.desc())
            )
        else:
            query = (
                select(
                    *_base_cols,
                    Product.name.label("product_name"),
                    FirmwareVersion.version.label("firmware_version"),
                )
                .join(Product, Document.product_id == Product.id)
                .join(FirmwareVersion, Document.firmware_version_id == FirmwareVersion.id)
                .order_by(Document.uploaded_at.desc())
            )

        result = await session.execute(query)
        rows = result.all()
        items = [dict(row._mapping) for row in rows]
        return Response(
            content=orjson.dumps(items, option=orjson.OPT_NAIVE_UTC),
            media_type="application/json",
        )


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


@router.get("/{document_id}/debug", response_model=DocumentDebugInfo, dependencies=[Depends(require_permission("debug"))])
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
                Document.error_message,
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
                Document.ocr_prompt_tokens,
                Document.ocr_completion_tokens,
                Document.ocr_model,
                Document.detected_language,
                Document.extract_ms,
                Document.extract_prompt_tokens,
                Document.extract_completion_tokens,
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
        data = dict(row._mapping)
        if data.get("extract_ms") is not None:
            from app.config import settings as _cfg
            data["extract_model"] = _cfg.metadata_extraction_model

        keys_count = (await session.execute(
            select(func.count()).select_from(ProductSearchKey)
            .where(ProductSearchKey.document_id == document_id)
        )).scalar() or 0
        data["search_keys_count"] = keys_count

        return DocumentDebugInfo(**data)


@router.get("/{document_id}/search-keys", response_model=DocumentSearchKeysResponse)
async def get_document_search_keys(document_id: int):
    """Get all search keys associated with a document."""
    async with async_session() as session:
        doc = await session.get(Document, document_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found")

        rows = (await session.execute(
            select(ProductSearchKey.key, ProductSearchKey.source)
            .where(ProductSearchKey.document_id == document_id)
            .order_by(ProductSearchKey.source, ProductSearchKey.key)
        )).all()

        keys = [SearchKeyItem(key=r.key, source=r.source) for r in rows]
        return DocumentSearchKeysResponse(
            document_id=document_id,
            total_keys=len(keys),
            keys=keys,
        )


@router.get("/{document_id}/usage-stats", response_model=DocumentUsageStats)
async def get_document_usage_stats(document_id: int, limit: int = 20):
    """Get detailed usage analytics for a document from document_usage_log."""
    async with async_session() as session:
        doc = await session.get(Document, document_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found")

        agg_result = await session.execute(
            select(
                func.count().label("total_usages"),
                func.count(func.distinct(DocumentUsageLog.session_id)).label("unique_sessions"),
                func.sum(DocumentUsageLog.context_tokens).label("total_context_tokens"),
                func.sum(DocumentUsageLog.charge_usd).label("total_charge_usd"),
                func.avg(DocumentUsageLog.similarity).label("avg_similarity"),
                func.min(DocumentUsageLog.created_at).label("first_used_at"),
                func.max(DocumentUsageLog.created_at).label("last_used_at"),
            ).where(DocumentUsageLog.document_id == document_id)
        )
        agg = agg_result.one()

        fb_result = await session.execute(
            select(
                func.count().filter(ChatMessage.feedback == "up").label("thumbs_up"),
                func.count().filter(ChatMessage.feedback == "down").label("thumbs_down"),
                func.count(func.distinct(ChatMessage.id)).filter(
                    ChatMessage.feedback.is_not(None)
                ).label("total_rated"),
            )
            .select_from(DocumentUsageLog)
            .join(ChatMessage, ChatMessage.id == DocumentUsageLog.message_id)
            .where(DocumentUsageLog.document_id == document_id)
        )
        fb = fb_result.one()

        heading_result = await session.execute(
            select(
                DocumentUsageLog.heading_path,
                func.count().label("cnt"),
            )
            .where(DocumentUsageLog.document_id == document_id)
            .group_by(DocumentUsageLog.heading_path)
            .order_by(func.count().desc())
            .limit(10)
        )
        top_headings = [
            {"heading_path": row.heading_path, "count": row.cnt}
            for row in heading_result.all()
        ]

        recent_result = await session.execute(
            select(DocumentUsageLog)
            .where(DocumentUsageLog.document_id == document_id)
            .order_by(DocumentUsageLog.created_at.desc())
            .limit(limit)
        )
        recent = [
            DocumentUsageEntry(
                created_at=r.created_at,
                session_id=r.session_id,
                message_id=r.message_id,
                heading_path=r.heading_path,
                similarity=r.similarity,
                context_tokens=r.context_tokens,
                query_text=r.query_text,
                query_type=r.query_type,
                sub_query=r.sub_query,
                charge_usd=float(r.charge_usd),
            )
            for r in recent_result.scalars().all()
        ]

        return DocumentUsageStats(
            document_id=document_id,
            title=doc.title,
            total_usages=agg.total_usages or 0,
            unique_sessions=agg.unique_sessions or 0,
            total_context_tokens=agg.total_context_tokens or 0,
            total_charge_usd=float(agg.total_charge_usd or 0),
            avg_similarity=float(agg.avg_similarity) if agg.avg_similarity else None,
            first_used_at=agg.first_used_at,
            last_used_at=agg.last_used_at,
            thumbs_up=fb.thumbs_up or 0,
            thumbs_down=fb.thumbs_down or 0,
            total_rated=fb.total_rated or 0,
            top_headings=top_headings,
            recent_usages=recent,
        )


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


@router.get("/{document_id}/preview-markdown", response_model=DocumentMarkdownPreview)
async def preview_markdown(document_id: int):
    """Get the converted Markdown content for a document.

    Priority: converted_s3_key (full MD before chunking) > s3_key for .md files >
    reconstruct from chunks as fallback.
    """
    from app.s3 import download_file as s3_download

    async with async_session() as session:
        doc = await session.get(Document, document_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found")
        if doc.status != "ready":
            raise HTTPException(status_code=400, detail=f"Document is not ready (status: {doc.status})")

        md_text: str | None = None
        source = "unknown"

        if doc.converted_s3_key:
            try:
                data = s3_download(doc.converted_s3_key)
                md_text = data.decode("utf-8", errors="replace")
                source = "s3_converted"
            except Exception:
                logger.warning("Failed to download converted MD from S3", extra={
                    "document_id": document_id, "key": doc.converted_s3_key,
                })

        if md_text is None and doc.s3_key:
            ext = os.path.splitext(doc.s3_key)[1].lower()
            if ext in (".md", ".txt"):
                try:
                    data = s3_download(doc.s3_key)
                    md_text = data.decode("utf-8", errors="replace")
                    source = "s3_original"
                except Exception:
                    logger.warning("Failed to download original MD from S3", extra={
                        "document_id": document_id, "key": doc.s3_key,
                    })

        if md_text is None:
            chunks = (await session.execute(
                select(Chunk)
                .where(Chunk.document_id == document_id)
                .order_by(Chunk.chunk_index)
            )).scalars().all()
            if not chunks:
                raise HTTPException(status_code=404, detail="No markdown content available")
            md_text = "\n\n".join(c.content for c in chunks)
            source = "chunks_reconstructed"

        return DocumentMarkdownPreview(
            document_id=doc.id,
            title=doc.title,
            markdown=md_text,
            size_bytes=len(md_text.encode("utf-8")),
            source=source,
        )


@router.post("/{document_id}/analyze-lifecycle", status_code=202, dependencies=[Depends(require_permission("debug"))])
async def analyze_document_lifecycle(document_id: int):
    """Manually trigger API lifecycle analysis for a document.

    Dispatches an async Celery task. Returns immediately with task info.
    """
    from app.models import ApiLifecycle
    async with async_session() as session:
        doc = (await session.execute(
            select(Document).where(Document.id == document_id)
        )).scalar_one_or_none()
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found")
        if doc.status != "ready":
            raise HTTPException(status_code=409, detail=f"Document status is '{doc.status}', must be 'ready'")

        existing = (await session.execute(
            select(ApiLifecycle.status).where(ApiLifecycle.document_id == document_id)
        )).scalar_one_or_none()

        doc.lifecycle_status = "pending"
        await session.commit()

    from app.celery_app import celery
    task = celery.send_task("analyze_api_lifecycle", args=[document_id])

    return {
        "document_id": document_id,
        "task_id": task.id,
        "message": "Lifecycle analysis started",
        "previous_status": existing or "none",
    }


@router.get("/{document_id}/lifecycle")
async def get_document_lifecycle(document_id: int):
    """Get lifecycle analysis result for a document."""
    from app.models import ApiLifecycle, DocIssueAnnotation
    async with async_session() as session:
        doc = (await session.execute(
            select(Document).where(Document.id == document_id)
        )).scalar_one_or_none()
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found")

        lc = (await session.execute(
            select(ApiLifecycle).where(ApiLifecycle.document_id == document_id)
        )).scalar_one_or_none()
        if lc is None:
            return {"document_id": document_id, "status": "not_analyzed"}

        issues = (await session.execute(
            select(DocIssueAnnotation).where(
                DocIssueAnnotation.document_id == document_id,
                DocIssueAnnotation.detected_by == "lifecycle_analysis",
            )
        )).scalars().all()

        return {
            "document_id": document_id,
            "status": lc.status,
            "phases": lc.phases,
            "unique_patterns": lc.unique_patterns,
            "dependency_chains": lc.dependency_chains,
            "code_skeleton": lc.code_skeleton,
            "data_models": lc.data_models or [],
            "error_catalog": lc.error_catalog or [],
            "prerequisites": lc.prerequisites or [],
            "data_access_patterns": lc.data_access_patterns or [],
            "endpoint_coverage": lc.endpoint_coverage or [],
            "validation_issues": lc.validation_issues,
            "validation_retries": lc.validation_retries,
            "prompt_tokens": lc.prompt_tokens,
            "completion_tokens": lc.completion_tokens,
            "analysis_ms": lc.analysis_ms,
            "model": lc.model,
            "error_message": lc.error_message,
            "created_at": lc.created_at.isoformat() if lc.created_at else None,
            "updated_at": lc.updated_at.isoformat() if lc.updated_at else None,
            "doc_issues": [
                {
                    "issue_type": i.issue_type,
                    "severity": i.severity,
                    "description": i.description,
                    "affected_entity": i.affected_entity,
                    "suggestion": i.suggestion,
                }
                for i in issues
            ],
        }


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


@router.delete("/{document_id}", response_model=DeleteResponse, dependencies=[Depends(require_permission("documents.delete"))])
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


@router.post("/{document_id}/reingest", status_code=202, dependencies=[Depends(require_permission("documents.reindex"))])
async def reingest_single_document(
    document_id: int,
    reindex_only: bool = False,
):
    """Re-run ingestion for a single document.

    reindex_only=False (default / "sync"): for linked documents re-crawls
    from source; for file-based documents re-indexes from stored S3 file.

    reindex_only=True ("reindex"): always re-indexes from the stored S3
    file without going to the external source. Returns 400 for placeholder
    documents that have no stored content.
    """
    from app.celery_app import ingest_document_task

    _PLACEHOLDER_FORMATS = {"site", "confluence", "url", "github"}

    async with async_session() as session:
        doc = (await session.execute(
            select(Document).where(Document.id == document_id).with_for_update()
        )).scalar_one_or_none()
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found")

        if doc.status in ("pending", "processing"):
            raise HTTPException(status_code=409, detail="Document is already being processed")

        is_placeholder = doc.format in _PLACEHOLDER_FORMATS

        if reindex_only:
            if is_placeholder:
                raise HTTPException(
                    status_code=400,
                    detail="Placeholder document has no stored content — use sync instead",
                )
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
            doc.progress_stage = "queued"
            await session.flush()

            task = ingest_document_task.delay(document_id)
            doc.celery_task_id = task.id
            await session.commit()

            logger.info("Single document reindex queued", extra={
                "document_id": document_id, "task_id": task.id, "format": doc.format,
            })
            return {
                "document_id": document_id,
                "status": "pending",
                "task_id": task.id,
                "message": "Document queued for reindexing",
            }

        # --- Full sync: re-crawl from source for linked, re-index for files ---
        is_confluence = doc.format == "confluence"
        is_url = doc.format == "url"
        is_github = doc.format == "github"
        is_site = doc.format == "site"
        is_confluence_child = (
            doc.format == "markdown"
            and doc.source_path
            and doc.source_container
            and doc.source_path != doc.source_container
            and "confluence" in (doc.source_path or "").lower()
        )

        if is_url and doc.source_path:
            from app.ingestion.converters.confluence import parse_confluence_url
            try:
                parse_confluence_url(doc.source_path)
                is_confluence = True
                is_url = False
                doc.format = "confluence"
                logger.info("Reingest: reclassified URL as Confluence", extra={
                    "document_id": document_id, "url": doc.source_path,
                })
            except ValueError:
                pass

        if not doc.s3_key and not is_confluence and not is_url and not is_github and not is_site and not is_confluence_child:
            raise HTTPException(status_code=400, detail="No source file stored — cannot reingest")

        if is_confluence or is_url or is_github or is_site:
            if not doc.source_path:
                raise HTTPException(status_code=400, detail="No source URL stored — cannot reingest")

            source_url = doc.source_path

            children = (await session.execute(
                select(Document).where(
                    Document.source_container == source_url,
                    Document.id != doc.id,
                )
            )).scalars().all()
            for child in children:
                child_chunks = (await session.execute(
                    select(Chunk).where(Chunk.document_id == child.id)
                )).scalars().all()
                for ch in child_chunks:
                    await session.delete(ch)
                if child.s3_key:
                    try:
                        delete_file(child.s3_key)
                    except Exception:
                        pass
                await session.delete(child)

        chunks = (await session.execute(
            select(Chunk).where(Chunk.document_id == doc.id)
        )).scalars().all()
        for chunk in chunks:
            await session.delete(chunk)

        doc.status = "pending"
        doc.total_chunks = 0
        doc.total_tokens = 0
        doc.file_size_bytes = 0
        doc.error_message = None
        doc.progress_percent = 0
        doc.progress_stage = "queued"
        doc.title = doc.source_path[:200] if (is_confluence or is_url or is_github or is_site) else doc.title
        if is_site:
            doc.crawl_checkpoint = None
        await session.flush()

        if is_site:
            from app.celery_app import ingest_site_task
            task = ingest_site_task.delay(document_id=document_id)
        elif is_github:
            from app.celery_app import ingest_github_task
            from app.ingestion.converters.github import parse_github_url
            _branch = "main"
            try:
                _, _, url_branch = parse_github_url(doc.source_path)
                if url_branch:
                    _branch = url_branch
            except ValueError:
                pass
            task = ingest_github_task.delay(document_id=document_id, branch=_branch)
        elif is_confluence:
            from app.celery_app import ingest_confluence_task
            task = ingest_confluence_task.delay(document_id=document_id)
        elif is_url:
            from app.celery_app import ingest_single_url_task
            task = ingest_single_url_task.delay(document_id=document_id)
        elif is_confluence_child:
            from app.celery_app import reingest_confluence_page_task
            task = reingest_confluence_page_task.delay(document_id=document_id)
        else:
            task = ingest_document_task.delay(document_id)

        doc.celery_task_id = task.id
        await session.commit()

    logger.info("Single document sync queued", extra={
        "document_id": document_id, "task_id": task.id,
        "format": doc.format,
    })
    return {
        "document_id": document_id,
        "status": "pending",
        "task_id": task.id,
        "message": "Document queued for sync",
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


@router.post("/requeue-pending", status_code=202, dependencies=[Depends(require_permission("documents.reindex"))])
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


@router.post("/reindex", status_code=202, dependencies=[Depends(require_permission("documents.reindex"))])
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
            embeddings, _ = embed_texts(contents)

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


@router.post("/reingest", status_code=202, dependencies=[Depends(require_permission("documents.reindex"))])
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


async def _find_by_hash(
    session, source_hash: str, product_id: int, firmware_version_id: int
) -> Document | None:
    """Find an existing document with the same content hash within the same product+version."""
    result = await session.execute(
        select(Document).where(
            Document.source_hash == source_hash,
            Document.product_id == product_id,
            Document.firmware_version_id == firmware_version_id,
        ).limit(1)
    )
    return result.scalar_one_or_none()


async def _get_or_create_product(session, name: str, manufacturer: str, *, tenant_id=None):
    from sqlalchemy.exc import IntegrityError

    result = await session.execute(
        select(Product).where(Product.name == name, Product.manufacturer == manufacturer)
    )
    product = result.scalar_one_or_none()
    if product:
        return product

    from app.products.utils import make_product_slug

    product = Product(
        name=name,
        manufacturer=manufacturer,
        model=name,
        slug=make_product_slug(manufacturer, name),
        tenant_id=tenant_id,
    )
    session.add(product)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        result = await session.execute(
            select(Product).where(Product.name == name, Product.manufacturer == manufacturer)
        )
        product = result.scalar_one_or_none()
        if product is None:
            raise
    return product


async def _get_or_create_firmware(session, product_id: int, version: str):
    from sqlalchemy.exc import IntegrityError

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
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        result = await session.execute(
            select(FirmwareVersion).where(
                FirmwareVersion.product_id == product_id,
                FirmwareVersion.version == version,
            )
        )
        fw = result.scalar_one_or_none()
        if fw is None:
            raise
    return fw
