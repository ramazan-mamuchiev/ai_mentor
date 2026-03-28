"""Celery application for background document ingestion."""

import hashlib
import logging
import os
import tempfile
import time

from celery import Celery
from celery.exceptions import SoftTimeLimitExceeded
from celery.signals import (
    after_setup_logger,
    before_task_publish,
    task_prerun,
    task_postrun,
    task_failure,
    task_retry,
    worker_ready,
)
from sqlalchemy import create_engine, func, select as sa_select
from sqlalchemy.orm import Session

from app.config import settings
from app.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)
_signals_logger = logging.getLogger("celery.signals")


@after_setup_logger.connect
def _on_after_setup_logger(logger=None, **kw):
    """Re-apply our JSON logging after Celery replaces the root logger config."""
    setup_logging()

celery = Celery("lexiro", broker=settings.redis_url, backend=settings.redis_url)
celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    worker_hijack_root_logger=False,
    task_routes={
        "queue_status_snapshot": {"queue": "monitoring"},
        "cleanup_expired_uploads": {"queue": "monitoring"},
        "check_stale_reindex_jobs": {"queue": "monitoring"},
        "check_stale_documents": {"queue": "monitoring"},
        "ensure_usage_partitions": {"queue": "monitoring"},
        "cleanup_expired_shares": {"queue": "monitoring"},
        "s3_health_probe": {"queue": "monitoring"},
    },
    beat_schedule={
        "cleanup-expired-uploads": {
            "task": "cleanup_expired_uploads",
            "schedule": 3600.0,
        },
        "queue-status-snapshot": {
            "task": "queue_status_snapshot",
            "schedule": 30.0,
        },
        "check-stale-reindex-jobs": {
            "task": "check_stale_reindex_jobs",
            "schedule": 60.0,
        },
        "ensure-usage-partitions": {
            "task": "ensure_usage_partitions",
            "schedule": 86400.0,
        },
        "cleanup-expired-shares": {
            "task": "cleanup_expired_shares",
            "schedule": 86400.0,
        },
        "s3-health-probe": {
            "task": "s3_health_probe",
            "schedule": 60.0,
        },
        "check-stale-documents": {
            "task": "check_stale_documents",
            "schedule": 120.0,
        },
    },
)

_task_publish_times: dict[str, float] = {}


def _extract_document_id(args, kwargs):
    """Extract document_id from task args/kwargs."""
    if args:
        return args[0]
    if kwargs:
        return kwargs.get("document_id")
    return None


@before_task_publish.connect
def _on_before_task_publish(sender=None, headers=None, body=None, **kwargs):
    """Logged from the API container when a task is sent to the broker."""
    task_id = headers.get("id") if headers else None
    task_name = sender or "unknown"
    args = body[0] if body and isinstance(body, (list, tuple)) and body else []
    kw = body[1] if body and isinstance(body, (list, tuple)) and len(body) > 1 else {}
    doc_id = _extract_document_id(args, kw)

    if task_id:
        _task_publish_times[task_id] = time.time()

    extra = {"event": "Task queued", "task_name": task_name, "task_id": task_id}
    if doc_id is not None:
        extra["document_id"] = doc_id
    _signals_logger.info("Task queued", extra=extra)


@task_prerun.connect
def _on_task_prerun(sender=None, task_id=None, task=None, args=None, kwargs=None, **kw):
    """Logged from the worker container when a task starts executing."""
    task_name = sender.name if sender else "unknown"
    doc_id = _extract_document_id(args, kwargs)
    hostname = getattr(task.request, "hostname", None) if task else None

    queue_wait_ms = None
    publish_time = _task_publish_times.pop(task_id, None)
    if publish_time is not None:
        queue_wait_ms = round((time.time() - publish_time) * 1000, 1)

    extra = {
        "event": "Task picked from queue",
        "task_name": task_name,
        "task_id": task_id,
        "worker_hostname": hostname,
    }
    if doc_id is not None:
        extra["document_id"] = doc_id
    if queue_wait_ms is not None:
        extra["queue_wait_ms"] = queue_wait_ms
    _signals_logger.info("Task picked from queue", extra=extra)


@task_postrun.connect
def _on_task_postrun(sender=None, task_id=None, task=None, args=None, kwargs=None, state=None, retval=None, **kw):
    """Logged from the worker container when a task finishes (success or failure)."""
    task_name = sender.name if sender else "unknown"
    doc_id = _extract_document_id(args, kwargs)

    runtime_ms = None
    if task and hasattr(task.request, "time_start") and task.request.time_start:
        runtime_ms = round((time.monotonic() - task.request.time_start) * 1000, 1)

    extra = {
        "event": "Task completed",
        "task_name": task_name,
        "task_id": task_id,
        "state": state or "UNKNOWN",
    }
    if doc_id is not None:
        extra["document_id"] = doc_id
    if runtime_ms is not None:
        extra["runtime_ms"] = runtime_ms
    _signals_logger.info("Task completed", extra=extra)


@task_failure.connect
def _on_task_failure(sender=None, task_id=None, args=None, kwargs=None, exception=None, **kw):
    """Logged from the worker container when a task raises an unhandled exception."""
    task_name = sender.name if sender else "unknown"
    doc_id = _extract_document_id(args, kwargs)

    extra = {
        "event": "Task failed",
        "task_name": task_name,
        "task_id": task_id,
        "exception_type": type(exception).__name__ if exception else "Unknown",
    }
    if doc_id is not None:
        extra["document_id"] = doc_id
    _signals_logger.error("Task failed", extra=extra)


@task_retry.connect
def _on_task_retry(sender=None, request=None, reason=None, **kw):
    """Logged from the worker container when a task is retried."""
    task_name = sender.name if sender else "unknown"
    task_id = request.id if request else None
    retries = request.retries if request else 0
    args = request.args if request else None
    kwargs_r = request.kwargs if request else None
    doc_id = _extract_document_id(args, kwargs_r)

    extra = {
        "event": "Task retrying",
        "task_name": task_name,
        "task_id": task_id,
        "retry_number": retries,
        "reason": str(reason)[:500] if reason else None,
    }
    if doc_id is not None:
        extra["document_id"] = doc_id
    _signals_logger.warning("Task retrying", extra=extra)


@worker_ready.connect
def _on_worker_ready(sender=None, **kw):
    _signals_logger.info("Worker ready", extra={"event": "Worker ready"})

_sync_engine = None


def _get_sync_engine():
    global _sync_engine
    if _sync_engine is None:
        _sync_engine = create_engine(settings.database_url_sync, pool_size=8, max_overflow=4)
    return _sync_engine


def _set_tenant_log_context(tenant_id, session):
    """Populate structlog/logging context vars with tenant info for Celery tasks."""
    from app.logging_config import tenant_id_ctx, tenant_name_ctx
    if not tenant_id:
        return
    from app.models import Tenant
    tenant_id_ctx.set(str(tenant_id))
    tenant = session.get(Tenant, tenant_id)
    tenant_name_ctx.set(tenant.name if tenant and tenant.name else "-")


@celery.task(name="ingest_document", bind=True, max_retries=2, default_retry_delay=30,
             soft_time_limit=2700, time_limit=3000)
def ingest_document_task(self, document_id: int):
    """Background task: download file from S3, run ingestion pipeline, update DB."""
    from app.models import Base, Chunk, Product, Document, FirmwareVersion
    from app.s3 import download_file_to_path
    from app.ingestion.pipeline import ingest_from_bytes, _update_progress, IngestionCancelled

    t0 = time.perf_counter()
    logger.info("Celery ingest_document_task started", extra={"document_id": document_id, "task_id": self.request.id})

    engine = _get_sync_engine()

    with Session(engine) as session:
        doc = session.get(Document, document_id)
        if doc is None:
            logger.error("Document not found", extra={"document_id": document_id})
            return {"status": "error", "error": "Document not found"}

        if doc.status == "ready":
            logger.warning("Document already processed", extra={"document_id": document_id})
            return {"status": "skipped", "message": "Already processed"}

        if doc.status == "cancelled":
            logger.info("Document was cancelled before task started", extra={"document_id": document_id})
            return {"status": "cancelled", "message": "Cancelled before processing"}

        _set_tenant_log_context(doc.tenant_id, session)

        from datetime import datetime, timezone as _tz
        doc.status = "processing"
        doc.processing_started_at = datetime.now(_tz.utc)
        doc.celery_task_id = self.request.id
        session.commit()

        ext = os.path.splitext(doc.original_filename)[1].lower() or ".bin"
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp_path = tmp.name

            _update_progress(session, doc, 0, "preparing")

            def _download_progress(frac: float) -> None:
                _update_progress(session, doc, max(1, int(frac * 5)), "preparing")

            try:
                download_file_to_path(doc.s3_key, tmp_path, progress_callback=_download_progress)
            except SoftTimeLimitExceeded:
                raise
            except Exception as exc:
                doc.status = "error"
                doc.error_message = f"S3 download failed: {exc}"
                doc.progress_percent = 0
                doc.progress_stage = ""
                session.commit()
                logger.error("S3 download failed", extra={"document_id": document_id, "s3_key": doc.s3_key, "error_type": type(exc).__name__}, exc_info=True)
                raise self.retry(exc=exc)

            result = ingest_from_bytes(
                session=session,
                document=doc,
                file_path=tmp_path,
                original_filename=doc.original_filename,
            )

            duration_ms = round((time.perf_counter() - t0) * 1000, 1)
            logger.info(
                "Celery ingest_document_task completed",
                extra={
                    "document_id": document_id,
                    "task_id": self.request.id,
                    "status": result["status"],
                    "chunks": result.get("chunks", 0),
                    "duration_ms": duration_ms,
                },
            )
            return result

        except IngestionCancelled:
            logger.info("Ingestion cancelled mid-flight", extra={"document_id": document_id, "task_id": self.request.id})
            return {"status": "cancelled", "document_id": document_id}

        except SoftTimeLimitExceeded:
            doc.status = "error"
            doc.error_message = "Task exceeded soft time limit (45 min)"
            session.commit()
            logger.error("ingest_document_task soft time limit exceeded",
                         extra={"document_id": document_id})
            return {"status": "error", "error": "soft_time_limit", "document_id": document_id}

        except Exception as exc:
            doc.status = "error"
            doc.error_message = str(exc)[:2000]
            session.commit()
            logger.error(
                "Celery ingest_document_task failed",
                extra={"document_id": document_id, "error_type": type(exc).__name__},
                exc_info=True,
            )
            raise self.retry(exc=exc)

        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)


@celery.task(name="ingest_archive", bind=True, max_retries=1, default_retry_delay=30,
             soft_time_limit=3600, time_limit=3900)
def ingest_archive_task(
    self,
    archive_document_id: int,
    product_name: str,
    firmware_version: str = "1.0",
    manufacturer: str = "",
    force: bool = False,
):
    """Background task: download archive from S3, extract files, create Documents, ingest each."""
    from app.models import Document, Product, FirmwareVersion
    from app.s3 import download_file, upload_file, s3_key_for_document
    from app.documents.archive import extract_archive

    t0 = time.perf_counter()
    logger.info("Celery ingest_archive_task started", extra={
        "archive_document_id": archive_document_id, "task_id": self.request.id,
    })

    engine = _get_sync_engine()

    with Session(engine) as session:
        archive_doc = session.get(Document, archive_document_id)
        if archive_doc is None:
            logger.error("Archive document not found", extra={"document_id": archive_document_id})
            return {"status": "error", "error": "Archive document not found"}

        archive_tenant_id = archive_doc.tenant_id
        _set_tenant_log_context(archive_tenant_id, session)

        from datetime import datetime, timezone as _tz
        archive_doc.status = "processing"
        archive_doc.processing_started_at = datetime.now(_tz.utc)
        session.commit()

        try:
            file_data = download_file(archive_doc.s3_key)
        except SoftTimeLimitExceeded:
            raise
        except Exception as exc:
            archive_doc.status = "error"
            archive_doc.error_message = f"S3 download failed: {exc}"
            session.commit()
            logger.error("S3 download failed for archive", extra={
                "document_id": archive_document_id, "s3_key": archive_doc.s3_key,
            }, exc_info=True)
            raise self.retry(exc=exc)

        try:
            entries = extract_archive(file_data, archive_doc.original_filename)
        except SoftTimeLimitExceeded:
            raise
        except Exception as exc:
            archive_doc.status = "error"
            archive_doc.error_message = f"Archive extraction failed: {exc}"
            session.commit()
            logger.error("Archive extraction failed", extra={
                "document_id": archive_document_id,
            }, exc_info=True)
            return {"status": "error", "error": str(exc)}

        if not entries:
            archive_doc.status = "error"
            archive_doc.error_message = "No supported files found in archive"
            session.commit()
            return {"status": "error", "error": "No supported files in archive"}

        from sqlalchemy import select as sa_select
        product_row = session.execute(
            sa_select(Product).where(Product.name == product_name)
        ).scalar_one_or_none()
        if product_row is None:
            product_row = Product(name=product_name, manufacturer=manufacturer, tenant_id=archive_tenant_id)
            session.add(product_row)
            session.flush()

        fw_row = session.execute(
            sa_select(FirmwareVersion).where(
                FirmwareVersion.product_id == product_row.id,
                FirmwareVersion.version == firmware_version,
            )
        ).scalar_one_or_none()
        if fw_row is None:
            fw_row = FirmwareVersion(product_id=product_row.id, version=firmware_version)
            session.add(fw_row)
            session.flush()

        archive_filename = archive_doc.original_filename

        child_ids = []
        for arc_path, entry_data in entries:
            entry_filename = os.path.basename(arc_path)
            entry_hash = hashlib.sha256(entry_data).hexdigest()

            if not force:
                dup = session.execute(
                    sa_select(Document).where(
                        Document.source_hash == entry_hash,
                        Document.product_id == product_row.id,
                        Document.firmware_version_id == fw_row.id,
                    ).limit(1)
                ).scalar_one_or_none()
                if dup is not None:
                    logger.info("Archive entry duplicate skipped", extra={
                        "entry": arc_path, "existing_id": dup.id,
                    })
                    continue

            child_doc = Document(
                product_id=product_row.id,
                firmware_version_id=fw_row.id,
                format="auto",
                original_filename=entry_filename,
                file_size_bytes=len(entry_data),
                title=os.path.splitext(entry_filename)[0],
                status="pending",
                source_hash=entry_hash,
                source_container=archive_filename,
                tenant_id=archive_tenant_id,
            )
            session.add(child_doc)
            session.flush()

            s3_key = s3_key_for_document(child_doc.id, entry_filename)
            upload_file(s3_key, entry_data, "application/octet-stream")
            child_doc.s3_key = s3_key
            session.commit()

            child_ids.append(child_doc.id)

        from app.s3 import delete_file as s3_delete
        if archive_doc.s3_key:
            try:
                s3_delete(archive_doc.s3_key)
            except Exception:
                logger.warning("Failed to delete archive S3 file", extra={"s3_key": archive_doc.s3_key})

        from app.models import Chunk
        existing_chunks = session.execute(
            sa_select(Chunk).where(Chunk.document_id == archive_doc.id)
        ).scalars().all()
        for c in existing_chunks:
            session.delete(c)
        session.delete(archive_doc)
        session.commit()

        for cid in child_ids:
            ingest_document_task.delay(cid)

        duration_ms = round((time.perf_counter() - t0) * 1000, 1)
        logger.info("Celery ingest_archive_task completed", extra={
            "archive_document_id": archive_document_id,
            "extracted_files": len(entries),
            "queued_documents": len(child_ids),
            "duration_ms": duration_ms,
        })
        return {
            "status": "ok",
            "archive_document_id": archive_document_id,
            "extracted_files": len(entries),
            "queued_documents": len(child_ids),
            "child_document_ids": child_ids,
        }


@celery.task(name="ingest_archive_from_s3", bind=True, max_retries=1, default_retry_delay=30)
def ingest_archive_from_s3_task(
    self,
    s3_key: str,
    archive_filename: str,
    product_name: str,
    firmware_version: str = "1.0",
    manufacturer: str = "",
    force: bool = False,
    tenant_id_str: str | None = None,
):
    """Download archive from S3, extract files, create Documents for each inner file.

    Unlike ingest_archive_task, this does NOT require a Document record for the
    archive itself — it works directly with an S3 key.
    """
    import uuid as _uuid
    from app.models import Document, Product, FirmwareVersion
    from app.s3 import download_file, upload_file, s3_key_for_document, delete_file as s3_delete
    from app.documents.archive import extract_archive

    t0 = time.perf_counter()
    logger.info("ingest_archive_from_s3_task started", extra={
        "s3_key": s3_key, "archive_filename": archive_filename, "task_id": self.request.id,
    })

    engine = _get_sync_engine()

    with Session(engine) as session:
        try:
            file_data = download_file(s3_key)
        except Exception as exc:
            logger.error("S3 download failed for archive", extra={
                "s3_key": s3_key,
            }, exc_info=True)
            raise self.retry(exc=exc)

        try:
            entries = extract_archive(file_data, archive_filename)
        except Exception as exc:
            logger.error("Archive extraction failed", extra={
                "archive_filename": archive_filename,
            }, exc_info=True)
            return {"status": "error", "error": str(exc)}

        if not entries:
            logger.warning("No supported files in archive", extra={"archive_filename": archive_filename})
            return {"status": "error", "error": "No supported files in archive"}

        _tenant_id = _uuid.UUID(tenant_id_str) if tenant_id_str else None
        _set_tenant_log_context(_tenant_id, session)

        from sqlalchemy import select as sa_select
        product_row = session.execute(
            sa_select(Product).where(Product.name == product_name)
        ).scalar_one_or_none()
        if product_row is None:
            from app.slugify import slugify
            product_row = Product(
                name=product_name,
                manufacturer=manufacturer,
                slug=slugify(product_name),
                manufacturer_slug=slugify(manufacturer) if manufacturer else "default",
                tenant_id=_tenant_id,
            )
            session.add(product_row)
            session.flush()

        fw_row = session.execute(
            sa_select(FirmwareVersion).where(
                FirmwareVersion.product_id == product_row.id,
                FirmwareVersion.version == firmware_version,
            )
        ).scalar_one_or_none()
        if fw_row is None:
            fw_row = FirmwareVersion(product_id=product_row.id, version=firmware_version)
            session.add(fw_row)
            session.flush()

        child_ids = []
        for arc_path, entry_data in entries:
            entry_filename = os.path.basename(arc_path)
            entry_hash = hashlib.sha256(entry_data).hexdigest()

            if not force:
                dup = session.execute(
                    sa_select(Document).where(
                        Document.source_hash == entry_hash,
                        Document.product_id == product_row.id,
                        Document.firmware_version_id == fw_row.id,
                    ).limit(1)
                ).scalar_one_or_none()
                if dup is not None:
                    logger.info("Archive entry duplicate skipped", extra={
                        "entry": arc_path, "existing_id": dup.id,
                    })
                    continue

            child_doc = Document(
                product_id=product_row.id,
                firmware_version_id=fw_row.id,
                format="auto",
                original_filename=entry_filename,
                file_size_bytes=len(entry_data),
                title=os.path.splitext(entry_filename)[0],
                status="pending",
                source_hash=entry_hash,
                source_container=archive_filename,
                tenant_id=_tenant_id,
            )
            session.add(child_doc)
            session.flush()

            child_s3_key = s3_key_for_document(child_doc.id, entry_filename)
            upload_file(child_s3_key, entry_data, "application/octet-stream")
            child_doc.s3_key = child_s3_key
            session.commit()

            child_ids.append(child_doc.id)

        try:
            s3_delete(s3_key)
        except Exception:
            logger.warning("Failed to delete archive S3 file", extra={"s3_key": s3_key})

        for cid in child_ids:
            ingest_document_task.delay(cid)

        duration_ms = round((time.perf_counter() - t0) * 1000, 1)
        logger.info("ingest_archive_from_s3_task completed", extra={
            "archive_filename": archive_filename,
            "extracted_files": len(entries),
            "queued_documents": len(child_ids),
            "duration_ms": duration_ms,
        })
        return {
            "status": "ok",
            "extracted_files": len(entries),
            "queued_documents": len(child_ids),
            "child_document_ids": child_ids,
        }


@celery.task(name="ingest_single_url", bind=True, max_retries=2, default_retry_delay=30,
             soft_time_limit=2700, time_limit=3000)
def ingest_single_url_task(self, document_id: int):
    """Background task: fetch a single web page, convert to Markdown, and ingest.

    Receives the placeholder Document id (created by the API endpoint).
    Updates the placeholder in-place with fetched content and embeddings.
    """
    import asyncio
    from app.models import Document, Chunk
    from app.ingestion.converters.web import convert_url
    from app.ingestion.pipeline import (
        enrich_for_embedding, _replace_generic_headings,
    )
    from app.ingestion.parsers.markdown import parse_markdown
    from app.ingestion.chunker import chunk_sections
    from app.ingestion.embedder import embed_texts
    from app.ingestion.text_cleaner import clean_for_embedding as _clean_md
    from app.config import settings as _settings
    from datetime import datetime, timezone

    t0 = time.perf_counter()
    engine = _get_sync_engine()

    with Session(engine) as session:
        doc = session.get(Document, document_id)
        if doc is None:
            logger.error("Placeholder document not found", extra={"document_id": document_id})
            return {"status": "error", "error": "Placeholder not found"}

        url = doc.source_path
        _set_tenant_log_context(doc.tenant_id, session)
        doc.status = "processing"
        doc.processing_started_at = datetime.now(timezone.utc)
        doc.progress_stage = "fetching"
        doc.progress_percent = 0
        session.commit()

    logger.info("Celery ingest_single_url_task started", extra={
        "url": url, "document_id": document_id, "task_id": self.request.id,
    })

    try:
        try:
            loop = asyncio.get_event_loop()
            text, convert_metadata = loop.run_until_complete(convert_url(url))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                text, convert_metadata = loop.run_until_complete(convert_url(url))
            finally:
                loop.close()
    except SoftTimeLimitExceeded:
        with Session(engine) as session:
            doc = session.get(Document, document_id)
            if doc:
                doc.status = "error"
                doc.error_message = "Task exceeded soft time limit (45 min) during URL fetch"
                doc.progress_stage = ""
                session.commit()
        logger.error("ingest_single_url_task soft time limit exceeded during fetch",
                     extra={"url": url, "document_id": document_id})
        return {"status": "error", "error": "soft_time_limit", "url": url}
    except Exception as exc:
        with Session(engine) as session:
            doc = session.get(Document, document_id)
            if doc:
                doc.status = "error"
                doc.error_message = f"Fetch failed: {type(exc).__name__}: {str(exc)[:1900]}"
                doc.progress_stage = ""
                session.commit()
        logger.error("URL conversion failed", extra={
            "url": url, "document_id": document_id,
            "error_type": type(exc).__name__,
        }, exc_info=True)
        raise self.retry(exc=exc)

    if not text or not text.strip():
        with Session(engine) as session:
            doc = session.get(Document, document_id)
            if doc:
                doc.status = "error"
                doc.error_message = "URL conversion produced empty content"
                doc.progress_stage = ""
                session.commit()
        logger.error("URL conversion produced empty content", extra={"url": url})
        return {"status": "error", "error": "Empty content", "url": url}

    source_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

    with Session(engine) as session:
        doc = session.get(Document, document_id)
        if doc is None:
            return {"status": "error", "error": "Placeholder disappeared"}

        page_title = convert_metadata.get("page_title") or convert_metadata.get("api_title") or url
        doc.title = page_title
        doc.original_filename = f"{page_title[:100]}.md"
        doc.file_size_bytes = len(text.encode("utf-8"))
        doc.source_hash = source_hash

        from app.s3 import upload_file as _s3_upload
        converted_key = f"documents/{doc.id}/converted.md"
        _s3_upload(converted_key, text.encode("utf-8"), content_type="text/markdown")
        doc.converted_s3_key = converted_key
        doc.s3_key = converted_key

        doc.progress_stage = "parsing"
        doc.progress_percent = 30
        session.commit()

        try:
            t_parse = time.perf_counter()
            sections = parse_markdown(text)
            _replace_generic_headings(sections, page_title)
            chunks = chunk_sections(sections)
            parse_ms = round((time.perf_counter() - t_parse) * 1000, 1)

            if not chunks:
                doc.status = "error"
                doc.error_message = "No content extracted"
                doc.progress_stage = ""
                session.commit()
                return {"status": "error", "error": "No content extracted", "url": url}

            doc.progress_stage = "embedding"
            doc.progress_percent = 50
            session.commit()

            t_embed = time.perf_counter()
            enriched = enrich_for_embedding(chunks)
            embeddings, embedding_api_tokens = embed_texts(enriched)
            embed_ms = round((time.perf_counter() - t_embed) * 1000, 1)

            doc.progress_stage = "storing"
            doc.progress_percent = 80
            session.commit()

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
            doc.error_message = None
            doc.progress_percent = 100
            doc.progress_stage = "done"
            doc.indexed_at = datetime.now(timezone.utc)

            token_counts = [c.token_count for c in chunks]
            doc.total_tokens = sum(token_counts)
            doc.min_chunk_tokens = min(token_counts)
            doc.max_chunk_tokens = max(token_counts)
            doc.avg_chunk_tokens = round(sum(token_counts) / len(token_counts), 1)
            doc.embedding_tokens = embedding_api_tokens or sum(token_counts)

            db_ms = round((time.perf_counter() - t_db) * 1000, 1)

            duration = time.perf_counter() - t0
            doc.ingest_duration_ms = round(duration * 1000, 1)
            doc.convert_ms = convert_metadata.get("total_ms", 0.0)
            doc.parse_ms = parse_ms
            doc.embed_ms = embed_ms
            doc.db_ms = db_ms
            doc.embedding_model = _settings.embedding_model_gemini
            doc.embedding_dims = _settings.embedding_dims

            session.commit()

            logger.info("Single URL ingestion completed", extra={
                "url": url, "document_id": doc.id,
                "chunks": len(chunks), "duration_ms": round(duration * 1000, 1),
            })
            return {
                "status": "ok",
                "document_id": doc.id,
                "url": url,
                "chunks": len(chunks),
                "duration_ms": round(duration * 1000, 1),
            }

        except SoftTimeLimitExceeded:
            doc.status = "error"
            doc.error_message = "Task exceeded soft time limit (45 min)"
            doc.progress_stage = ""
            session.commit()
            logger.error("ingest_single_url_task soft time limit exceeded",
                         extra={"url": url, "document_id": doc.id})
            return {"status": "error", "error": "soft_time_limit", "url": url}

        except Exception as exc:
            doc.status = "error"
            doc.error_message = str(exc)[:2000]
            doc.progress_stage = ""
            session.commit()
            logger.error("Single URL ingestion failed", extra={
                "url": url, "document_id": doc.id,
                "error_type": type(exc).__name__,
            }, exc_info=True)
            return {"status": "error", "error": str(exc), "url": url}


@celery.task(name="ingest_confluence", bind=True, max_retries=1, default_retry_delay=60,
             soft_time_limit=3600, time_limit=3900)
def ingest_confluence_task(self, document_id: int):
    """Background task: crawl Confluence page tree and ingest each page.

    Receives the placeholder Document id (created by the API endpoint).
    For every crawled page the task immediately:
      1. Creates a child Document in the DB (status='pending')
      2. Uploads page markdown to S3
      3. Dispatches ``ingest_document_task`` for that child

    This way each page appears in the UI and starts processing as soon as
    it is discovered — without waiting for the entire crawl to finish.
    """
    import asyncio
    from datetime import datetime, timezone
    from app.models import Document
    from app.ingestion.converters.confluence import crawl_confluence
    from app.s3 import upload_file

    t0 = time.perf_counter()
    engine = _get_sync_engine()

    with Session(engine) as session:
        placeholder = session.get(Document, document_id)
        if placeholder is None:
            logger.error("Placeholder document not found", extra={"document_id": document_id})
            return {"status": "error", "error": "Placeholder not found"}

        url = placeholder.source_path
        product_id = placeholder.product_id
        firmware_version_id = placeholder.firmware_version_id
        confluence_tenant_id = placeholder.tenant_id
        _set_tenant_log_context(confluence_tenant_id, session)

        placeholder.status = "processing"
        placeholder.processing_started_at = datetime.now(timezone.utc)
        placeholder.progress_stage = "crawling"
        placeholder.progress_percent = 0
        session.commit()

    logger.info("Celery ingest_confluence_task started", extra={
        "url": url, "document_id": document_id, "task_id": self.request.id,
    })

    dispatched = 0
    skipped = 0
    errors = 0
    pages_total = 0

    def _on_page(page):
        """Called by crawl_confluence for each page as it is discovered.

        Fully fault-tolerant: any error for a single page is logged and
        the crawl continues with the next page.
        """
        nonlocal dispatched, skipped, errors, pages_total
        pages_total += 1

        try:
            if not page.markdown or not page.markdown.strip():
                skipped += 1
                return

            md_bytes = page.markdown.encode("utf-8")
            source_hash = hashlib.sha256(md_bytes).hexdigest()

            with Session(engine) as s:
                existing = s.execute(
                    sa_select(Document).where(
                        Document.source_hash == source_hash,
                        Document.product_id == product_id,
                        Document.firmware_version_id == firmware_version_id,
                    ).limit(1)
                ).scalar_one_or_none()
                if existing is not None:
                    skipped += 1
                    return

                doc = Document(
                    product_id=product_id,
                    firmware_version_id=firmware_version_id,
                    format="markdown",
                    original_filename=f"{page.title}.md",
                    file_size_bytes=len(md_bytes),
                    title=page.title,
                    status="pending",
                    source_hash=source_hash,
                    source_container=url,
                    source_path=page.url,
                    tenant_id=confluence_tenant_id,
                )
                if page.ocr_images_total > 0 or page.ocr_error:
                    doc.ocr_ms = page.ocr_ms
                    doc.ocr_images_total = page.ocr_images_total
                    doc.ocr_images_success = page.ocr_images_success
                    doc.ocr_images_empty = page.ocr_images_empty
                    doc.ocr_images_failed = page.ocr_images_failed
                    doc.ocr_prompt_tokens = page.ocr_prompt_tokens
                    doc.ocr_completion_tokens = page.ocr_completion_tokens
                    doc.ocr_model = settings.ocr_vision_model
                if page.ocr_error:
                    doc.error_message = f"OCR failed: {page.ocr_error}"
                s.add(doc)
                s.flush()

                s3_key = f"documents/{doc.id}/source.md"
                upload_file(s3_key, md_bytes, content_type="text/markdown")
                doc.s3_key = s3_key
                s.commit()

                try:
                    task = ingest_document_task.delay(doc.id)
                    doc.celery_task_id = task.id
                    s.commit()
                except Exception as task_exc:
                    logger.warning("Failed to dispatch ingest task, doc stays pending", extra={
                        "child_document_id": doc.id, "error": str(task_exc)[:200],
                    })

                dispatched += 1
                logger.debug("Confluence page queued for ingestion", extra={
                    "page_id": page.page_id, "title": page.title,
                    "child_document_id": doc.id,
                })

        except Exception as exc:
            errors += 1
            logger.warning("Failed to persist Confluence page — skipping", extra={
                "page_id": page.page_id, "title": page.title,
                "error_type": type(exc).__name__,
                "error": str(exc)[:300],
            })
            return

        try:
            with Session(engine) as s:
                ph = s.get(Document, document_id)
                if ph:
                    stage = f"crawling ({pages_total} found, {dispatched} queued)"
                    if errors:
                        stage += f", {errors} storage errors!"
                    ph.progress_stage = stage
                    ph.title = f"{page.title}" if pages_total == 1 else ph.title
                    s.commit()
        except Exception:
            pass

    try:
        try:
            result = asyncio.get_event_loop().run_until_complete(
                crawl_confluence(url, max_pages=500, page_callback=_on_page)
            )
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(
                    crawl_confluence(url, max_pages=500, page_callback=_on_page)
                )
            finally:
                loop.close()
    except SoftTimeLimitExceeded:
        with Session(engine) as session:
            placeholder = session.get(Document, document_id)
            if placeholder:
                placeholder.status = "error"
                placeholder.error_message = (
                    f"Crawl exceeded soft time limit (60 min). "
                    f"Processed {dispatched} pages before timeout."
                )
                placeholder.progress_stage = ""
                session.commit()
        logger.error("ingest_confluence_task soft time limit exceeded", extra={
            "url": url, "document_id": document_id, "dispatched": dispatched,
        })
        return {
            "status": "error", "error": "soft_time_limit",
            "url": url, "document_id": document_id, "dispatched": dispatched,
        }

    except Exception as exc:
        from app.ingestion.converters.confluence import ConfluenceAuthError
        is_auth = isinstance(exc, ConfluenceAuthError)

        with Session(engine) as session:
            placeholder = session.get(Document, document_id)
            if placeholder:
                placeholder.status = "error"
                placeholder.error_message = f"Crawl failed: {type(exc).__name__}: {str(exc)[:1900]}"
                placeholder.progress_stage = ""
                session.commit()

        if is_auth:
            logger.error("Confluence authentication failed — not retrying", extra={
                "url": url, "document_id": document_id,
            }, exc_info=True)
            return {"status": "error", "error": str(exc)[:500]}

        logger.error("Confluence crawl failed", extra={
            "url": url, "document_id": document_id,
            "error_type": type(exc).__name__,
        }, exc_info=True)
        raise self.retry(exc=exc)

    with Session(engine) as session:
        placeholder = session.get(Document, document_id)
        if placeholder:
            duration_ms = round((time.perf_counter() - t0) * 1000, 1)
            placeholder.progress_percent = 100
            placeholder.ingest_duration_ms = duration_ms
            placeholder.total_chunks = dispatched
            if result.root_title:
                placeholder.title = f"{result.root_title} ({result.total_pages} pages)"

            crawl_errors_summary = "; ".join(result.errors[:3]) if result.errors else ""

            crawled = pages_total - skipped
            if dispatched == 0:
                placeholder.status = "error"
                placeholder.progress_stage = "done"
                if result.total_pages == 0:
                    placeholder.error_message = (
                        "Crawl returned 0 pages. The page may not exist or access is denied."
                    )
                elif skipped == pages_total and errors == 0:
                    placeholder.error_message = (
                        f"All {pages_total} crawled pages had empty content — "
                        "no documents were created. This usually means authentication "
                        "is required or the pages have no body content."
                    )
                    if crawl_errors_summary:
                        placeholder.error_message += f" Details: {crawl_errors_summary}"
                else:
                    placeholder.error_message = (
                        f"No documents were created from {pages_total} crawled pages "
                        f"({skipped} empty, {errors} errors)."
                    )
                    if crawl_errors_summary:
                        placeholder.error_message += f" Details: {crawl_errors_summary}"

                logger.warning("Confluence crawl produced 0 dispatched documents", extra={
                    "url": url, "document_id": document_id,
                    "total_pages": result.total_pages,
                    "skipped": skipped, "errors": errors,
                    "crawl_errors": result.errors[:5],
                })
            elif crawled > 0 and errors >= crawled:
                placeholder.status = "error"
                placeholder.progress_stage = "done"
                placeholder.error_message = (
                    f"Storage write failures: all {errors} pages failed to save. "
                    "Check MinIO health (disk, drives)."
                )
            elif errors > 0:
                placeholder.status = "ready"
                placeholder.progress_stage = "done"
                placeholder.error_message = (
                    f"Partial storage failures: {errors}/{crawled} pages could not be saved."
                )
            else:
                placeholder.status = "ready"
                placeholder.progress_stage = "done"
                placeholder.error_message = None
            session.commit()

    duration_ms = round((time.perf_counter() - t0) * 1000, 1)
    logger.info("Celery ingest_confluence_task completed", extra={
        "url": url, "document_id": document_id,
        "total_pages": result.total_pages,
        "dispatched": dispatched, "skipped": skipped, "errors": errors,
        "duration_ms": duration_ms,
    })
    return {
        "status": "ok",
        "url": url,
        "document_id": document_id,
        "total_pages": result.total_pages,
        "dispatched": dispatched,
        "skipped": skipped,
        "errors": errors,
        "crawl_errors": result.errors[:10],
        "duration_ms": duration_ms,
    }


@celery.task(name="reingest_confluence_page", bind=True, max_retries=2, default_retry_delay=30,
             soft_time_limit=2700, time_limit=3000)
def reingest_confluence_page_task(self, document_id: int):
    """Re-fetch a single Confluence page by its source_path and re-ingest.

    Used when a child document (format='markdown') produced by a Confluence
    crawl needs to be individually re-fetched from the source, e.g. after
    an embedding failure (429) or when content has changed.
    """
    from datetime import datetime, timezone
    from app.models import Document, Chunk
    from app.ingestion.converters.confluence import (
        parse_confluence_url, _get_page_content, _html_to_markdown,
    )
    from app.s3 import upload_file

    t0 = time.perf_counter()
    engine = _get_sync_engine()

    with Session(engine) as session:
        doc = session.get(Document, document_id)
        if doc is None:
            logger.error("Document not found for confluence page reingest",
                         extra={"document_id": document_id})
            return {"status": "error", "error": "Document not found"}

        url = doc.source_path
        _set_tenant_log_context(doc.tenant_id, session)

        if not url:
            doc.status = "error"
            doc.error_message = "No source_path stored — cannot reingest page"
            session.commit()
            return {"status": "error", "error": "No source_path"}

        doc.status = "processing"
        doc.processing_started_at = datetime.now(timezone.utc)
        doc.progress_stage = "fetching"
        doc.progress_percent = 0
        session.commit()

    logger.info("Celery reingest_confluence_page_task started",
                extra={"url": url, "document_id": document_id})

    try:
        base_url, _space_key, page_id = parse_confluence_url(url)
    except ValueError as exc:
        with Session(engine) as session:
            doc = session.get(Document, document_id)
            if doc:
                doc.status = "error"
                doc.error_message = f"Invalid Confluence URL: {exc}"
                doc.progress_stage = ""
                session.commit()
        return {"status": "error", "error": str(exc)}

    try:
        title, html_body = _get_page_content(base_url, page_id)
    except SoftTimeLimitExceeded:
        with Session(engine) as session:
            doc = session.get(Document, document_id)
            if doc:
                doc.status = "error"
                doc.error_message = "Task exceeded soft time limit (45 min)"
                doc.progress_stage = ""
                session.commit()
        logger.error("reingest_confluence_page_task soft time limit exceeded",
                     extra={"url": url, "document_id": document_id})
        return {"status": "error", "error": "soft_time_limit", "document_id": document_id}
    except Exception as exc:
        with Session(engine) as session:
            doc = session.get(Document, document_id)
            if doc:
                doc.status = "error"
                doc.error_message = f"Fetch failed: {type(exc).__name__}: {str(exc)[:1900]}"
                doc.progress_stage = ""
                session.commit()
        logger.error("Confluence page fetch failed",
                     extra={"url": url, "document_id": document_id},
                     exc_info=True)
        raise self.retry(exc=exc)

    markdown = _html_to_markdown(html_body, title, base_url=base_url, page_id=page_id)
    md_bytes = markdown.encode("utf-8")
    source_hash = hashlib.sha256(md_bytes).hexdigest()

    with Session(engine) as session:
        doc = session.get(Document, document_id)
        if doc is None:
            return {"status": "error", "error": "Document disappeared"}

        doc.title = title
        doc.original_filename = f"{title}.md"
        doc.file_size_bytes = len(md_bytes)
        doc.source_hash = source_hash
        doc.progress_stage = "uploading"
        doc.progress_percent = 30

        s3_key = doc.s3_key or f"documents/{doc.id}/source.md"
        upload_file(s3_key, md_bytes, content_type="text/markdown")
        doc.s3_key = s3_key
        session.commit()

    try:
        task = ingest_document_task.delay(document_id)
        with Session(engine) as session:
            doc = session.get(Document, document_id)
            if doc:
                doc.celery_task_id = task.id
                doc.progress_stage = "queued for indexing"
                doc.progress_percent = 40
                session.commit()
    except Exception as exc:
        logger.warning("Failed to dispatch ingest_document_task after page refetch",
                       extra={"document_id": document_id, "error": str(exc)[:200]})

    duration_ms = round((time.perf_counter() - t0) * 1000, 1)
    logger.info("Confluence page refetched and queued for indexing",
                extra={"document_id": document_id, "title": title,
                       "duration_ms": duration_ms})
    return {
        "status": "ok",
        "document_id": document_id,
        "title": title,
        "duration_ms": duration_ms,
    }


def _update_placeholder_progress(session, document_id: int, done: int, total: int):
    """Update placeholder document progress (throttled to avoid excessive commits)."""
    from app.models import Document
    pct = round(done / max(total, 1) * 100)
    placeholder = session.get(Document, document_id)
    if placeholder and placeholder.progress_percent != pct:
        placeholder.progress_percent = pct
        placeholder.progress_stage = f"ingesting ({done}/{total})"
        session.commit()


@celery.task(name="run_reindex_job", bind=True, max_retries=0)
def run_reindex_job_task(self, job_id: int, document_ids: list[int]):
    """Celery task: orchestrate a reindex job."""
    from app.reindex.service import run_reindex_sync
    logger.info(
        "Celery run_reindex_job_task started",
        extra={"job_id": job_id, "document_count": len(document_ids), "task_id": self.request.id},
    )
    try:
        run_reindex_sync(job_id, document_ids)
    except Exception as exc:
        logger.error(
            "Celery run_reindex_job_task crashed",
            extra={"job_id": job_id, "error_type": type(exc).__name__},
            exc_info=True,
        )
        from app.models import ReindexJob
        from datetime import datetime, timezone
        engine = _get_sync_engine()
        with Session(engine) as session:
            job = session.get(ReindexJob, job_id)
            if job and job.status == "running":
                job.status = "failed"
                job.error_message = f"Task crashed: {exc}"
                job.finished_at = datetime.now(timezone.utc)
                session.commit()
        raise


@celery.task(name="cleanup_expired_uploads", bind=True)
def cleanup_expired_uploads_task(self):
    """Periodic task: abort S3 multipart uploads and delete expired upload sessions."""
    from datetime import datetime, timezone
    from sqlalchemy import select
    from app.models import UploadSession
    from app.s3 import abort_multipart_upload

    engine = _get_sync_engine()
    now = datetime.now(timezone.utc)
    cleaned = 0

    with Session(engine) as session:
        rows = session.execute(
            select(UploadSession).where(
                UploadSession.status == "uploading",
                UploadSession.expires_at < now,
            )
        ).scalars().all()

        for us in rows:
            try:
                if us.s3_upload_id:
                    abort_multipart_upload(us.s3_key, us.s3_upload_id)
            except Exception:
                logger.warning(
                    "Failed to abort expired S3 multipart upload",
                    extra={"upload_id": us.id, "s3_key": us.s3_key},
                    exc_info=True,
                )
            us.status = "expired"
            cleaned += 1

        session.commit()

    if cleaned:
        logger.info("Cleaned up expired upload sessions", extra={"count": cleaned})
    return {"cleaned": cleaned}


@celery.task(name="check_stale_reindex_jobs", bind=True)
def check_stale_reindex_jobs_task(self):
    """Periodic task: detect and mark stale reindex jobs."""
    from datetime import datetime, timezone
    from sqlalchemy import select
    from app.models import ReindexJob

    engine = _get_sync_engine()
    threshold = datetime.now(timezone.utc) - __import__("datetime").timedelta(
        seconds=settings.reindex_stale_timeout_sec
    )

    with Session(engine) as session:
        stale_jobs = session.execute(
            select(ReindexJob).where(
                ReindexJob.status == "running",
                ReindexJob.heartbeat_at < threshold,
            )
        ).scalars().all()

        for job in stale_jobs:
            job.status = "stale"
            job.finished_at = datetime.now(timezone.utc)
            job.error_message = (
                f"Heartbeat stopped at {job.heartbeat_at}. "
                f"Exceeded stale timeout of {settings.reindex_stale_timeout_sec}s."
            )
            logger.warning(
                "Reindex job marked stale by periodic check",
                extra={
                    "event": "reindex_job_stale",
                    "job_id": job.id,
                    "last_heartbeat": str(job.heartbeat_at),
                },
            )

        if stale_jobs:
            session.commit()


@celery.task(name="check_stale_documents", bind=True)
def check_stale_documents_task(self):
    """Periodic task: reset documents stuck in 'processing' for too long."""
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import select, func as sa_func
    from app.models import Document

    engine = _get_sync_engine()
    threshold = datetime.now(timezone.utc) - timedelta(
        seconds=settings.document_stale_timeout_sec
    )

    with Session(engine) as session:
        effective_started = sa_func.coalesce(
            Document.processing_started_at, Document.uploaded_at,
        )
        stale_docs = session.execute(
            select(Document).where(
                Document.status == "processing",
                effective_started < threshold,
            )
        ).scalars().all()

        for doc in stale_docs:
            started = doc.processing_started_at or doc.uploaded_at
            doc.status = "error"
            doc.error_message = (
                f"Auto-reset: document stuck in 'processing' since {started}. "
                f"Exceeded stale timeout of {settings.document_stale_timeout_sec}s."
            )
            doc.progress_percent = 0
            doc.progress_stage = ""
            logger.warning(
                "Document auto-reset from processing to error",
                extra={
                    "event": "document_stale_reset",
                    "document_id": doc.id,
                    "title": doc.title,
                    "processing_started_at": str(started),
                },
            )

        if stale_docs:
            session.commit()
            logger.info(
                "Stale documents reset",
                extra={"count": len(stale_docs)},
            )


@celery.task(name="queue_status_snapshot", bind=True)
def queue_status_snapshot_task(self):
    """Periodic task (every 30s): log current queue depth by document status."""
    from app.models import Document

    engine = _get_sync_engine()
    with Session(engine) as session:
        rows = session.execute(
            sa_select(Document.status, func.count())
            .where(Document.status.in_(["pending", "processing"]))
            .group_by(Document.status)
        ).all()

    counts = {status: cnt for status, cnt in rows}
    pending = counts.get("pending", 0)
    processing = counts.get("processing", 0)

    _signals_logger.info(
        "Queue snapshot",
        extra={
            "event": "Queue snapshot",
            "pending_count": pending,
            "processing_count": processing,
            "total_queued": pending + processing,
        },
    )


def _add_months(d, months: int):
    """Add N months to a date, returning the 1st of the resulting month."""
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    return d.replace(year=year, month=month, day=1)


@celery.task(name="ensure_usage_partitions", bind=True)
def ensure_usage_partitions_task(self):
    """Create usage_log partitions for the current month and the next 2 months.

    Safe to run repeatedly — uses IF NOT EXISTS. Runs daily via Beat.
    """
    from datetime import date
    from sqlalchemy import text as sa_text

    engine = _get_sync_engine()
    today = date.today()
    created = []

    with Session(engine) as session:
        for offset in range(3):
            month_start = _add_months(today, offset)
            month_end = _add_months(today, offset + 1)
            partition_name = f"usage_log_{month_start.year}_{month_start.month:02d}"

            session.execute(sa_text(
                f"CREATE TABLE IF NOT EXISTS {partition_name} "
                f"PARTITION OF usage_log "
                f"FOR VALUES FROM ('{month_start.isoformat()}') "
                f"TO ('{month_end.isoformat()}')"
            ))
            created.append(partition_name)

        session.commit()

    logger.info(
        "Usage partitions ensured",
        extra={"event": "usage_partitions", "partitions": created},
    )


@celery.task(name="s3_health_probe", bind=True)
def s3_health_probe_task(self):
    """Periodic (60s): write+delete a probe object to detect MinIO degradation early."""
    from app.s3 import check_write_health

    if check_write_health():
        logger.info("S3 health probe OK")
    else:
        logger.error("S3 health probe FAILED — storage may be degraded or unreachable")


@celery.task(name="cleanup_expired_shares", bind=True)
def cleanup_expired_shares_task(self):
    """Periodic task: delete expired and old deactivated shared links."""
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import select, or_, and_
    from app.models import SharedLink

    engine = _get_sync_engine()
    now = datetime.now(timezone.utc)
    deactivated_cutoff = now - timedelta(days=30)
    deleted = 0

    with Session(engine) as session:
        rows = session.execute(
            select(SharedLink).where(
                or_(
                    and_(SharedLink.expires_at.isnot(None), SharedLink.expires_at < now),
                    and_(SharedLink.is_active.is_(False), SharedLink.created_at < deactivated_cutoff),
                )
            )
        ).scalars().all()

        for link in rows:
            session.delete(link)
            deleted += 1

        if deleted:
            session.commit()

    if deleted:
        logger.info("Cleaned up expired/deactivated shared links", extra={"count": deleted})
