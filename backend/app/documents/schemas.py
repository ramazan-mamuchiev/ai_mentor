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
    ingested_at: datetime

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
    ingested_at: datetime

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
