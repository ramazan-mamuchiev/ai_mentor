"""Pydantic schemas for document REST API."""

from datetime import datetime

from pydantic import BaseModel, Field


class IngestResponse(BaseModel):
    document_id: int
    status: str
    message: str
    task_id: str | None = None
    existing_document_id: int | None = None
    existing_document_title: str | None = None

    model_config = {"from_attributes": True}


class DocumentStatus(BaseModel):
    document_id: int
    status: str
    title: str
    format: str
    original_filename: str
    file_size_bytes: int
    total_chunks: int
    error_message: str | None = None
    uploaded_at: datetime
    indexed_at: datetime | None = None

    model_config = {"from_attributes": True}


class DocumentListItem(BaseModel):
    id: int
    title: str
    format: str
    status: str
    original_filename: str
    file_size_bytes: int
    total_chunks: int
    product_name: str = ""
    firmware_version: str = ""
    error_message: str | None = None
    uploaded_at: datetime
    indexed_at: datetime | None = None
    progress_percent: int = 0
    progress_stage: str = ""
    detected_language: str | None = None
    source_container: str | None = None

    model_config = {"from_attributes": True}


class DocumentDownload(BaseModel):
    document_id: int
    original_filename: str
    download_url: str
    expires_in_seconds: int = 900


class DeleteResponse(BaseModel):
    document_id: int
    deleted: bool
    message: str


class ArchiveFileResult(BaseModel):
    filename: str
    status: str
    document_id: int | None = None
    task_id: str | None = None
    message: str = ""


class ArchiveIngestResponse(BaseModel):
    product_name: str
    total_files: int
    accepted: int
    skipped: int
    errors: int
    files: list[ArchiveFileResult]


class UrlIngestRequest(BaseModel):
    url: str
    product_name: str
    firmware_version: str = "1.0"
    manufacturer: str = ""

    model_config = {"from_attributes": True}


class UrlIngestResponse(BaseModel):
    status: str
    message: str
    url: str
    product_name: str
    task_id: str | None = None

    model_config = {"from_attributes": True}


class DocumentDebugInfo(BaseModel):
    document_id: int
    title: str
    original_filename: str
    format: str
    status: str
    source_hash: str

    file_size_bytes: int
    uploaded_at: datetime
    indexed_at: datetime | None = None

    ingest_duration_ms: float | None = None
    read_ms: float | None = None
    convert_ms: float | None = None
    parse_ms: float | None = None
    embed_ms: float | None = None
    db_ms: float | None = None

    total_chunks: int = 0
    total_tokens: int = 0
    min_chunk_tokens: int | None = None
    max_chunk_tokens: int | None = None
    avg_chunk_tokens: float | None = None

    embedding_model: str | None = None
    embedding_dims: int | None = None
    embedding_tokens: int = 0

    rag_hit_count: int = 0
    rag_avg_similarity: float | None = None
    rag_last_used_at: datetime | None = None

    ocr_ms: float | None = None
    ocr_images_total: int | None = None
    ocr_images_success: int | None = None
    ocr_images_empty: int | None = None
    ocr_images_failed: int | None = None
    detected_language: str | None = None

    product_name: str = ""
    firmware_version: str = ""

    model_config = {"from_attributes": True}
