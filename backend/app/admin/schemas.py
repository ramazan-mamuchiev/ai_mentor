"""Pydantic request/response schemas for admin endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# --- Tenants ---

class TenantListItem(BaseModel):
    id: uuid.UUID
    email: str
    name: str | None
    slug: str
    tier: str
    role: str
    is_active: bool
    email_verified: bool
    created_at: datetime
    updated_at: datetime
    documents_count: int = 0
    sessions_count: int = 0

class TenantDetail(TenantListItem):
    api_keys_count: int = 0
    total_tokens: int = 0
    total_requests: int = 0
    total_charge_usd: str = "0"

class TenantPatchRequest(BaseModel):
    role: str | None = None
    tier: str | None = None
    is_active: bool | None = None

class TenantListResponse(BaseModel):
    items: list[TenantListItem]
    total: int
    page: int
    page_size: int


# --- Documents ---

class AdminDocumentItem(BaseModel):
    id: int
    tenant_id: uuid.UUID | None
    tenant_email: str | None = None
    product_name: str | None = None
    manufacturer: str | None = None
    firmware_version: str | None = None
    title: str
    original_filename: str
    format: str
    status: str
    file_size_bytes: int
    total_chunks: int
    error_message: str | None
    uploaded_at: datetime
    indexed_at: datetime | None

class AdminDocumentDetail(AdminDocumentItem):
    s3_key: str
    source_hash: str
    embedding_model: str | None
    embedding_dims: int | None
    ingest_duration_ms: float | None
    total_tokens: int
    rag_hit_count: int
    rag_avg_similarity: float | None

class AdminDocumentPatchRequest(BaseModel):
    status: str | None = None

class AdminDocumentListResponse(BaseModel):
    items: list[AdminDocumentItem]
    total: int
    page: int
    page_size: int


# --- Chat Audit ---

class AdminChatSessionItem(BaseModel):
    id: int
    tenant_id: uuid.UUID | None
    tenant_email: str | None = None
    title: str | None
    product_filter: str | None
    messages_count: int = 0
    created_at: datetime
    updated_at: datetime

class AdminChatMessage(BaseModel):
    id: int
    role: str
    content: str
    sources: dict | None = None
    duration_ms: float | None
    feedback: str | None
    created_at: datetime

class AdminChatSessionDetail(AdminChatSessionItem):
    messages: list[AdminChatMessage] = []

class AdminChatSessionListResponse(BaseModel):
    items: list[AdminChatSessionItem]
    total: int
    page: int
    page_size: int

class AdminChatMessageSearchItem(BaseModel):
    message_id: int
    session_id: int
    role: str
    content: str
    tenant_email: str | None = None
    created_at: datetime

class AdminChatMessageSearchResponse(BaseModel):
    items: list[AdminChatMessageSearchItem]
    total: int


# --- Stats ---

class PlatformOverview(BaseModel):
    total_tenants: int
    active_tenants: int
    total_documents: int
    documents_indexed: int
    documents_pending: int
    documents_error: int
    total_sessions: int
    total_messages: int
    total_tokens_30d: int
    total_requests_30d: int
    total_charge_usd_30d: str

class DailyUsageStat(BaseModel):
    date: str
    requests: int
    tokens: int
    charge_usd: str

class ModelUsageStat(BaseModel):
    model: str
    provider: str
    request_count: int
    total_tokens: int
    avg_total_ms: float

class IngestionStat(BaseModel):
    total_ingested: int
    avg_duration_ms: float | None
    total_chunks: int
    pending_count: int
    error_count: int
    top_errors: list[dict] = []

class SearchStat(BaseModel):
    total_searches: int
    avg_similarity: float | None
    avg_duration_ms: float | None
    top_queries: list[dict] = []
    zero_result_count: int

class UsageStatsResponse(BaseModel):
    daily: list[DailyUsageStat]


# --- Logs ---

class LogEntry(BaseModel):
    timestamp: str
    level: str
    message: str
    service: str = ""
    extra: dict = Field(default_factory=dict)

class LogsResponse(BaseModel):
    entries: list[LogEntry]
    total: int


# --- Roles ---

class RoleListItem(BaseModel):
    id: int
    slug: str
    name: str
    description: str
    is_system: bool
    priority: int
    tenants_count: int = 0
    created_at: datetime

class RoleDetail(RoleListItem):
    permissions: dict = {}
    updated_at: datetime

class RoleCreateRequest(BaseModel):
    slug: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    priority: int = 0
    permissions: dict = Field(default_factory=dict)

class RolePatchRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    priority: int | None = None
    permissions: dict | None = None

class TenantRoleAssignRequest(BaseModel):
    role_id: int

class TenantRoleItem(BaseModel):
    id: int
    role_id: int
    role_slug: str
    role_name: str
    assigned_at: datetime


# --- Prompt Templates ---

class PromptTemplateItem(BaseModel):
    id: int
    query_type: str
    role_id: int | None
    role_slug: str | None = None
    parent_id: int | None
    is_system: bool
    is_customized: bool
    classifier_hint: str
    max_response_tokens: int | None
    rag_top_k: int | None
    created_at: datetime
    updated_at: datetime

class PromptTemplateDetail(PromptTemplateItem):
    body: str

class PromptTemplateCreateRequest(BaseModel):
    query_type: str = Field(min_length=1, max_length=64)
    role_id: int | None = None
    body: str = ""
    classifier_hint: str = ""
    max_response_tokens: int | None = None
    rag_top_k: int | None = None

class PromptTemplatePatchRequest(BaseModel):
    body: str | None = None
    classifier_hint: str | None = None
    max_response_tokens: int | None = Field(default=None)
    rag_top_k: int | None = Field(default=None)

class PromptPreviewResponse(BaseModel):
    query_type: str
    resolved_body: str
    resolved_classifier_hint: str
    resolved_max_response_tokens: int | None
    resolved_rag_top_k: int | None
