"""Pydantic schemas for document REST API."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


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
    source_path: str | None = None

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
    max_pages: int | None = None
    max_depth: int | None = None
    confluence_username: str | None = None
    confluence_password: str | None = None

    model_config = {"from_attributes": True}


class SiteIngestRequest(BaseModel):
    url: str
    product_name: str
    firmware_version: str = "1.0"
    manufacturer: str = ""
    max_depth: int = Field(default=5, ge=1, le=200)
    max_pages: int = Field(default=500, ge=1, le=50000)
    download_resources: bool = True

    @field_validator("url")
    @classmethod
    def _validate_url(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v

    model_config = {"from_attributes": True}


class GitHubIngestRequest(BaseModel):
    url: str
    product_name: str
    firmware_version: str = "1.0"
    manufacturer: str = ""
    branch: str = "main"

    @field_validator("url")
    @classmethod
    def _validate_url(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        if "github.com" not in v:
            raise ValueError("URL must be a GitHub repository URL")
        return v

    model_config = {"from_attributes": True}


class UrlIngestResponse(BaseModel):
    status: str
    message: str
    url: str
    product_name: str
    task_id: str | None = None
    product_id: int | None = None
    document_id: int | None = None

    model_config = {"from_attributes": True}


class DocumentMarkdownPreview(BaseModel):
    document_id: int
    title: str
    markdown: str
    size_bytes: int
    source: str  # "s3_converted" | "s3_original" | "chunks_reconstructed"


class DocumentUsageEntry(BaseModel):
    created_at: datetime
    session_id: int
    message_id: int
    heading_path: str = ""
    similarity: float = 0
    context_tokens: int = 0
    query_text: str | None = None
    query_type: str | None = None
    sub_query: str | None = None
    charge_usd: float = 0

    model_config = {"from_attributes": True}


class DocumentUsageStats(BaseModel):
    document_id: int
    title: str
    total_usages: int = 0
    unique_sessions: int = 0
    total_context_tokens: int = 0
    total_charge_usd: float = 0
    avg_similarity: float | None = None
    first_used_at: datetime | None = None
    last_used_at: datetime | None = None
    thumbs_up: int = 0
    thumbs_down: int = 0
    total_rated: int = 0
    top_headings: list[dict] = []
    recent_usages: list[DocumentUsageEntry] = []

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
    error_message: str | None = None

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
    ocr_prompt_tokens: int | None = None
    ocr_completion_tokens: int | None = None
    ocr_model: str | None = None
    detected_language: str | None = None

    extract_ms: float | None = None
    extract_model: str | None = None
    extract_prompt_tokens: int | None = None
    extract_completion_tokens: int | None = None

    search_keys_count: int = 0

    product_name: str = ""
    firmware_version: str = ""

    model_config = {"from_attributes": True}


class SearchKeyItem(BaseModel):
    key: str
    source: str


class DocumentSearchKeysResponse(BaseModel):
    document_id: int
    total_keys: int = 0
    keys: list[SearchKeyItem] = []
