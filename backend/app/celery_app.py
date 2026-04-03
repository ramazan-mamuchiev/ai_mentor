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
        "delete_product": {"queue": "critical"},
        "queue_status_snapshot": {"queue": "monitoring"},
        "cleanup_expired_uploads": {"queue": "monitoring"},
        "check_stale_reindex_jobs": {"queue": "monitoring"},
        "check_stale_documents": {"queue": "monitoring"},
        "rescue_orphaned_documents": {"queue": "monitoring"},
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
        "rescue-orphaned-documents": {
            "task": "rescue_orphaned_documents",
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


def _create_proto_bundle_docs(
    session,
    proto_entries: list[tuple[str, bytes]],
    *,
    product_id: int,
    firmware_version_id: int,
    archive_filename: str,
    tenant_id=None,
    force: bool = False,
) -> list[int]:
    """Convert proto entries into bundled domain documents via convert_proto_bundle.

    Returns list of created document IDs.
    """
    from app.ingestion.converters.proto import convert_proto_bundle
    from app.models import Document
    from app.s3 import upload_file, s3_key_for_document
    from sqlalchemy import select as sa_select

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
            dup = session.execute(
                sa_select(Document).where(
                    Document.source_hash == md_hash,
                    Document.product_id == product_id,
                    Document.firmware_version_id == firmware_version_id,
                ).limit(1)
            ).scalar_one_or_none()
            if dup is not None:
                logger.info("Proto bundle duplicate skipped", extra={
                    "domain": domain_name, "existing_id": dup.id,
                })
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
        session.flush()

        s3_key = s3_key_for_document(doc.id, filename)
        upload_file(s3_key, md_bytes, "text/markdown")
        doc.s3_key = s3_key
        session.commit()

        doc_ids.append(doc.id)
        logger.info("Proto bundle document created", extra={
            "domain": domain_name, "document_id": doc.id,
            "services": meta.get("services", 0),
            "messages": meta.get("messages", 0),
            "source_files": meta.get("source_files", 0),
        })

    return doc_ids


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
            from app.products.utils import make_product_slug
            product_row = Product(
                name=product_name, manufacturer=manufacturer,
                slug=make_product_slug(manufacturer, product_name),
                tenant_id=archive_tenant_id,
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

        archive_filename = archive_doc.original_filename

        from app.documents.archive import is_proto_heavy, classify_archive_entries
        proto_entries, other_entries = classify_archive_entries(entries)
        use_bundle = is_proto_heavy(entries) and len(proto_entries) >= 5

        child_ids = []

        if use_bundle:
            bundle_ids = _create_proto_bundle_docs(
                session, proto_entries,
                product_id=product_row.id,
                firmware_version_id=fw_row.id,
                archive_filename=archive_filename,
                tenant_id=archive_tenant_id,
                force=force,
            )
            child_ids.extend(bundle_ids)
            remaining_entries = other_entries
        else:
            remaining_entries = entries

        for arc_path, entry_data in remaining_entries:
            entry_filename = os.path.basename(arc_path)
            entry_folder = os.path.dirname(arc_path).replace("\\", "/")
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
                source_folder=entry_folder,
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
    product_id: int,
    firmware_version_id: int,
    force: bool = False,
    tenant_id_str: str | None = None,
):
    """Download archive from S3, extract files, create Documents for each inner file.

    Product and FirmwareVersion are created by the API layer before this task
    is enqueued, so the product appears in the UI immediately.
    """
    import uuid as _uuid
    from app.models import Document, Product, FirmwareVersion
    from app.s3 import download_file, upload_file, s3_key_for_document, delete_file as s3_delete
    from app.documents.archive import extract_archive

    t0 = time.perf_counter()
    logger.info("ingest_archive_from_s3_task started", extra={
        "s3_key": s3_key, "archive_filename": archive_filename, "task_id": self.request.id,
        "product_id": product_id, "firmware_version_id": firmware_version_id,
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

        product_row = session.get(Product, product_id)
        if product_row is None:
            logger.error("Product not found", extra={"product_id": product_id})
            return {"status": "error", "error": f"Product {product_id} not found"}

        fw_row = session.get(FirmwareVersion, firmware_version_id)
        if fw_row is None:
            logger.error("FirmwareVersion not found", extra={"firmware_version_id": firmware_version_id})
            return {"status": "error", "error": f"FirmwareVersion {firmware_version_id} not found"}

        from app.documents.archive import is_proto_heavy, classify_archive_entries
        proto_entries, other_entries = classify_archive_entries(entries)
        use_bundle = is_proto_heavy(entries) and len(proto_entries) >= 5

        child_ids = []

        if use_bundle:
            bundle_ids = _create_proto_bundle_docs(
                session, proto_entries,
                product_id=product_row.id,
                firmware_version_id=fw_row.id,
                archive_filename=archive_filename,
                tenant_id=_tenant_id,
                force=force,
            )
            child_ids.extend(bundle_ids)
            remaining_entries = other_entries
        else:
            remaining_entries = entries

        for arc_path, entry_data in remaining_entries:
            entry_filename = os.path.basename(arc_path)
            entry_folder = os.path.dirname(arc_path).replace("\\", "/")
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
                source_folder=entry_folder,
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

    http_auth = None
    with Session(engine) as session:
        doc = session.get(Document, document_id)
        if doc is None:
            logger.error("Placeholder document not found", extra={"document_id": document_id})
            return {"status": "error", "error": "Placeholder not found"}

        url = doc.source_path
        _set_tenant_log_context(doc.tenant_id, session)

        ckpt = doc.crawl_checkpoint
        if ckpt and isinstance(ckpt, dict) and ckpt.get("http_auth"):
            from app.utils.crypto import decrypt_credentials
            http_auth = decrypt_credentials(ckpt["http_auth"])

        doc.status = "processing"
        doc.processing_started_at = datetime.now(timezone.utc)
        doc.progress_stage = "fetching"
        doc.progress_percent = 0
        session.commit()

    logger.info("Celery ingest_single_url_task started", extra={
        "url": url, "document_id": document_id, "task_id": self.request.id,
        "has_http_auth": http_auth is not None,
    })

    try:
        try:
            loop = asyncio.get_event_loop()
            text, convert_metadata = loop.run_until_complete(convert_url(url, auth=http_auth))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                text, convert_metadata = loop.run_until_complete(convert_url(url, auth=http_auth))
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
            sections, _fm = parse_markdown(text)
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


@celery.task(name="ingest_confluence", bind=True, max_retries=10, default_retry_delay=10,
             soft_time_limit=14400, time_limit=14700)
def ingest_confluence_task(self, document_id: int, max_pages: int | None = None, max_depth: int | None = None):
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
    from datetime import datetime, timezone, timedelta
    from app.models import Document
    from app.ingestion.converters.confluence import crawl_confluence
    from app.s3 import upload_file

    _CHECKPOINT_VERSION = 1
    _CHECKPOINT_TTL = timedelta(hours=24)

    t0 = time.perf_counter()
    engine = _get_sync_engine()

    restored_queue = None
    restored_visited = None

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

        confluence_auth = None
        ckpt_pre = placeholder.crawl_checkpoint
        if ckpt_pre and isinstance(ckpt_pre, dict) and ckpt_pre.get("auth"):
            from app.utils.crypto import decrypt_credentials
            confluence_auth = decrypt_credentials(ckpt_pre["auth"])

        placeholder.status = "processing"
        placeholder.processing_started_at = datetime.now(timezone.utc)
        placeholder.progress_stage = "crawling"
        placeholder.progress_percent = 0
        session.commit()

    logger.info("Celery ingest_confluence_task started", extra={
        "url": url, "document_id": document_id, "task_id": self.request.id,
        "has_auth": confluence_auth is not None,
    })

    dispatched = 0
    skipped = 0
    errors = 0
    pages_seen = 0

    with Session(engine) as session:
        placeholder = session.get(Document, document_id)
        ckpt = placeholder.crawl_checkpoint if placeholder else None
        if ckpt and isinstance(ckpt, dict):
            try:
                if ckpt.get("version") != _CHECKPOINT_VERSION:
                    raise ValueError(f"unknown checkpoint version: {ckpt.get('version')}")
                saved_at = datetime.fromisoformat(ckpt["saved_at"])
                age = datetime.now(timezone.utc) - saved_at
                if age > _CHECKPOINT_TTL:
                    raise ValueError(f"checkpoint too old: {age}")

                restored_queue = [tuple(pair) for pair in ckpt["queue"]]
                restored_visited = set(ckpt["visited"])
                dispatched = ckpt.get("dispatched", 0)
                skipped = ckpt.get("skipped", 0)
                errors = ckpt.get("errors", 0)
                pages_seen = ckpt.get("pages_seen", 0)

                logger.info("Resuming crawl from checkpoint", extra={
                    "document_id": document_id,
                    "queue_size": len(restored_queue),
                    "visited_size": len(restored_visited),
                    "checkpoint_age_sec": round(age.total_seconds()),
                    "dispatched": dispatched,
                    "skipped": skipped,
                })
            except Exception as ckpt_err:
                logger.warning("Discarding invalid/stale checkpoint — starting fresh", extra={
                    "document_id": document_id,
                    "reason": str(ckpt_err)[:300],
                })
                restored_queue = None
                restored_visited = None

    _latest_queue_snapshot: list[tuple[str, int]] = []
    _latest_visited_snapshot: set[str] = set()

    def _on_checkpoint(queue_snapshot, visited_snapshot):
        """Called by crawl_confluence after each page to expose BFS state."""
        nonlocal _latest_queue_snapshot, _latest_visited_snapshot
        _latest_queue_snapshot = queue_snapshot
        _latest_visited_snapshot = visited_snapshot

    def _on_page(page):
        """Called by crawl_confluence for each page as it is discovered.

        Fully fault-tolerant: any error for a single page is logged and
        the crawl continues with the next page.
        """
        nonlocal dispatched, skipped, errors, pages_seen
        pages_seen += 1

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
                    stage = f"crawling ({pages_seen} found, {dispatched} queued)"
                    if errors:
                        stage += f", {errors} storage errors!"
                    ph.progress_stage = stage
                    ph.title = f"{page.title}" if pages_seen == 1 else ph.title
                    _ckpt_data = {
                        "version": _CHECKPOINT_VERSION,
                        "saved_at": datetime.now(timezone.utc).isoformat(),
                        "queue": list(_latest_queue_snapshot),
                        "visited": list(_latest_visited_snapshot),
                        "dispatched": dispatched,
                        "skipped": skipped,
                        "errors": errors,
                        "pages_seen": pages_seen,
                    }
                    if ckpt_pre and isinstance(ckpt_pre, dict) and ckpt_pre.get("auth"):
                        _ckpt_data["auth"] = ckpt_pre["auth"]
                    ph.crawl_checkpoint = _ckpt_data
                    s.commit()
        except Exception:
            pass

    _eff_max_pages = max_pages or settings.confluence_crawl_max_pages or settings.crawl_max_pages
    _eff_max_depth = max_depth or settings.confluence_crawl_max_depth or settings.crawl_max_depth
    _eff_max_seconds = settings.confluence_crawl_max_seconds or settings.crawl_max_seconds

    _crawl_kwargs = dict(
        max_pages=_eff_max_pages,
        max_depth=_eff_max_depth,
        max_seconds=_eff_max_seconds,
        page_callback=_on_page,
        checkpoint_callback=_on_checkpoint,
        auth=confluence_auth,
    )
    if restored_queue is not None:
        _crawl_kwargs["initial_queue"] = restored_queue
        _crawl_kwargs["initial_visited"] = restored_visited

    try:
        try:
            result = asyncio.get_event_loop().run_until_complete(
                crawl_confluence(url, **_crawl_kwargs)
            )
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(
                    crawl_confluence(url, **_crawl_kwargs)
                )
            finally:
                loop.close()
    except SoftTimeLimitExceeded:
        with Session(engine) as session:
            placeholder = session.get(Document, document_id)
            if placeholder:
                placeholder.progress_stage = f"timeout, resuming... ({dispatched} pages so far)"
                session.commit()
        logger.warning("Confluence crawl hit Celery time limit — resuming from checkpoint", extra={
            "url": url, "document_id": document_id,
            "dispatched": dispatched, "retry": self.request.retries + 1,
        })
        raise self.retry(countdown=10)

    except Exception as exc:
        from app.ingestion.converters.confluence import ConfluenceAuthError
        is_auth = isinstance(exc, ConfluenceAuthError)

        with Session(engine) as session:
            placeholder = session.get(Document, document_id)
            if placeholder:
                placeholder.status = "error"
                placeholder.error_message = f"Crawl failed: {type(exc).__name__}: {str(exc)[:1900]}"
                placeholder.progress_stage = ""
                if is_auth:
                    placeholder.crawl_checkpoint = None
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
            auth_token = (ckpt_pre or {}).get("auth") if isinstance(ckpt_pre, dict) else None
            placeholder.crawl_checkpoint = {"auth": auth_token} if auth_token else None
            if result.root_title:
                placeholder.title = f"{result.root_title} ({result.total_pages} pages)"

            crawl_errors_summary = "; ".join(result.errors[:3]) if result.errors else ""

            crawled = pages_seen - skipped
            if dispatched == 0:
                placeholder.status = "error"
                placeholder.progress_stage = "done"
                if result.total_pages == 0:
                    placeholder.error_message = (
                        "Crawl returned 0 pages. The page may not exist or access is denied."
                    )
                elif skipped == pages_seen and errors == 0:
                    placeholder.error_message = (
                        f"All {pages_seen} crawled pages had empty content — "
                        "no documents were created. This usually means authentication "
                        "is required or the pages have no body content."
                    )
                    if crawl_errors_summary:
                        placeholder.error_message += f" Details: {crawl_errors_summary}"
                else:
                    placeholder.error_message = (
                        f"No documents were created from {pages_seen} crawled pages "
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


@celery.task(name="ingest_site", bind=True, max_retries=10, default_retry_delay=10,
             soft_time_limit=7200, time_limit=7500)
def ingest_site_task(self, document_id: int, max_depth: int | None = None, max_pages: int | None = None, download_resources: bool = True):
    """Background task: crawl a website and ingest each page + downloaded files.

    Receives the placeholder Document id (format='site').
    For every crawled page the task immediately:
      1. Creates a child Document in the DB (status='pending')
      2. Uploads content to S3
      3. Dispatches ``ingest_document_task`` for that child

    File links (PDF, WSDL, etc.) are downloaded and processed the same way.
    Supports crash recovery via crawl_checkpoint.
    """
    import asyncio
    from datetime import datetime, timezone, timedelta
    from app.models import Document
    from app.ingestion.converters.site import crawl_site, CrawledPage, CrawledFile
    from app.s3 import upload_file
    from app.ingestion.pipeline import detect_format

    _CHECKPOINT_VERSION = 1
    _CHECKPOINT_TTL = timedelta(hours=24)

    _max_depth = max_depth or settings.site_crawl_max_depth or settings.crawl_max_depth
    _max_pages = max_pages or settings.site_crawl_max_pages or settings.crawl_max_pages
    _max_seconds_cfg = settings.site_crawl_max_seconds or settings.crawl_max_seconds

    _soft_limit = (self.request.timelimit or (None, None))[0] or 7200
    _deadline_seconds = int(_soft_limit * 0.85)

    t0 = time.perf_counter()
    engine = _get_sync_engine()

    restored_state = None

    with Session(engine) as session:
        placeholder = session.get(Document, document_id)
        if placeholder is None:
            logger.error("Placeholder document not found", extra={"document_id": document_id})
            return {"status": "error", "error": "Placeholder not found"}

        url = placeholder.source_path
        product_id = placeholder.product_id
        firmware_version_id = placeholder.firmware_version_id
        site_tenant_id = placeholder.tenant_id
        _set_tenant_log_context(site_tenant_id, session)

        placeholder.status = "processing"
        placeholder.processing_started_at = datetime.now(timezone.utc)
        placeholder.progress_stage = "crawling"
        placeholder.progress_percent = 0
        session.commit()

    logger.info("Celery ingest_site_task started", extra={
        "url": url, "document_id": document_id, "task_id": self.request.id,
        "max_depth": _max_depth, "max_pages": _max_pages,
        "retry": self.request.retries, "deadline_seconds": _deadline_seconds,
    })

    dispatched = 0
    files_dispatched = 0
    skipped = 0
    errors = 0
    pages_seen = 0

    with Session(engine) as session:
        placeholder = session.get(Document, document_id)
        ckpt = placeholder.crawl_checkpoint if placeholder else None
        if ckpt and isinstance(ckpt, dict):
            try:
                if ckpt.get("version") != _CHECKPOINT_VERSION:
                    raise ValueError(f"unknown checkpoint version: {ckpt.get('version')}")
                saved_at = datetime.fromisoformat(ckpt["saved_at"])
                age = datetime.now(timezone.utc) - saved_at
                if age > _CHECKPOINT_TTL:
                    raise ValueError(f"checkpoint too old: {age}")

                restored_state = ckpt.get("crawl4ai_state")
                dispatched = ckpt.get("dispatched", 0)
                files_dispatched = ckpt.get("files_dispatched", 0)
                skipped = ckpt.get("skipped", 0)
                errors = ckpt.get("errors", 0)
                pages_seen = ckpt.get("pages_seen", 0)

                logger.info("Resuming site crawl from checkpoint", extra={
                    "document_id": document_id,
                    "checkpoint_age_sec": round(age.total_seconds()),
                    "dispatched": dispatched,
                })
            except Exception as ckpt_err:
                logger.warning("Discarding invalid/stale checkpoint — starting fresh", extra={
                    "document_id": document_id,
                    "reason": str(ckpt_err)[:300],
                })
                restored_state = None

    _latest_crawl4ai_state: dict | None = None

    async def _on_state_change(state: dict) -> None:
        nonlocal _latest_crawl4ai_state
        _latest_crawl4ai_state = state

    downloaded_file_urls: set[str] = set()

    def _on_page(page: CrawledPage) -> None:
        nonlocal dispatched, skipped, errors, pages_seen
        pages_seen += 1

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
                    original_filename=f"{page.title[:150]}.md",
                    file_size_bytes=len(md_bytes),
                    title=page.title[:200],
                    status="pending",
                    source_hash=source_hash,
                    source_container=url,
                    source_path=page.url,
                    tenant_id=site_tenant_id,
                )
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
                    logger.warning("Failed to dispatch ingest task for page", extra={
                        "child_document_id": doc.id, "error": str(task_exc)[:200],
                    })

                dispatched += 1

        except Exception as exc:
            errors += 1
            logger.warning("Failed to persist crawled page — skipping", extra={
                "url": page.url, "title": page.title[:100],
                "error_type": type(exc).__name__,
                "error": str(exc)[:300],
            })
            return

        _save_progress()

    def _on_file(crawled_file: CrawledFile) -> None:
        nonlocal files_dispatched, errors
        try:
            if crawled_file.url in downloaded_file_urls:
                return
            downloaded_file_urls.add(crawled_file.url)

            if not crawled_file.local_path or not os.path.isfile(crawled_file.local_path):
                return

            with open(crawled_file.local_path, "rb") as f:
                file_bytes = f.read()

            source_hash = hashlib.sha256(file_bytes).hexdigest()
            filename = crawled_file.url.rsplit("/", 1)[-1][:200]
            fmt = crawled_file.format

            with Session(engine) as s:
                existing = s.execute(
                    sa_select(Document).where(
                        Document.source_hash == source_hash,
                        Document.product_id == product_id,
                        Document.firmware_version_id == firmware_version_id,
                    ).limit(1)
                ).scalar_one_or_none()
                if existing is not None:
                    return

                doc = Document(
                    product_id=product_id,
                    firmware_version_id=firmware_version_id,
                    format=fmt,
                    original_filename=filename,
                    file_size_bytes=len(file_bytes),
                    title=filename,
                    status="pending",
                    source_hash=source_hash,
                    source_container=url,
                    source_path=crawled_file.url,
                    tenant_id=site_tenant_id,
                )
                s.add(doc)
                s.flush()

                ext = crawled_file.extension or ".bin"
                s3_key = f"documents/{doc.id}/source{ext}"
                content_type = "application/pdf" if ext == ".pdf" else "application/octet-stream"
                upload_file(s3_key, file_bytes, content_type=content_type)
                doc.s3_key = s3_key
                s.commit()

                try:
                    task = ingest_document_task.delay(doc.id)
                    doc.celery_task_id = task.id
                    s.commit()
                except Exception as task_exc:
                    logger.warning("Failed to dispatch ingest task for file", extra={
                        "child_document_id": doc.id, "error": str(task_exc)[:200],
                    })

                files_dispatched += 1

        except Exception as exc:
            errors += 1
            logger.warning("Failed to persist downloaded file — skipping", extra={
                "url": crawled_file.url,
                "error_type": type(exc).__name__,
                "error": str(exc)[:300],
            })
        finally:
            if crawled_file.local_path and os.path.isfile(crawled_file.local_path):
                try:
                    os.unlink(crawled_file.local_path)
                except OSError:
                    pass

    def _save_progress() -> None:
        try:
            with Session(engine) as s:
                ph = s.get(Document, document_id)
                if ph:
                    total = dispatched + files_dispatched
                    stage = f"crawling ({pages_seen} pages, {total} queued)"
                    if errors:
                        stage += f", {errors} errors"
                    ph.progress_stage = stage
                    if pages_seen == 1:
                        ph.title = f"Site: {url}"
                    ph.crawl_checkpoint = {
                        "version": _CHECKPOINT_VERSION,
                        "saved_at": datetime.now(timezone.utc).isoformat(),
                        "crawl4ai_state": _latest_crawl4ai_state,
                        "dispatched": dispatched,
                        "files_dispatched": files_dispatched,
                        "skipped": skipped,
                        "errors": errors,
                        "pages_seen": pages_seen,
                    }
                    s.commit()
        except Exception:
            pass

    _elapsed_before_crawl = time.perf_counter() - t0
    _remaining = max(60, _deadline_seconds - int(_elapsed_before_crawl))
    _max_seconds = min(_max_seconds_cfg, _remaining)

    try:
        try:
            loop = asyncio.get_event_loop()
            _file_cb = _on_file if download_resources else None
            crawl_result = loop.run_until_complete(
                crawl_site(
                    url,
                    max_depth=_max_depth,
                    max_pages=_max_pages,
                    max_seconds=_max_seconds,
                    page_callback=_on_page,
                    file_callback=_file_cb,
                    on_state_change=_on_state_change,
                    resume_state=restored_state,
                )
            )
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                crawl_result = loop.run_until_complete(
                    crawl_site(
                        url,
                        max_depth=_max_depth,
                        max_pages=_max_pages,
                        max_seconds=_max_seconds,
                        page_callback=_on_page,
                        file_callback=_file_cb,
                        on_state_change=_on_state_change,
                        resume_state=restored_state,
                    )
                )
            finally:
                loop.close()

    except SoftTimeLimitExceeded:
        _save_progress()
        total = dispatched + files_dispatched
        if self.request.retries < self.max_retries:
            with Session(engine) as session:
                ph = session.get(Document, document_id)
                if ph:
                    ph.progress_stage = f"timeout, resuming... ({total} items so far)"
                    session.commit()
            logger.warning("Site crawl hit Celery time limit — resuming from checkpoint", extra={
                "url": url, "document_id": document_id,
                "dispatched": dispatched, "files_dispatched": files_dispatched,
                "retry": self.request.retries + 1,
            })
            raise self.retry(countdown=10)
        else:
            with Session(engine) as session:
                ph = session.get(Document, document_id)
                if ph:
                    if total > 0:
                        ph.status = "ready"
                        ph.progress_stage = "done"
                        ph.error_message = f"Crawl stopped after max retries. Processed {total} items."
                    else:
                        ph.status = "error"
                        ph.progress_stage = ""
                        ph.error_message = "Crawl exceeded all retry attempts without results."
                    ph.progress_percent = 100
                    session.commit()
            return {"status": "error", "error": "max_retries_exhausted"}

    except Exception as exc:
        with Session(engine) as session:
            placeholder = session.get(Document, document_id)
            if placeholder:
                placeholder.status = "error"
                placeholder.error_message = f"Crawl failed: {type(exc).__name__}: {str(exc)[:1900]}"
                placeholder.progress_stage = ""
                session.commit()

        logger.error("Site crawl failed", extra={
            "url": url, "document_id": document_id,
            "error_type": type(exc).__name__,
        }, exc_info=True)
        raise self.retry(exc=exc)

    if crawl_result.stopped_by_time and self.request.retries < self.max_retries:
        _save_progress()
        total = dispatched + files_dispatched
        logger.info("Site crawl auto-continuing via retry", extra={
            "url": url, "document_id": document_id,
            "retry": self.request.retries + 1,
            "dispatched": dispatched, "files_dispatched": files_dispatched,
            "pages_seen": pages_seen,
        })
        with Session(engine) as session:
            ph = session.get(Document, document_id)
            if ph:
                ph.progress_stage = f"restarting ({total} items so far, retry {self.request.retries + 1})"
                session.commit()
        raise self.retry(countdown=10)

    with Session(engine) as session:
        placeholder = session.get(Document, document_id)
        if placeholder:
            duration_ms = round((time.perf_counter() - t0) * 1000, 1)
            total = dispatched + files_dispatched
            placeholder.progress_percent = 100
            placeholder.ingest_duration_ms = duration_ms
            placeholder.total_chunks = total
            placeholder.crawl_checkpoint = None

            from urllib.parse import urlparse as _urlparse
            domain = _urlparse(url).netloc
            placeholder.title = f"{domain} ({crawl_result.pages_crawled} pages, {crawl_result.files_found} files)"

            if total == 0:
                placeholder.status = "error"
                placeholder.progress_stage = "done"
                if crawl_result.pages_crawled == 0:
                    placeholder.error_message = (
                        "Crawl returned 0 pages. The site may require authentication "
                        "or the URL may be invalid."
                    )
                else:
                    placeholder.error_message = (
                        f"No documents created from {pages_seen} crawled pages "
                        f"({skipped} empty, {errors} errors)."
                    )
            elif errors > total:
                placeholder.status = "error"
                placeholder.progress_stage = "done"
                placeholder.error_message = (
                    f"Too many storage failures: {errors} errors vs {total} documents."
                )
            elif errors > 0:
                placeholder.status = "ready"
                placeholder.progress_stage = "done"
                placeholder.error_message = (
                    f"Partial failures: {errors} items could not be saved."
                )
            else:
                placeholder.status = "ready"
                placeholder.progress_stage = "done"
                placeholder.error_message = None
            session.commit()

    duration_ms = round((time.perf_counter() - t0) * 1000, 1)
    total = dispatched + files_dispatched
    logger.info("Celery ingest_site_task completed", extra={
        "url": url, "document_id": document_id,
        "pages_crawled": crawl_result.pages_crawled,
        "files_found": crawl_result.files_found,
        "dispatched": dispatched, "files_dispatched": files_dispatched,
        "skipped": skipped, "errors": errors,
        "duration_ms": duration_ms,
    })
    return {
        "status": "ok",
        "url": url,
        "document_id": document_id,
        "pages_crawled": crawl_result.pages_crawled,
        "files_found": crawl_result.files_found,
        "dispatched": dispatched,
        "files_dispatched": files_dispatched,
        "skipped": skipped,
        "errors": errors,
        "duration_ms": duration_ms,
    }


@celery.task(name="ingest_github", bind=True, max_retries=10, default_retry_delay=10,
             soft_time_limit=7200, time_limit=7500)
def ingest_github_task(self, document_id: int, branch: str = "main"):
    """Background task: import files from a public GitHub repository.

    Receives the placeholder Document id (format='github').
    For every matching file the task:
      1. Downloads the file via raw.githubusercontent.com
      2. Creates a child Document in the DB (status='pending')
      3. Uploads content to S3
      4. Dispatches ``ingest_document_task`` for that child

    Supports crash recovery via crawl_checkpoint (set of processed paths).
    """
    import asyncio
    from datetime import datetime, timezone, timedelta
    from app.models import Document
    from app.ingestion.converters.github import crawl_github, parse_github_url, GitHubFile
    from app.s3 import upload_file

    _CHECKPOINT_VERSION = 1
    _CHECKPOINT_TTL = timedelta(hours=24)

    t0 = time.perf_counter()
    engine = _get_sync_engine()
    _processed_paths: set[str] = set()

    with Session(engine) as session:
        placeholder = session.get(Document, document_id)
        if placeholder is None:
            logger.error("Placeholder document not found", extra={"document_id": document_id})
            return {"status": "error", "error": "Placeholder not found"}

        url = placeholder.source_path
        product_id = placeholder.product_id
        firmware_version_id = placeholder.firmware_version_id
        gh_tenant_id = placeholder.tenant_id
        _set_tenant_log_context(gh_tenant_id, session)

        placeholder.status = "processing"
        placeholder.processing_started_at = datetime.now(timezone.utc)
        placeholder.progress_stage = "fetching repository tree"
        placeholder.progress_percent = 0
        session.commit()

    try:
        owner, repo, url_branch = parse_github_url(url)
    except ValueError as exc:
        with Session(engine) as session:
            ph = session.get(Document, document_id)
            if ph:
                ph.status = "error"
                ph.error_message = str(exc)
                ph.progress_stage = ""
                session.commit()
        return {"status": "error", "error": str(exc)}

    effective_branch = url_branch or branch

    logger.info("Celery ingest_github_task started", extra={
        "url": url, "document_id": document_id, "task_id": self.request.id,
        "owner": owner, "repo": repo, "branch": effective_branch,
    })

    dispatched = 0
    skipped = 0
    errors = 0

    with Session(engine) as session:
        placeholder = session.get(Document, document_id)
        ckpt = placeholder.crawl_checkpoint if placeholder else None
        if ckpt and isinstance(ckpt, dict):
            try:
                if ckpt.get("version") != _CHECKPOINT_VERSION:
                    raise ValueError(f"unknown checkpoint version: {ckpt.get('version')}")
                saved_at = datetime.fromisoformat(ckpt["saved_at"])
                age = datetime.now(timezone.utc) - saved_at
                if age > _CHECKPOINT_TTL:
                    raise ValueError(f"checkpoint too old: {age}")
                _processed_paths.update(ckpt.get("processed_paths", []))
                dispatched = ckpt.get("dispatched", 0)
                skipped = ckpt.get("skipped", 0)
                errors = ckpt.get("errors", 0)
                logger.info("Resuming GitHub import from checkpoint", extra={
                    "document_id": document_id,
                    "processed_files": len(_processed_paths),
                    "checkpoint_age_sec": round(age.total_seconds()),
                    "dispatched": dispatched,
                })
            except Exception as ckpt_err:
                logger.warning("Discarding invalid/stale GitHub checkpoint — starting fresh", extra={
                    "document_id": document_id,
                    "reason": str(ckpt_err)[:300],
                })
                _processed_paths.clear()

    def _on_file(gh_file: GitHubFile) -> None:
        nonlocal dispatched, skipped, errors

        if gh_file.path in _processed_paths:
            return

        try:
            if not gh_file.local_path or not os.path.isfile(gh_file.local_path):
                errors += 1
                return

            with open(gh_file.local_path, "rb") as f:
                file_bytes = f.read()

            if not file_bytes:
                skipped += 1
                return

            source_hash = hashlib.sha256(file_bytes).hexdigest()
            filename = gh_file.path.rsplit("/", 1)[-1][:200]
            fmt = gh_file.format

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
                    format=fmt,
                    original_filename=filename,
                    file_size_bytes=len(file_bytes),
                    title=gh_file.path[:200],
                    status="pending",
                    source_hash=source_hash,
                    source_container=url,
                    source_path=gh_file.url,
                    tenant_id=gh_tenant_id,
                )
                s.add(doc)
                s.flush()

                ext = os.path.splitext(gh_file.path)[1] or ".bin"
                s3_key = f"documents/{doc.id}/source{ext}"
                content_type = "application/pdf" if ext == ".pdf" else "application/octet-stream"
                upload_file(s3_key, file_bytes, content_type=content_type)
                doc.s3_key = s3_key
                s.commit()

                try:
                    task = ingest_document_task.delay(doc.id)
                    doc.celery_task_id = task.id
                    s.commit()
                except Exception as task_exc:
                    logger.warning("Failed to dispatch ingest task for GitHub file", extra={
                        "child_document_id": doc.id, "error": str(task_exc)[:200],
                    })

                dispatched += 1

            _processed_paths.add(gh_file.path)

        except Exception as exc:
            errors += 1
            _processed_paths.add(gh_file.path)
            logger.warning("Failed to persist GitHub file — skipping", extra={
                "path": gh_file.path,
                "error_type": type(exc).__name__,
                "error": str(exc)[:300],
            })
        finally:
            if gh_file.local_path and os.path.isfile(gh_file.local_path):
                try:
                    os.unlink(gh_file.local_path)
                except OSError:
                    pass

        try:
            with Session(engine) as s:
                ph = s.get(Document, document_id)
                if ph:
                    ph.progress_stage = f"importing ({dispatched} files queued, {skipped} skipped)"
                    if errors:
                        ph.progress_stage += f", {errors} errors"
                    if len(_processed_paths) % 10 == 0:
                        ph.crawl_checkpoint = {
                            "version": _CHECKPOINT_VERSION,
                            "saved_at": datetime.now(timezone.utc).isoformat(),
                            "processed_paths": list(_processed_paths),
                            "dispatched": dispatched,
                            "skipped": skipped,
                            "errors": errors,
                        }
                    s.commit()
        except Exception:
            pass

    _eff_max_files = settings.github_max_files or settings.crawl_max_pages

    try:
        try:
            loop = asyncio.get_event_loop()
            crawl_result = loop.run_until_complete(
                crawl_github(
                    owner=owner,
                    repo=repo,
                    branch=effective_branch,
                    token=settings.github_api_token,
                    max_files=_eff_max_files,
                    max_file_size_mb=settings.github_max_file_size_mb,
                    file_callback=_on_file,
                )
            )
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                crawl_result = loop.run_until_complete(
                    crawl_github(
                        owner=owner,
                        repo=repo,
                        branch=effective_branch,
                        token=settings.github_api_token,
                        max_files=_eff_max_files,
                        max_file_size_mb=settings.github_max_file_size_mb,
                        file_callback=_on_file,
                    )
                )
            finally:
                loop.close()

    except SoftTimeLimitExceeded:
        with Session(engine) as session:
            ph = session.get(Document, document_id)
            if ph:
                ph.crawl_checkpoint = {
                    "version": _CHECKPOINT_VERSION,
                    "saved_at": datetime.now(timezone.utc).isoformat(),
                    "processed_paths": list(_processed_paths),
                    "dispatched": dispatched,
                    "skipped": skipped,
                    "errors": errors,
                }
                ph.progress_stage = f"timeout, resuming... ({dispatched} files so far)"
                session.commit()
        logger.warning("GitHub import hit Celery time limit — resuming from checkpoint", extra={
            "url": url, "document_id": document_id,
            "dispatched": dispatched, "retry": self.request.retries + 1,
        })
        raise self.retry(countdown=10)

    except Exception as exc:
        with Session(engine) as session:
            ph = session.get(Document, document_id)
            if ph:
                ph.status = "error"
                ph.error_message = f"GitHub import failed: {type(exc).__name__}: {str(exc)[:1900]}"
                ph.progress_stage = ""
                session.commit()

        logger.error("GitHub crawl failed", extra={
            "url": url, "document_id": document_id,
            "error_type": type(exc).__name__,
        }, exc_info=True)
        raise self.retry(exc=exc)

    with Session(engine) as session:
        ph = session.get(Document, document_id)
        if ph:
            duration_ms = round((time.perf_counter() - t0) * 1000, 1)
            ph.progress_percent = 100
            ph.ingest_duration_ms = duration_ms
            ph.total_chunks = dispatched
            ph.crawl_checkpoint = None
            ph.title = f"{owner}/{repo} ({crawl_result.files_downloaded} files)"

            if dispatched == 0:
                ph.status = "error"
                ph.progress_stage = "done"
                if crawl_result.files_found == 0:
                    ph.error_message = (
                        f"No supported files found in {owner}/{repo} ({effective_branch}). "
                        f"Check that the repository contains .md, .yaml, .json, or other supported files."
                    )
                else:
                    ph.error_message = (
                        f"No documents created from {crawl_result.files_found} files "
                        f"({skipped} duplicates/empty, {errors} errors)."
                    )
            elif errors > dispatched:
                ph.status = "error"
                ph.progress_stage = "done"
                ph.error_message = f"Too many failures: {errors} errors vs {dispatched} documents."
            elif errors > 0:
                ph.status = "ready"
                ph.progress_stage = "done"
                ph.error_message = f"Partial failures: {errors} items could not be saved."
            else:
                ph.status = "ready"
                ph.progress_stage = "done"
                ph.error_message = None
            session.commit()

    duration_ms = round((time.perf_counter() - t0) * 1000, 1)
    logger.info("Celery ingest_github_task completed", extra={
        "url": url, "document_id": document_id,
        "owner": owner, "repo": repo, "branch": effective_branch,
        "files_found": crawl_result.files_found,
        "files_downloaded": crawl_result.files_downloaded,
        "dispatched": dispatched, "skipped": skipped, "errors": errors,
        "duration_ms": duration_ms,
    })
    return {
        "status": "ok",
        "url": url,
        "document_id": document_id,
        "repo": f"{owner}/{repo}",
        "branch": effective_branch,
        "files_found": crawl_result.files_found,
        "files_downloaded": crawl_result.files_downloaded,
        "dispatched": dispatched,
        "skipped": skipped,
        "errors": errors,
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
        parse_confluence_url, get_page_with_children_toc,
    )
    from app.s3 import upload_file

    t0 = time.perf_counter()
    engine = _get_sync_engine()

    confluence_auth = None

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

        if doc.source_container:
            parent = session.execute(
                sa_select(Document).where(
                    Document.source_path == doc.source_container,
                    Document.format == "confluence",
                ).limit(1)
            ).scalar_one_or_none()
            if parent and parent.crawl_checkpoint and isinstance(parent.crawl_checkpoint, dict):
                auth_token = parent.crawl_checkpoint.get("auth")
                if auth_token:
                    from app.utils.crypto import decrypt_credentials
                    confluence_auth = decrypt_credentials(auth_token)

        doc.status = "processing"
        doc.processing_started_at = datetime.now(timezone.utc)
        doc.progress_stage = "fetching"
        doc.progress_percent = 0
        session.commit()

    logger.info("Celery reingest_confluence_page_task started",
                extra={"url": url, "document_id": document_id,
                       "has_auth": confluence_auth is not None})

    try:
        base_url, _space_key, page_id = parse_confluence_url(url, auth=confluence_auth)
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
        title, markdown = get_page_with_children_toc(
            base_url, _space_key, page_id, auth=confluence_auth,
        )
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


def _redispatch_document(doc) -> str | None:
    """Dispatch the appropriate Celery ingest task for a document.

    Returns the new celery_task_id, or None if the format is unknown.
    """
    if doc.format == "confluence":
        task = ingest_confluence_task.delay(document_id=doc.id)
    elif doc.format == "site":
        task = ingest_site_task.delay(document_id=doc.id)
    elif doc.format == "url":
        task = ingest_single_url_task.delay(document_id=doc.id)
    elif doc.format == "github":
        from app.ingestion.converters.github import parse_github_url
        _branch = "main"
        try:
            _, _, url_branch = parse_github_url(doc.source_path)
            if url_branch:
                _branch = url_branch
        except ValueError:
            pass
        task = ingest_github_task.delay(document_id=doc.id, branch=_branch)
    else:
        task = ingest_document_task.delay(doc.id)
    return task.id


@celery.task(name="check_stale_documents", bind=True)
def check_stale_documents_task(self):
    """Periodic task: reset documents stuck in 'processing' for too long
    and immediately re-dispatch them (single-step recovery)."""
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

        rescued = 0
        for doc in stale_docs:
            started = doc.processing_started_at or doc.uploaded_at
            doc.error_message = None
            doc.progress_percent = 0
            doc.progress_stage = ""
            doc.status = "pending"
            task_id = _redispatch_document(doc)
            if task_id:
                doc.celery_task_id = task_id
                rescued += 1
            logger.warning(
                "Stale document reset and re-queued",
                extra={
                    "event": "document_stale_reset",
                    "document_id": doc.id,
                    "title": doc.title,
                    "format": doc.format,
                    "processing_started_at": str(started),
                    "re_queued": task_id is not None,
                },
            )

        if stale_docs:
            session.commit()
            logger.info(
                "Stale documents reset",
                extra={"count": len(stale_docs), "re_queued": rescued},
            )


@celery.task(name="rescue_orphaned_documents", bind=True)
def rescue_orphaned_documents_task(self):
    """Periodic task: re-queue documents whose Celery tasks were lost.

    Covers two cases:
    1. 'pending' documents older than 5 minutes (task never started or lost).
    2. 'processing' documents whose celery_task_id is no longer known to
       Redis (worker restarted mid-task) and have been stuck for > 5 min.

    Handles all document formats including confluence, site, url, and github.
    Processes up to 200 per run to avoid overloading the queue.
    """
    from celery.result import AsyncResult
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import select, func as sa_func
    from app.models import Document

    _THRESHOLD_MINUTES = 5
    _BATCH_LIMIT = 200
    _LOST_STATES = {"PENDING", "REVOKED"}

    engine = _get_sync_engine()
    threshold = datetime.now(timezone.utc) - timedelta(minutes=_THRESHOLD_MINUTES)

    rescued_count = 0

    with Session(engine) as session:
        pending_orphans = session.execute(
            select(Document).where(
                Document.status == "pending",
                Document.uploaded_at < threshold,
            ).limit(_BATCH_LIMIT)
        ).scalars().all()

        effective_started = sa_func.coalesce(
            Document.processing_started_at, Document.uploaded_at,
        )
        processing_candidates = session.execute(
            select(Document).where(
                Document.status == "processing",
                effective_started < threshold,
            ).limit(_BATCH_LIMIT)
        ).scalars().all()

        processing_orphans = []
        for doc in processing_candidates:
            if not doc.celery_task_id:
                processing_orphans.append(doc)
                continue
            result = AsyncResult(doc.celery_task_id, app=celery)
            if result.state in _LOST_STATES:
                processing_orphans.append(doc)

        all_orphans = pending_orphans + processing_orphans
        if not all_orphans:
            return

        for doc in all_orphans:
            prev_status = doc.status
            doc.status = "pending"
            doc.progress_percent = 0
            doc.progress_stage = ""
            doc.error_message = None
            task_id = _redispatch_document(doc)
            if task_id:
                doc.celery_task_id = task_id
                rescued_count += 1
            logger.info(
                "Rescued orphaned document",
                extra={
                    "event": "rescue_orphaned_document",
                    "document_id": doc.id,
                    "title": doc.title,
                    "format": doc.format,
                    "prev_status": prev_status,
                    "new_task_id": task_id,
                },
            )

        session.commit()

    logger.info(
        "Rescued orphaned documents",
        extra={
            "event": "rescue_orphaned_documents",
            "count": rescued_count,
            "from_pending": len(pending_orphans),
            "from_processing": len(processing_orphans),
        },
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


@celery.task(name="run_rag_evaluation", bind=True, soft_time_limit=600, time_limit=660)
def run_rag_evaluation_task(self, run_id: int):
    """Background task: execute full RAG evaluation pipeline."""
    from app.admin.rag_eval import run_full_evaluation
    logger.info("Celery run_rag_evaluation_task started", extra={"run_id": run_id, "task_id": self.request.id})
    try:
        run_full_evaluation(run_id)
    except Exception as exc:
        logger.error("run_rag_evaluation_task failed", extra={"run_id": run_id, "error_type": type(exc).__name__}, exc_info=True)
        from app.models import RagEvalRun
        from datetime import datetime, timezone
        engine = _get_sync_engine()
        with Session(engine) as session:
            run = session.get(RagEvalRun, run_id)
            if run and run.status == "running":
                run.status = "failed"
                run.error_message = f"Task crashed: {exc}"
                run.finished_at = datetime.now(timezone.utc)
                session.commit()
        raise


@celery.task(name="delete_product", bind=True, acks_late=False)
def delete_product_task(self, product_id: int):
    """Delete all documents (S3 files + DB rows) of a product, then the product itself.

    Runs as a background Celery task so the API can return 202 immediately.
    Documents are processed in batches to avoid holding a huge transaction.
    """
    from sqlalchemy import select as sa_sel, func as sa_func, delete as sa_del
    from app.models import Product, Document, Chunk
    from app.s3 import delete_file

    BATCH_SIZE = 500
    engine = _get_sync_engine()

    with Session(engine) as session:
        total = session.scalar(
            sa_sel(sa_func.count()).select_from(Document).where(Document.product_id == product_id)
        ) or 0

        task_ids: list[str] = []
        active_docs = session.execute(
            sa_sel(Document.celery_task_id).where(
                Document.product_id == product_id,
                Document.status.in_(["pending", "processing"]),
                Document.celery_task_id.isnot(None),
            )
        ).scalars().all()
        task_ids = [tid for tid in active_docs if tid]

    if task_ids:
        try:
            for tid in task_ids:
                celery.control.revoke(tid, terminate=True)
        except Exception:
            logger.warning("delete_product: failed to revoke active tasks",
                           extra={"product_id": product_id, "task_ids": task_ids})

    deleted_count = 0
    try:
        while True:
            with Session(engine) as session:
                docs = session.execute(
                    sa_sel(Document).where(Document.product_id == product_id).limit(BATCH_SIZE)
                ).scalars().all()
                if not docs:
                    break

                for doc in docs:
                    for key in (doc.s3_key, doc.converted_s3_key):
                        if key:
                            try:
                                delete_file(key)
                            except Exception as e:
                                logger.warning("delete_product: S3 cleanup failed",
                                               extra={"s3_key": key, "error": str(e)})

                    session.execute(sa_del(Chunk).where(Chunk.document_id == doc.id))
                    session.delete(doc)

                session.commit()
                deleted_count += len(docs)

        with Session(engine) as session:
            product = session.get(Product, product_id)
            if product:
                session.delete(product)
                session.commit()

        logger.info("delete_product: completed",
                     extra={"product_id": product_id, "documents_deleted": deleted_count, "total": total})
    except Exception:
        logger.error("delete_product: failed",
                      extra={"product_id": product_id, "deleted_so_far": deleted_count},
                      exc_info=True)
        with Session(engine) as session:
            product = session.get(Product, product_id)
            if product and product.sync_status == "deleting":
                product.sync_status = "idle"
                session.commit()
        raise


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


@celery.task(name="backfill_chunk_languages", bind=True)
def backfill_chunk_languages_task(self):
    """One-shot task: detect language for documents missing it and
    backfill ``chunks.language`` so the ``tsv_lang`` trigger fires.
    """
    from sqlalchemy import select as sa_select, update as sa_update
    from app.models import Document, Chunk
    from app.ingestion.lang_detect import detect_language

    engine = _get_sync_engine()
    updated_docs = 0
    updated_chunks = 0
    batch_size = 100

    with Session(engine) as session:
        docs_no_lang = session.execute(
            sa_select(Document.id).where(
                Document.status == "ready",
                Document.detected_language.is_(None),
            )
        ).scalars().all()

        docs_with_lang_but_no_chunks = session.execute(
            sa_select(Document.id).where(
                Document.status == "ready",
                Document.detected_language.isnot(None),
            ).where(
                ~Document.id.in_(
                    sa_select(Chunk.document_id)
                    .where(Chunk.language.isnot(None))
                    .distinct()
                )
            )
        ).scalars().all()

    doc_ids_detect = list(docs_no_lang)
    doc_ids_propagate = list(docs_with_lang_but_no_chunks)

    logger.info("backfill_chunk_languages: starting",
                extra={"docs_need_detection": len(doc_ids_detect),
                       "docs_need_propagation": len(doc_ids_propagate)})

    for offset in range(0, len(doc_ids_detect), batch_size):
        batch_ids = doc_ids_detect[offset : offset + batch_size]
        with Session(engine) as session:
            for doc_id in batch_ids:
                first_chunk = session.execute(
                    sa_select(Chunk.content)
                    .where(Chunk.document_id == doc_id)
                    .order_by(Chunk.chunk_index)
                    .limit(1)
                ).scalar_one_or_none()

                if not first_chunk:
                    continue

                lang = detect_language(first_chunk)

                session.execute(
                    sa_update(Document)
                    .where(Document.id == doc_id)
                    .values(detected_language=lang)
                )
                cnt = session.execute(
                    sa_update(Chunk)
                    .where(Chunk.document_id == doc_id)
                    .values(language=lang)
                ).rowcount
                updated_docs += 1
                updated_chunks += cnt

            session.commit()

    for offset in range(0, len(doc_ids_propagate), batch_size):
        batch_ids = doc_ids_propagate[offset : offset + batch_size]
        with Session(engine) as session:
            for doc_id in batch_ids:
                lang = session.execute(
                    sa_select(Document.detected_language)
                    .where(Document.id == doc_id)
                ).scalar_one_or_none()

                if not lang:
                    continue

                cnt = session.execute(
                    sa_update(Chunk)
                    .where(Chunk.document_id == doc_id)
                    .values(language=lang)
                ).rowcount
                updated_docs += 1
                updated_chunks += cnt

            session.commit()

        logger.info("backfill_chunk_languages: progress",
                    extra={"docs_done": updated_docs, "chunks_done": updated_chunks,
                           "total_docs": len(doc_ids_detect)})

    logger.info("backfill_chunk_languages: completed",
                extra={"docs_updated": updated_docs, "chunks_updated": updated_chunks})


# ---------------------------------------------------------------------------
# API Lifecycle Analysis Tasks
# ---------------------------------------------------------------------------

@celery.task(name="analyze_api_lifecycle", bind=True, max_retries=1,
             soft_time_limit=600, time_limit=660)
def analyze_api_lifecycle_task(self, document_id: int):
    """Analyze a single document and extract its API lifecycle."""
    from datetime import datetime, timezone as _tz
    from app.models import Base, Document, ApiLifecycle, DocIssueAnnotation, Chunk
    from app.ingestion.lifecycle_analyzer import analyze_document_lifecycle_sync
    from app.billing.usage_writer import write_usage_log_sync
    from app.billing.pricing import calculate_llm_cogs, calculate_llm_charge

    if not settings.lifecycle_analysis_enabled:
        return {"status": "skipped", "reason": "lifecycle_analysis_enabled=False"}

    engine = _get_sync_engine()

    with Session(engine) as session:
        doc = session.get(Document, document_id)
        if doc is None:
            return {"status": "error", "error": "Document not found"}
        if doc.status != "ready":
            return {"status": "skipped", "reason": f"Document status is '{doc.status}', not 'ready'"}

        _set_tenant_log_context(doc.tenant_id, session)

        api_types = {"api_reference", "protocol", "model_schema"}
        chunk_types = session.execute(
            sa_select(Chunk.doc_type).where(Chunk.document_id == document_id).distinct()
        ).scalars().all()
        if not any(ct in api_types for ct in chunk_types):
            logger.info("Skipping lifecycle analysis: no API-related chunks",
                        extra={"document_id": document_id, "chunk_types": list(chunk_types)})
            return {"status": "skipped", "reason": "No API-related doc_types"}

        doc.lifecycle_status = "processing"
        session.commit()

        try:
            result, doc_issues = analyze_document_lifecycle_sync(document_id, session)

            has_content = bool(result.phases)
            if has_content:
                effective_status = "ready"
                error_msg = None
            else:
                effective_status = "error"
                error_msg = "No API lifecycle phases extracted after all retries"
                if result.validation_issues:
                    error_msg += f": {result.validation_issues[0].get('error', '')}"

            existing = session.execute(
                sa_select(ApiLifecycle).where(ApiLifecycle.document_id == document_id)
            ).scalar_one_or_none()

            if existing:
                existing.phases = result.phases
                existing.unique_patterns = result.unique_patterns
                existing.dependency_chains = result.dependency_chains
                existing.code_skeleton = result.code_skeleton
                existing.validation_issues = result.validation_issues
                existing.validation_retries = result.validation_retries
                existing.prompt_tokens = result.usage.prompt_tokens
                existing.completion_tokens = result.usage.completion_tokens
                existing.analysis_ms = result.usage.analysis_ms
                existing.model = result.usage.model
                existing.status = effective_status
                existing.error_message = error_msg
                existing.updated_at = datetime.now(_tz.utc)
            else:
                lc = ApiLifecycle(
                    document_id=document_id,
                    product_id=doc.product_id,
                    phases=result.phases,
                    unique_patterns=result.unique_patterns,
                    dependency_chains=result.dependency_chains,
                    code_skeleton=result.code_skeleton,
                    validation_issues=result.validation_issues,
                    validation_retries=result.validation_retries,
                    prompt_tokens=result.usage.prompt_tokens,
                    completion_tokens=result.usage.completion_tokens,
                    analysis_ms=result.usage.analysis_ms,
                    model=result.usage.model,
                    status=effective_status,
                    error_message=error_msg,
                )
                session.add(lc)

            from sqlalchemy import delete as sa_delete
            session.execute(
                sa_delete(DocIssueAnnotation).where(
                    DocIssueAnnotation.document_id == document_id,
                    DocIssueAnnotation.detected_by == "lifecycle_analysis",
                )
            )
            for issue in doc_issues:
                session.add(DocIssueAnnotation(
                    document_id=document_id,
                    product_id=doc.product_id,
                    chunk_id=issue.chunk_id,
                    issue_type=issue.issue_type,
                    severity=issue.severity,
                    description=issue.description,
                    affected_entity=issue.affected_entity,
                    suggestion=issue.suggestion,
                    detected_by="lifecycle_analysis",
                ))

            doc.lifecycle_prompt_tokens = result.usage.prompt_tokens
            doc.lifecycle_completion_tokens = result.usage.completion_tokens
            doc.lifecycle_ms = result.usage.analysis_ms
            doc.lifecycle_status = effective_status
            session.commit()

            import uuid
            model = settings.lifecycle_analysis_model
            tid = str(doc.tenant_id) if doc.tenant_id else None
            req_id = f"lifecycle-{document_id}-{uuid.uuid4().hex[:8]}"
            total_billed_tokens = result.usage.prompt_tokens + result.usage.completion_tokens + result.usage.thinking_tokens
            write_usage_log_sync(
                "ingestion", "lifecycle_analysis", req_id,
                llm_provider="google", llm_model=model,
                prompt_tokens=result.usage.prompt_tokens,
                completion_tokens=result.usage.completion_tokens + result.usage.thinking_tokens,
                duration_ms=result.usage.analysis_ms,
                llm_ms=result.usage.llm_ms,
                cogs_usd=calculate_llm_cogs(model, result.usage.prompt_tokens, result.usage.completion_tokens + result.usage.thinking_tokens),
                charge_usd=calculate_llm_charge(model, result.usage.prompt_tokens, result.usage.completion_tokens + result.usage.thinking_tokens),
                tenant_id=tid,
            )

            if has_content:
                doc_lc_count = session.execute(
                    sa_select(func.count()).select_from(ApiLifecycle).where(
                        ApiLifecycle.product_id == doc.product_id,
                        ApiLifecycle.document_id.isnot(None),
                        ApiLifecycle.status == "ready",
                    )
                ).scalar() or 0

                if doc_lc_count >= 1:
                    try:
                        celery.send_task("merge_product_lifecycle", args=[doc.product_id])
                    except Exception:
                        logger.warning("Failed to dispatch merge_product_lifecycle", exc_info=True)

            logger.info("Lifecycle analysis completed",
                        extra={
                            "document_id": document_id,
                            "phases": len(result.phases),
                            "patterns": len(result.unique_patterns),
                            "doc_issues": len(doc_issues),
                            "retries": result.validation_retries,
                            "analysis_ms": result.usage.analysis_ms,
                        })
            return {"status": "ok", "document_id": document_id, "phases": len(result.phases)}

        except Exception as exc:
            doc.lifecycle_status = "error"
            session.commit()
            logger.error("Lifecycle analysis failed",
                         extra={"document_id": document_id, "error_type": type(exc).__name__},
                         exc_info=True)
            raise self.retry(exc=exc)


@celery.task(name="merge_product_lifecycle", bind=True, max_retries=1,
             soft_time_limit=300, time_limit=360)
def merge_product_lifecycle_task(self, product_id: int):
    """Merge all document-level lifecycles for a product into one."""
    from datetime import datetime, timezone as _tz
    from app.models import Base, ApiLifecycle, DocIssueAnnotation, Product
    from app.ingestion.lifecycle_analyzer import merge_product_lifecycle_sync
    from app.billing.usage_writer import write_usage_log_sync
    from app.billing.pricing import calculate_llm_cogs, calculate_llm_charge

    if not settings.lifecycle_analysis_enabled:
        return {"status": "skipped", "reason": "lifecycle_analysis_enabled=False"}

    engine = _get_sync_engine()

    with Session(engine) as session:
        product = session.get(Product, product_id)
        if product is None:
            return {"status": "error", "error": "Product not found"}

        try:
            result, doc_issues = merge_product_lifecycle_sync(product_id, session)

            existing = session.execute(
                sa_select(ApiLifecycle).where(
                    ApiLifecycle.product_id == product_id,
                    ApiLifecycle.document_id.is_(None),
                )
            ).scalar_one_or_none()

            if existing:
                existing.phases = result.phases
                existing.unique_patterns = result.unique_patterns
                existing.dependency_chains = result.dependency_chains
                existing.code_skeleton = result.code_skeleton
                existing.validation_issues = result.validation_issues
                existing.validation_retries = result.validation_retries
                existing.prompt_tokens = result.usage.prompt_tokens
                existing.completion_tokens = result.usage.completion_tokens
                existing.analysis_ms = result.usage.analysis_ms
                existing.model = result.usage.model
                existing.status = "ready"
                existing.error_message = None
                existing.updated_at = datetime.now(_tz.utc)
            else:
                lc = ApiLifecycle(
                    document_id=None,
                    product_id=product_id,
                    phases=result.phases,
                    unique_patterns=result.unique_patterns,
                    dependency_chains=result.dependency_chains,
                    code_skeleton=result.code_skeleton,
                    validation_issues=result.validation_issues,
                    validation_retries=result.validation_retries,
                    prompt_tokens=result.usage.prompt_tokens,
                    completion_tokens=result.usage.completion_tokens,
                    analysis_ms=result.usage.analysis_ms,
                    model=result.usage.model,
                    status="ready",
                )
                session.add(lc)

            session.commit()

            if result.usage.prompt_tokens > 0:
                import uuid
                model = settings.lifecycle_analysis_model
                req_id = f"lifecycle-merge-{product_id}-{uuid.uuid4().hex[:8]}"
                tenant_id = getattr(product, "tenant_id", None)
                tid = str(tenant_id) if tenant_id else None
                write_usage_log_sync(
                    "ingestion", "lifecycle_merge", req_id,
                    llm_provider="google", llm_model=model,
                    prompt_tokens=result.usage.prompt_tokens,
                    completion_tokens=result.usage.completion_tokens + result.usage.thinking_tokens,
                    duration_ms=result.usage.analysis_ms,
                    llm_ms=result.usage.llm_ms,
                    cogs_usd=calculate_llm_cogs(model, result.usage.prompt_tokens, result.usage.completion_tokens + result.usage.thinking_tokens),
                    charge_usd=calculate_llm_charge(model, result.usage.prompt_tokens, result.usage.completion_tokens + result.usage.thinking_tokens),
                    tenant_id=tid,
                )

            logger.info("Product lifecycle merge completed",
                        extra={
                            "product_id": product_id,
                            "phases": len(result.phases),
                            "analysis_ms": result.usage.analysis_ms,
                        })
            return {"status": "ok", "product_id": product_id, "phases": len(result.phases)}

        except Exception as exc:
            logger.error("Product lifecycle merge failed",
                         extra={"product_id": product_id, "error_type": type(exc).__name__},
                         exc_info=True)
            raise self.retry(exc=exc)


