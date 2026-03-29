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
    search_keys_count: int = 0
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
    id: str
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
    sources: list | dict | None = None
    duration_ms: float | None
    feedback: str | None
    created_at: datetime
    debug: dict | None = None

class AdminChatSessionDetail(AdminChatSessionItem):
    messages: list[AdminChatMessage] = []

class AdminChatSessionListResponse(BaseModel):
    items: list[AdminChatSessionItem]
    total: int
    page: int
    page_size: int

class AdminChatMessageSearchItem(BaseModel):
    message_id: int
    session_id: str
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
    total_chunks: int = 0
    total_api_keys: int = 0
    total_shared_links: int = 0
    total_prompts: int = 0
    customized_prompts: int = 0

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


# --- Extended Stats ---

class FeedbackStat(BaseModel):
    total_messages: int
    rated_count: int
    positive: int
    negative: int
    positive_rate: float | None

class QueryTypeStat(BaseModel):
    query_type: str
    count: int
    pct: float

class ResponseTimeStat(BaseModel):
    avg_total_ms: float | None
    avg_rag_ms: float | None
    avg_llm_ms: float | None
    avg_search_ms: float | None
    avg_first_token_ms: float | None
    avg_tokens_per_sec: float | None
    daily: list[dict] = []

class ErrorRateStat(BaseModel):
    total: int
    errors: int
    rate: float

class ChatStats(BaseModel):
    feedback: FeedbackStat
    query_types: list[QueryTypeStat]
    response_time: ResponseTimeStat
    models: list[ModelUsageStat]
    avg_messages_per_session: float | None
    error_rate: ErrorRateStat

class TopDocumentStat(BaseModel):
    document_id: int
    title: str
    product_name: str | None
    usage_count: int
    context_tokens: int
    charge_usd: str

class DocumentFormatStat(BaseModel):
    format: str
    count: int
    pct: float

class DocumentStats(BaseModel):
    total: int
    avg_size_bytes: float | None
    avg_chunks: float | None
    uploads_daily: list[dict] = []
    top_products: list[dict] = []
    top_documents: list[TopDocumentStat] = []
    formats: list[DocumentFormatStat] = []
    unused_count: int = 0
    total_chunks: int = 0
    total_size_bytes: int = 0
    used_chunks_count: int = 0

class SearchSourceStat(BaseModel):
    source: str
    count: int
    pct: float

class ExtendedSearchStats(BaseModel):
    total_searches: int
    avg_similarity: float | None
    avg_duration_ms: float | None
    zero_result_count: int
    top_queries: list[dict] = []
    sources: list[SearchSourceStat] = []
    daily: list[dict] = []

class CostByModelStat(BaseModel):
    model: str
    provider: str | None
    total_charge_usd: str
    total_tokens: int
    request_count: int

class CostByChannelStat(BaseModel):
    channel: str
    total_charge_usd: str
    request_count: int

class TopApiKeyStat(BaseModel):
    key_prefix: str
    email: str
    request_count: int
    charge_usd: str

class CostStats(BaseModel):
    total_charge_usd: str
    total_cogs_usd: str
    avg_per_day: str
    avg_per_user: str
    forecast_month_usd: str
    daily: list[dict] = []
    by_model: list[CostByModelStat] = []
    by_channel: list[CostByChannelStat] = []
    top_api_keys: list[TopApiKeyStat] = []


# --- MCP Audit ---

class McpRequestItem(BaseModel):
    id: int
    created_at: datetime
    tenant_email: str | None = None
    key_prefix: str | None = None
    request_id: str
    tool_name: str
    query_text: str | None
    result_count: int
    top_similarity: float
    duration_ms: float
    query_tokens: int
    response_tokens: int
    embedding_tokens: int
    rerank_total_tokens: int = 0
    resolve_prompt_tokens: int = 0
    resolve_completion_tokens: int = 0
    resolve_model: str | None = None
    resolve_ms: float | None = None
    charge_usd: str
    status: str

class McpRequestDetail(McpRequestItem):
    tenant_id: str | None = None
    api_key_id: str | None = None
    product_filter: str | None
    version_filter: str | None
    doc_type_filter: str | None
    response_length: int
    rerank_prompt_tokens: int
    rerank_completion_tokens: int
    rerank_total_tokens: int
    rerank_model: str | None
    embed_ms: float
    search_ms: float
    rerank_ms: float
    cogs_usd: str
    client_ip: str | None
    user_agent: str | None
    error: str | None
    sources: list[dict] | None = None

class McpRequestListResponse(BaseModel):
    items: list[McpRequestItem]
    total: int
    page: int
    page_size: int

class McpToolBreakdown(BaseModel):
    tool_name: str
    count: int
    pct: float

class McpStats(BaseModel):
    total_requests: int
    total_query_tokens: int
    total_response_tokens: int
    total_embedding_tokens: int
    total_rerank_tokens: int = 0
    total_resolve_tokens: int = 0
    total_charge_usd: str
    avg_duration_ms: float | None
    error_count: int
    error_rate: float
    daily: list[dict] = []
    by_tool: list[McpToolBreakdown] = []
    top_queries: list[dict] = []
    top_tenants: list[dict] = []


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


# --- System Monitor ---

class ServiceHealth(BaseModel):
    name: str
    status: str
    latency_ms: float
    detail: str | None = None

class LLMStatus(BaseModel):
    provider: str
    model: str
    avg_response_ms: float | None
    errors_last_hour: int
    timeouts_last_hour: int

class IngestionPipelineStatus(BaseModel):
    pending: int
    processing: int
    error: int
    docs_per_hour_24h: float
    stale_count: int
    tus_uploads_active: int

class TableSize(BaseModel):
    name: str
    size_bytes: int

class SystemInfo(BaseModel):
    cpu_percent: float
    cpu_count: int
    ram_used_bytes: int
    ram_total_bytes: int
    ram_percent: float
    disk_used_bytes: int
    disk_total_bytes: int
    disk_percent: float
    uptime_sec: float

    db_size_bytes: int
    db_active_connections: int
    db_pool_size: int
    db_pool_checked_out: int
    db_pool_overflow: int
    db_top_tables: list[TableSize]

    redis_used_memory_bytes: int
    redis_total_keys: int
    redis_queue_celery: int
    redis_queue_monitoring: int

    s3_bucket_size_bytes: int
    s3_objects_count: int
    s3_quota_bytes: int

    ingestion: IngestionPipelineStatus
    llm: LLMStatus

    active_requests: int
    online_users_5min: int
    active_chat_sessions_5min: int

    services: list[ServiceHealth]
