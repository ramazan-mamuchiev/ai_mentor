"""Reindex orchestration service.

Coordinates background reindexing jobs with:
- Duplicate protection (same scope cannot run in parallel)
- Progress tracking via DB heartbeat
- Stale job detection and auto-recovery
- Cancellation support
"""

import json
import logging
import time
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session as SyncSession

from app.config import settings
from app.models import Document, Product, ReindexJob

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = ("pending", "running")
TERMINAL_STATUSES = ("completed", "failed", "cancelled", "stale")


def _is_stale(job: ReindexJob) -> bool:
    if job.status != "running" or job.heartbeat_at is None:
        return False
    age = (datetime.now(timezone.utc) - job.heartbeat_at).total_seconds()
    return age > settings.reindex_stale_timeout_sec


def _job_to_dict(job: ReindexJob) -> dict:
    progress = 0.0
    if job.total_documents > 0:
        progress = round(
            (job.processed_documents + job.failed_documents + job.skipped_documents)
            / job.total_documents * 100, 1
        )

    duration = None
    if job.started_at:
        end = job.finished_at or datetime.now(timezone.utc)
        duration = round((end - job.started_at).total_seconds(), 1)

    return {
        "id": job.id,
        "mode": job.mode,
        "status": job.status,
        "product_filter": job.product_filter,
        "format_filter": job.format_filter,
        "total_documents": job.total_documents,
        "processed_documents": job.processed_documents,
        "failed_documents": job.failed_documents,
        "skipped_documents": job.skipped_documents,
        "total_chunks": job.total_chunks,
        "progress_percent": progress,
        "celery_task_id": job.celery_task_id,
        "error_message": job.error_message,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "heartbeat_at": job.heartbeat_at,
        "duration_sec": duration,
        "is_stale": _is_stale(job),
    }


# ── Async helpers (used by FastAPI endpoints) ────────────────────────

async def start_reindex_job(
    db: AsyncSession,
    mode: str,
    product_name: str | None = None,
    format_filter: str | None = None,
) -> dict:
    """Create a new reindex job and dispatch it to Celery.

    Raises ValueError if a conflicting job is already active.
    """
    if mode not in ("reingest", "reembed", "extract_metadata"):
        raise ValueError(f"Invalid mode '{mode}'. Must be 'reingest', 'reembed', or 'extract_metadata'.")

    conflict = await _find_conflicting_job(db, mode, product_name, format_filter)
    if conflict is not None:
        if _is_stale(conflict):
            await _mark_stale(db, conflict)
        else:
            raise ValueError(
                f"Reindex job #{conflict.id} ({conflict.status}) already covers this scope. "
                f"Cancel it first or wait for completion."
            )

    doc_query = select(Document).where(Document.status == "ready")
    product_id = None

    if product_name:
        prod_result = await db.execute(select(Product).where(Product.name == product_name))
        product = prod_result.scalar_one_or_none()
        if product is None:
            raise ValueError(f"Product '{product_name}' not found")
        product_id = product.id
        doc_query = doc_query.where(Document.product_id == product_id)

    if format_filter:
        doc_query = doc_query.where(Document.format == format_filter)

    docs_result = await db.execute(doc_query)
    doc_ids = [d.id for d in docs_result.scalars().all()]

    if not doc_ids:
        raise ValueError("No documents match the given filters")

    job = ReindexJob(
        mode=mode,
        status="pending",
        product_filter=product_name,
        format_filter=format_filter,
        total_documents=len(doc_ids),
    )
    db.add(job)
    await db.flush()

    from app.celery_app import run_reindex_job_task
    task = run_reindex_job_task.delay(job.id, doc_ids)

    job.celery_task_id = task.id
    await db.commit()

    logger.info(
        "Reindex job created",
        extra={
            "event": "reindex_job_created",
            "job_id": job.id,
            "mode": mode,
            "product_filter": product_name,
            "format_filter": format_filter,
            "total_documents": len(doc_ids),
            "celery_task_id": task.id,
        },
    )

    return _job_to_dict(job)


async def get_job_status(db: AsyncSession, job_id: int) -> dict | None:
    job = await db.get(ReindexJob, job_id)
    if job is None:
        return None
    if _is_stale(job):
        await _mark_stale(db, job)
        await db.commit()
    return _job_to_dict(job)


async def list_jobs(
    db: AsyncSession,
    status_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    query = select(ReindexJob).order_by(ReindexJob.created_at.desc())
    if status_filter:
        query = query.where(ReindexJob.status == status_filter)

    from sqlalchemy import func
    count_q = select(func.count()).select_from(ReindexJob)
    if status_filter:
        count_q = count_q.where(ReindexJob.status == status_filter)
    total = (await db.execute(count_q)).scalar() or 0

    result = await db.execute(query.limit(limit).offset(offset))
    jobs = result.scalars().all()

    for j in jobs:
        if _is_stale(j):
            await _mark_stale(db, j)
    await db.commit()

    return [_job_to_dict(j) for j in jobs], total


async def cancel_job(db: AsyncSession, job_id: int) -> dict | None:
    job = await db.get(ReindexJob, job_id)
    if job is None:
        return None

    if job.status in TERMINAL_STATUSES:
        raise ValueError(f"Job #{job_id} is already in terminal state '{job.status}'")

    job.status = "cancelled"
    job.finished_at = datetime.now(timezone.utc)
    await db.commit()

    if job.celery_task_id:
        try:
            from app.celery_app import celery
            celery.control.revoke(job.celery_task_id, terminate=True)
        except Exception:
            logger.warning("Failed to revoke Celery task", extra={"task_id": job.celery_task_id})

    logger.info(
        "Reindex job cancelled",
        extra={
            "event": "reindex_job_cancelled",
            "job_id": job_id,
            "processed": job.processed_documents,
            "total": job.total_documents,
        },
    )
    return _job_to_dict(job)


async def get_job_errors(db: AsyncSession, job_id: int) -> list[dict]:
    job = await db.get(ReindexJob, job_id)
    if job is None:
        return []
    try:
        return json.loads(job.errors_json)
    except (json.JSONDecodeError, TypeError):
        return []


async def _find_conflicting_job(
    db: AsyncSession, mode: str, product_name: str | None, format_filter: str | None
) -> ReindexJob | None:
    query = (
        select(ReindexJob)
        .where(ReindexJob.status.in_(ACTIVE_STATUSES))
        .where(ReindexJob.mode == mode)
    )
    if product_name:
        query = query.where(
            (ReindexJob.product_filter == product_name) | (ReindexJob.product_filter.is_(None))
        )
    else:
        query = query.where(ReindexJob.product_filter.is_(None))

    if format_filter:
        query = query.where(
            (ReindexJob.format_filter == format_filter) | (ReindexJob.format_filter.is_(None))
        )
    else:
        query = query.where(ReindexJob.format_filter.is_(None))

    result = await db.execute(query.limit(1))
    return result.scalar_one_or_none()


async def _mark_stale(db: AsyncSession, job: ReindexJob):
    job.status = "stale"
    job.finished_at = datetime.now(timezone.utc)
    job.error_message = (
        f"Job heartbeat stopped at {job.heartbeat_at}. "
        f"Exceeded stale timeout of {settings.reindex_stale_timeout_sec}s."
    )
    logger.warning(
        "Reindex job marked stale",
        extra={
            "event": "reindex_job_stale",
            "job_id": job.id,
            "last_heartbeat": str(job.heartbeat_at),
        },
    )


# ── Sync helpers (used by Celery worker) ─────────────────────────────

def run_reindex_sync(job_id: int, document_ids: list[int]):
    """Execute the reindex job synchronously inside the Celery worker.

    Processes documents one by one, updating progress and heartbeat in DB.
    Checks for cancellation between each document.
    """
    from app.celery_app import _get_sync_engine
    engine = _get_sync_engine()

    with SyncSession(engine) as session:
        job = session.get(ReindexJob, job_id)
        if job is None:
            logger.error("Reindex job not found", extra={"job_id": job_id})
            return

        if job.status == "cancelled":
            logger.info("Reindex job already cancelled", extra={"job_id": job_id})
            return

        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        job.heartbeat_at = datetime.now(timezone.utc)
        session.commit()

        logger.info(
            "Reindex job started",
            extra={
                "event": "reindex_job_started",
                "job_id": job_id,
                "mode": job.mode,
                "total_documents": job.total_documents,
                "product_filter": job.product_filter,
                "format_filter": job.format_filter,
            },
        )

        errors: list[dict] = []
        t0 = time.perf_counter()

        for i, doc_id in enumerate(document_ids):
            session.expire(job)
            job = session.get(ReindexJob, job_id)
            if job.status == "cancelled":
                logger.info(
                    "Reindex job cancelled mid-flight",
                    extra={"event": "reindex_job_cancelled_mid", "job_id": job_id, "at_doc": i},
                )
                return

            job.heartbeat_at = datetime.now(timezone.utc)
            session.commit()

            try:
                if job.mode == "reingest":
                    chunks = _reingest_document(session, doc_id)
                elif job.mode == "extract_metadata":
                    chunks = _extract_metadata_document(session, doc_id)
                else:
                    chunks = _reembed_document(session, doc_id)

                job.processed_documents += 1
                job.total_chunks += chunks

            except Exception as exc:
                job.failed_documents += 1
                doc = session.get(Document, doc_id)
                err_entry = {
                    "document_id": doc_id,
                    "document_title": doc.title if doc else "?",
                    "error": str(exc)[:500],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                errors.append(err_entry)
                logger.error(
                    "Reindex document failed",
                    extra={
                        "event": "reindex_doc_error",
                        "job_id": job_id,
                        "document_id": doc_id,
                        "error_type": type(exc).__name__,
                    },
                    exc_info=True,
                )

            job.errors_json = json.dumps(errors[-100:])
            job.heartbeat_at = datetime.now(timezone.utc)
            session.commit()

            if (i + 1) % 10 == 0 or i == len(document_ids) - 1:
                elapsed = round(time.perf_counter() - t0, 1)
                logger.info(
                    "Reindex progress",
                    extra={
                        "event": "reindex_progress",
                        "job_id": job_id,
                        "processed": job.processed_documents,
                        "failed": job.failed_documents,
                        "total": job.total_documents,
                        "elapsed_sec": elapsed,
                    },
                )

        job.status = "failed" if job.failed_documents == job.total_documents else "completed"
        job.finished_at = datetime.now(timezone.utc)
        if errors:
            job.error_message = f"{len(errors)} document(s) failed during reindex"
        session.commit()

        elapsed = round(time.perf_counter() - t0, 1)
        logger.info(
            "Reindex job finished",
            extra={
                "event": "reindex_job_finished",
                "job_id": job_id,
                "status": job.status,
                "processed": job.processed_documents,
                "failed": job.failed_documents,
                "skipped": job.skipped_documents,
                "total_chunks": job.total_chunks,
                "elapsed_sec": elapsed,
            },
        )


def _reingest_document(session: SyncSession, doc_id: int) -> int:
    """Re-run full ingestion pipeline for a single document. Returns chunk count."""
    import os
    import tempfile
    from app.models import Document
    from app.s3 import download_file
    from app.ingestion.pipeline import ingest_from_bytes

    doc = session.get(Document, doc_id)
    if doc is None:
        raise ValueError(f"Document {doc_id} not found")

    file_data = download_file(doc.s3_key)
    ext = os.path.splitext(doc.original_filename)[1].lower() or ".bin"

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(file_data)
        tmp_path = tmp.name

    try:
        result = ingest_from_bytes(
            session=session,
            document=doc,
            file_path=tmp_path,
            original_filename=doc.original_filename,
        )
        return result.get("chunks", 0)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _reembed_document(session: SyncSession, doc_id: int) -> int:
    """Re-generate embeddings for all chunks of a document. Returns chunk count."""
    from sqlalchemy import select as sa_select
    from app.models import Chunk, Document
    from app.ingestion.embedder import embed_texts

    doc = session.get(Document, doc_id)
    if doc is None:
        raise ValueError(f"Document {doc_id} not found")

    chunks = session.execute(
        sa_select(Chunk).where(Chunk.document_id == doc_id).order_by(Chunk.chunk_index)
    ).scalars().all()

    if not chunks:
        return 0

    contents = [c.content for c in chunks]
    embeddings = embed_texts(contents)
    for chunk, emb in zip(chunks, embeddings):
        chunk.embedding = emb
    session.commit()
    return len(chunks)


def _extract_metadata_document(session: SyncSession, doc_id: int) -> int:
    """Extract metadata (doc_type, entities) for existing chunks without re-embedding.

    Returns the number of chunks updated.
    """
    from sqlalchemy import select as sa_select
    from app.models import Chunk, Document
    from app.ingestion.metadata_extractor import extract_metadata_batch_sync

    doc = session.get(Document, doc_id)
    if doc is None:
        raise ValueError(f"Document {doc_id} not found")

    chunks = session.execute(
        sa_select(Chunk).where(Chunk.document_id == doc_id).order_by(Chunk.chunk_index)
    ).scalars().all()

    if not chunks:
        return 0

    result = extract_metadata_batch_sync([c.content for c in chunks])

    for chunk, meta in zip(chunks, result.metadata):
        chunk.doc_type = meta.doc_type
        chunk.entities = meta.entities

    doc.extract_ms = result.usage.extract_ms
    doc.extract_prompt_tokens = result.usage.prompt_tokens
    doc.extract_completion_tokens = result.usage.completion_tokens

    session.commit()
    return len(chunks)
