"""REST API endpoints for reindex job management."""

import logging

from fastapi import APIRouter, HTTPException, Query

from app.database import async_session
from app.reindex.schemas import (
    ReindexErrorItem,
    ReindexJobListResponse,
    ReindexJobResponse,
    ReindexStartRequest,
)
from app.reindex.service import (
    cancel_job,
    get_job_errors,
    get_job_status,
    list_jobs,
    start_reindex_job,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reindex", tags=["reindex"])


@router.post("/jobs", response_model=ReindexJobResponse, status_code=202)
async def create_reindex_job(body: ReindexStartRequest):
    """Start a new reindex job.

    Modes:
    - **reingest**: Full re-ingestion (download → convert → chunk → embed).
    - **reembed**: Only regenerate embeddings for existing chunks.

    Filters narrow the scope. Omit both for all products.
    Returns 409 if a conflicting job is already active.
    """
    async with async_session() as db:
        try:
            result = await start_reindex_job(
                db=db,
                mode=body.mode,
                product_name=body.product_name,
                format_filter=body.format_filter,
            )
        except ValueError as e:
            msg = str(e)
            if "already covers" in msg:
                raise HTTPException(status_code=409, detail=msg)
            raise HTTPException(status_code=400, detail=msg)

    return ReindexJobResponse(**result)


@router.get("/jobs", response_model=ReindexJobListResponse)
async def list_reindex_jobs(
    status: str | None = Query(default=None, description="Filter by status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """List reindex jobs with optional status filter and pagination."""
    async with async_session() as db:
        jobs, total = await list_jobs(db, status_filter=status, limit=limit, offset=offset)
    return ReindexJobListResponse(
        jobs=[ReindexJobResponse(**j) for j in jobs],
        total=total,
    )


@router.get("/jobs/{job_id}", response_model=ReindexJobResponse)
async def get_reindex_job(job_id: int):
    """Get current status and progress of a reindex job.

    Automatically detects stale jobs (heartbeat timeout exceeded).
    """
    async with async_session() as db:
        result = await get_job_status(db, job_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Reindex job not found")
    return ReindexJobResponse(**result)


@router.post("/jobs/{job_id}/cancel", response_model=ReindexJobResponse)
async def cancel_reindex_job(job_id: int):
    """Cancel a running or pending reindex job.

    The worker checks for cancellation between documents, so it may
    process one more document before actually stopping.
    """
    async with async_session() as db:
        try:
            result = await cancel_job(db, job_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    if result is None:
        raise HTTPException(status_code=404, detail="Reindex job not found")
    return ReindexJobResponse(**result)


@router.get("/jobs/{job_id}/errors", response_model=list[ReindexErrorItem])
async def get_reindex_job_errors(job_id: int):
    """Get the list of per-document errors for a reindex job.

    Returns up to 100 most recent errors.
    """
    async with async_session() as db:
        errors = await get_job_errors(db, job_id)
    return [ReindexErrorItem(**e) for e in errors]
