"""Pydantic schemas for products REST API."""

from datetime import datetime

from pydantic import BaseModel


class FormatCount(BaseModel):
    format: str
    count: int


class ProductListItem(BaseModel):
    id: int
    name: str
    manufacturer: str = ""
    model: str = ""
    category: str = ""
    slug: str = ""
    manufacturer_slug: str = ""
    created_at: datetime

    firmware_version_id: int | None = None
    version: str = ""
    display_name: str = ""

    total_documents: int = 0
    pending_documents: int = 0
    processing_documents: int = 0
    ready_documents: int = 0
    error_documents: int = 0
    cancelled_documents: int = 0

    total_file_size_bytes: int = 0
    total_chunks: int = 0
    formats: list[FormatCount] = []

    uploaded_at: datetime | None = None
    indexed_at: datetime | None = None

    progress_percent: int = 0
    progress_detail: str = ""

    model_config = {"from_attributes": True}


class ProductDetail(BaseModel):
    id: int
    name: str
    manufacturer: str = ""
    model: str = ""
    category: str = ""
    slug: str = ""
    manufacturer_slug: str = ""
    created_at: datetime
    firmware_versions: list[str] = []

    model_config = {"from_attributes": True}


class ProductUpdate(BaseModel):
    name: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    category: str | None = None


class DocumentUpdate(BaseModel):
    title: str | None = None
    product_id: int | None = None
    firmware_version_id: int | None = None


class ProductDocumentSummary(BaseModel):
    id: int
    title: str
    format: str
    file_size_bytes: int
    total_chunks: int
    status: str
    indexed_at: datetime | None = None


class ProductDebugInfo(BaseModel):
    product_id: int
    product_name: str
    total_documents: int = 0
    firmware_version_count: int = 0
    total_file_size_bytes: int = 0

    sum_ingest_duration_ms: float | None = None
    avg_ingest_duration_ms: float | None = None
    sum_read_ms: float | None = None
    sum_convert_ms: float | None = None
    sum_parse_ms: float | None = None
    sum_embed_ms: float | None = None
    sum_db_ms: float | None = None

    total_chunks: int = 0
    total_tokens: int = 0
    min_chunk_tokens: int | None = None
    max_chunk_tokens: int | None = None
    avg_chunk_tokens: float | None = None

    embedding_model: str | None = None
    total_embedding_tokens: int = 0

    total_rag_hit_count: int = 0
    avg_rag_similarity: float | None = None
    last_rag_used_at: datetime | None = None

    sum_extract_ms: float | None = None
    total_extract_tokens: int = 0

    documents: list[ProductDocumentSummary] = []
