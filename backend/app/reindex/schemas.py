"""Pydantic schemas for the reindex API."""

from datetime import datetime

from pydantic import BaseModel


class ReindexStartRequest(BaseModel):
    mode: str = "reingest"  # "reingest" | "reembed"
    product_name: str | None = None
    format_filter: str | None = None


class ReindexJobResponse(BaseModel):
    id: int
    mode: str
    status: str
    product_filter: str | None
    format_filter: str | None
    total_documents: int
    processed_documents: int
    failed_documents: int
    skipped_documents: int
    total_chunks: int
    progress_percent: float
    celery_task_id: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    heartbeat_at: datetime | None
    duration_sec: float | None
    is_stale: bool


class ReindexErrorItem(BaseModel):
    document_id: int
    document_title: str
    error: str
    timestamp: str


class ReindexJobListResponse(BaseModel):
    jobs: list[ReindexJobResponse]
    total: int
