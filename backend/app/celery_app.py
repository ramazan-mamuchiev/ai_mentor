"""Celery application for background document ingestion."""

import logging
import os
import tempfile
import time

from celery import Celery
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import settings

logger = logging.getLogger(__name__)

celery = Celery("ipcodex", broker=settings.redis_url, backend=settings.redis_url)
celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

_sync_engine = None


def _get_sync_engine():
    global _sync_engine
    if _sync_engine is None:
        _sync_engine = create_engine(settings.database_url_sync, pool_size=5, max_overflow=2)
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
