"""Celery application for background document ingestion."""

import hashlib
import logging
import os
import tempfile
import time

from celery import Celery
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

celery = Celery("ipcodex", broker=settings.redis_url, backend=settings.redis_url)
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
        "ensure_usage_partitions": {"queue": "monitoring"},
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


@celery.task(name="ingest_document", bind=True, max_retries=2, default_retry_delay=30)
def ingest_document_task(self, document_id: int):
    """Background task: download file from S3, run ingestion pipeline, update DB."""
    from app.models import Base, Chunk, Product, Document, FirmwareVersion
    from app.s3 import download_file
    from app.ingestion.pipeline import ingest_from_bytes

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

        doc.status = "processing"
        session.commit()

        try:
            file_data = download_file(doc.s3_key)
        except Exception as exc:
            doc.status = "error"
            doc.error_message = f"S3 download failed: {exc}"
            session.commit()
            logger.error("S3 download failed", extra={"document_id": document_id, "s3_key": doc.s3_key, "error_type": type(exc).__name__}, exc_info=True)
            raise self.retry(exc=exc)

        ext = os.path.splitext(doc.original_filename)[1].lower() or ".bin"
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp.write(file_data)
                tmp_path = tmp.name

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


@celery.task(name="ingest_archive", bind=True, max_retries=1, default_retry_delay=30)
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
    from app.documents.archive import extract_archive, ARCHIVE_ALLOWED_EXTENSIONS

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

        archive_doc.status = "processing"
        session.commit()

        try:
            file_data = download_file(archive_doc.s3_key)
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
            product_row = Product(name=product_name, manufacturer=manufacturer)
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
                    sa_select(Document).where(Document.source_hash == entry_hash).limit(1)
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
            )
            session.add(child_doc)
            session.flush()

            s3_key = s3_key_for_document(child_doc.id, entry_filename)
            upload_file(s3_key, entry_data, "application/octet-stream")
            child_doc.s3_key = s3_key
            session.commit()

            child_ids.append(child_doc.id)

        archive_doc.status = "ready"
        archive_doc.total_chunks = 0
        archive_doc.error_message = f"Archive: extracted {len(child_ids)} files"
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
