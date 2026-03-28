# Lexiro — Database Schema & Data Model

> Part of [Lexiro Architecture](PLAN.md)

---

## Current Schema (Implemented)

The tables below are currently implemented in `backend/db/schema.sql`, `backend/db/migrations/001-005`, and `backend/app/models.py`. The schema includes multi-tenancy (tenants, API keys, OAuth, RBAC).

> **Migrations**: manual SQL files in `backend/db/migrations/` (001–005). Alembic is not used. Some schema changes are applied at startup in `main.py` (e.g. `_migrate_embedding_dims()`).

```sql
CREATE EXTENSION IF NOT EXISTS vector;

-- Tenants (organizations / accounts)
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT,                       -- NULL for OAuth-only accounts
    name TEXT,
    slug TEXT NOT NULL UNIQUE,
    tier TEXT NOT NULL DEFAULT 'free',        -- free | pro | team | enterprise
    role TEXT NOT NULL DEFAULT 'user',        -- user | admin
    email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- API Keys (multiple per tenant, hashed storage)
CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    key_hash TEXT NOT NULL UNIQUE,            -- SHA-256 of the actual key
    key_prefix TEXT NOT NULL,                 -- "ipx_a1b2" for identification
    name TEXT NOT NULL DEFAULT '',
    scopes TEXT NOT NULL DEFAULT 'search,list',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- OAuth links (Google, GitHub)
CREATE TABLE tenant_oauth_links (
    id SERIAL PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,                   -- google | github
    oauth_id TEXT NOT NULL,
    email TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(provider, oauth_id)
);

-- Refresh tokens (JWT rotation)
CREATE TABLE refresh_tokens (
    id SERIAL PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- RBAC: Roles
CREATE TABLE roles (
    id SERIAL PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    is_system BOOLEAN NOT NULL DEFAULT FALSE,
    priority INT NOT NULL DEFAULT 0,
    permissions JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- RBAC: Tenant ↔ Role assignments
CREATE TABLE tenant_roles (
    id SERIAL PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    role_id INT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    assigned_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, role_id)
);

-- Prompt templates (role-based overrides for RAG prompts)
CREATE TABLE prompt_templates (
    id SERIAL PRIMARY KEY,
    query_type TEXT NOT NULL,                 -- overview | technical | code | ...
    body TEXT NOT NULL,
    classifier_hint TEXT NOT NULL DEFAULT '',
    role_id INT REFERENCES roles(id),         -- NULL = system default
    parent_id INT REFERENCES prompt_templates(id),
    is_system BOOLEAN NOT NULL DEFAULT FALSE,
    is_customized BOOLEAN NOT NULL DEFAULT FALSE,
    max_response_tokens INT,
    rag_top_k INT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(query_type, role_id)
);

-- Products (integration product catalog — hardware devices + software platforms)
CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    tenant_id UUID REFERENCES tenants(id),    -- NULL for legacy/shared products
    name TEXT NOT NULL,
    manufacturer TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',         -- camera | vms | access_control | intercom | nvr | sdk
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(manufacturer, model)
);

-- Firmware / API versions per product
CREATE TABLE firmware_versions (
    id SERIAL PRIMARY KEY,
    product_id INT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    version TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(product_id, version)
);

-- Documents (uploaded files metadata)
CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    tenant_id UUID REFERENCES tenants(id),    -- NULL for legacy documents
    product_id INT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    firmware_version_id INT NOT NULL REFERENCES firmware_versions(id),
    format TEXT NOT NULL DEFAULT 'markdown',   -- markdown | swagger | pdf | web | proto | postman | confluence
    source_path TEXT NOT NULL DEFAULT '',
    s3_key TEXT NOT NULL DEFAULT '',
    original_filename TEXT NOT NULL DEFAULT '',
    file_size_bytes BIGINT NOT NULL DEFAULT 0,
    source_hash TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    total_chunks INT NOT NULL DEFAULT 0,
    total_tokens INT NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',    -- pending | processing | ready | error
    error_message TEXT,
    celery_task_id TEXT,
    progress_percent INT NOT NULL DEFAULT 0,
    progress_stage TEXT NOT NULL DEFAULT '',   -- converting | ocr | chunking | embedding | storing | crawling | ''
    -- Timing metrics
    ingest_duration_ms FLOAT,
    read_ms FLOAT,
    convert_ms FLOAT,
    parse_ms FLOAT,
    embed_ms FLOAT,
    db_ms FLOAT,
    extract_ms FLOAT,
    -- Embedding metadata
    embedding_model TEXT,
    embedding_dims INT,
    embedding_tokens INT,
    -- OCR metrics (PDF only)
    ocr_ms FLOAT,
    ocr_images_total INT,
    ocr_images_success INT,
    ocr_images_empty INT,
    ocr_images_failed INT,
    ocr_prompt_tokens INT,
    ocr_completion_tokens INT,
    ocr_model TEXT,
    detected_language TEXT,
    -- RAG usage stats
    rag_hit_count INT NOT NULL DEFAULT 0,
    rag_last_used_at TIMESTAMPTZ,
    rag_avg_similarity FLOAT,
    avg_chunk_tokens FLOAT,
    min_chunk_tokens INT,
    max_chunk_tokens INT,
    -- Metadata extraction
    extract_prompt_tokens INT,
    extract_completion_tokens INT,
    -- Source
    source_container TEXT,                     -- archive filename or Confluence space
    converted_s3_key TEXT,
    uploaded_at TIMESTAMPTZ DEFAULT NOW(),
    indexed_at TIMESTAMPTZ
);

-- Chunks (semantic search units with vector embeddings)
CREATE TABLE chunks (
    id BIGSERIAL PRIMARY KEY,
    document_id INT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INT NOT NULL,
    heading_path TEXT NOT NULL,
    heading_level INT NOT NULL DEFAULT 1,
    content TEXT NOT NULL,
    content_clean TEXT,                        -- Markdown-stripped text for BM25
    parent_content TEXT,                       -- full section for small-to-big retrieval
    token_count INT NOT NULL DEFAULT 0,
    embedding vector(1024),                    -- Gemini embedding-2-preview (1024 dims)
    doc_type TEXT NOT NULL DEFAULT '',
    entities JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(document_id, chunk_index)
);
-- BM25 full-text search: tsvector column + trigger + GIN index
-- ALTER TABLE chunks ADD COLUMN tsv tsvector;
-- CREATE TRIGGER chunks_tsv_trigger ... tsvector_update_trigger(tsv, 'pg_catalog.english', content_clean, content);
-- CREATE INDEX idx_chunks_tsv ON chunks USING gin(tsv);

-- Chat sessions
CREATE TABLE chat_sessions (
    id SERIAL PRIMARY KEY,
    uuid UUID NOT NULL UNIQUE,
    tenant_id UUID REFERENCES tenants(id),
    api_key_id UUID,
    title TEXT,
    product_filter TEXT,
    product_filter_source TEXT,               -- user | auto
    version_filter TEXT,
    doc_context TEXT,
    history_summary TEXT,                      -- LLM-generated summary of older messages
    product_id INT REFERENCES products(id),
    summary_up_to_message_id INT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Chat messages (user + assistant turns)
CREATE TABLE chat_messages (
    id SERIAL PRIMARY KEY,
    session_id INT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,                        -- user | assistant
    content TEXT NOT NULL,
    sources JSONB,
    duration_ms FLOAT,
    feedback TEXT,                             -- thumbs_up | thumbs_down | NULL
    feedback_comment TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Chat message analytics (per-response debug/metrics)
CREATE TABLE chat_message_analytics (
    id SERIAL PRIMARY KEY,
    message_id INT NOT NULL UNIQUE REFERENCES chat_messages(id) ON DELETE CASCADE,
    session_id INT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    user_message_id INT REFERENCES chat_messages(id),
    -- LLM parameters
    llm_provider TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    embedding_model TEXT NOT NULL DEFAULT '',
    query_type TEXT,                           -- overview | technical | code | ...
    prompt_hash TEXT,
    finish_reason TEXT,
    temperature FLOAT NOT NULL DEFAULT 0,
    max_tokens INT NOT NULL DEFAULT 0,
    token_count INT NOT NULL DEFAULT 0,
    tokens_per_sec FLOAT NOT NULL DEFAULT 0,
    response_length INT NOT NULL DEFAULT 0,
    continuations INT NOT NULL DEFAULT 0,
    -- Timing
    total_ms FLOAT NOT NULL DEFAULT 0,
    rag_ms FLOAT NOT NULL DEFAULT 0,
    rag_build_ms FLOAT NOT NULL DEFAULT 0,
    llm_ms FLOAT NOT NULL DEFAULT 0,
    search_ms FLOAT NOT NULL DEFAULT 0,
    first_token_ms FLOAT NOT NULL DEFAULT 0,
    -- RAG quality
    chunks_found INT NOT NULL DEFAULT 0,
    top_similarity FLOAT NOT NULL DEFAULT 0,
    min_similarity FLOAT NOT NULL DEFAULT 0,
    context_tokens INT NOT NULL DEFAULT 0,
    history_messages INT NOT NULL DEFAULT 0,
    prompt_messages INT NOT NULL DEFAULT 0,
    -- Billing tokens
    user_input_tokens INT NOT NULL DEFAULT 0,
    user_output_tokens INT NOT NULL DEFAULT 0,
    llm_prompt_tokens INT NOT NULL DEFAULT 0,
    llm_completion_tokens INT NOT NULL DEFAULT 0,
    llm_total_tokens INT NOT NULL DEFAULT 0,
    -- Context (debugging)
    doc_context TEXT,
    auto_product TEXT,
    detected_doc_context TEXT,
    search_query TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Document usage log (per-chunk RAG usage tracking)
CREATE TABLE document_usage_log (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID,
    api_key_id UUID,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    request_id TEXT NOT NULL,
    heading_path TEXT NOT NULL DEFAULT '',
    query_text TEXT NOT NULL DEFAULT '',
    query_type TEXT NOT NULL DEFAULT '',
    sub_query TEXT NOT NULL DEFAULT '',
    session_id INT REFERENCES chat_sessions(id),
    message_id INT REFERENCES chat_messages(id),
    document_id INT REFERENCES documents(id),
    product_id INT REFERENCES products(id),
    chunk_id BIGINT,
    similarity FLOAT NOT NULL DEFAULT 0,
    context_tokens INT NOT NULL DEFAULT 0,
    charge_usd NUMERIC(12,8) NOT NULL DEFAULT 0
);

-- Search analytics (per-query metrics for MCP tools and API search)
CREATE TABLE search_analytics (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID,                           -- added in migration 002
    api_key_id UUID,                          -- added in migration 003
    source TEXT NOT NULL,                     -- "mcp" | "api" | "chat_rag"
    tool_name TEXT NOT NULL,
    query TEXT NOT NULL DEFAULT '',
    product_filter TEXT,
    version_filter TEXT,
    result_count INT NOT NULL DEFAULT 0,
    top_similarity FLOAT NOT NULL DEFAULT 0,
    duration_ms FLOAT NOT NULL DEFAULT 0,
    embedding_model TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Shared links (public access to chat sessions/messages)
CREATE TABLE shared_links (
    id SERIAL PRIMARY KEY,
    tenant_id UUID REFERENCES tenants(id),
    token TEXT NOT NULL UNIQUE,
    session_id INT REFERENCES chat_sessions(id),
    message_id INT REFERENCES chat_messages(id),
    share_type TEXT NOT NULL,                 -- session | message
    title TEXT NOT NULL DEFAULT '',
    snapshot_json JSONB,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    view_count INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ
);

-- Suggestion templates (configurable chat suggestions per role/lang)
CREATE TABLE suggestion_templates (
    id SERIAL PRIMARY KEY,
    role TEXT NOT NULL,
    lang TEXT NOT NULL,
    template TEXT NOT NULL,
    sort_order INT NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(role, lang, template)
);

-- Reindex jobs (background reindexing operations)
CREATE TABLE reindex_jobs (
    id SERIAL PRIMARY KEY,
    tenant_id UUID REFERENCES tenants(id),
    mode TEXT NOT NULL,                       -- reingest | reembed
    status TEXT NOT NULL DEFAULT 'pending',   -- pending | running | completed | failed | cancelled | stale
    product_filter TEXT,
    format_filter TEXT,
    total_documents INT NOT NULL DEFAULT 0,
    processed_documents INT NOT NULL DEFAULT 0,
    failed_documents INT NOT NULL DEFAULT 0,
    skipped_documents INT NOT NULL DEFAULT 0,
    total_chunks INT NOT NULL DEFAULT 0,
    celery_task_id TEXT,
    error_message TEXT,
    errors_json TEXT NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    heartbeat_at TIMESTAMPTZ
);

-- Upload sessions (TUS resumable upload protocol)
CREATE TABLE upload_sessions (
    id TEXT PRIMARY KEY,
    tenant_id UUID REFERENCES tenants(id),
    filename TEXT NOT NULL,
    file_size BIGINT NOT NULL,
    "offset" BIGINT NOT NULL DEFAULT 0,
    content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
    product_name TEXT NOT NULL,
    firmware_version TEXT NOT NULL DEFAULT '1.0',
    manufacturer TEXT NOT NULL DEFAULT '',
    is_archive BOOLEAN NOT NULL DEFAULT FALSE,
    force BOOLEAN NOT NULL DEFAULT FALSE,
    s3_upload_id TEXT NOT NULL DEFAULT '',
    s3_key TEXT NOT NULL DEFAULT '',
    parts_json TEXT NOT NULL DEFAULT '[]',
    sha256_state TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'uploading',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL
);

-- Usage log (append-only billing audit trail, partitioned by month)
CREATE TABLE usage_log (
    id BIGSERIAL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    channel TEXT NOT NULL,
    action TEXT NOT NULL,
    request_id TEXT NOT NULL,

    llm_provider TEXT,
    llm_model TEXT,
    prompt_tokens INT NOT NULL DEFAULT 0,
    completion_tokens INT NOT NULL DEFAULT 0,
    total_tokens INT NOT NULL DEFAULT 0,

    context_chunks INT NOT NULL DEFAULT 0,
    context_tokens INT NOT NULL DEFAULT 0,
    history_messages INT NOT NULL DEFAULT 0,
    query_tokens INT NOT NULL DEFAULT 0,
    history_tokens INT NOT NULL DEFAULT 0,
    system_prompt_tokens INT NOT NULL DEFAULT 0,

    query_text TEXT,
    result_count INT NOT NULL DEFAULT 0,
    response_tokens INT NOT NULL DEFAULT 0,
    response_length INT NOT NULL DEFAULT 0,
    top_similarity FLOAT NOT NULL DEFAULT 0,

    product_filter TEXT,
    version_filter TEXT,

    duration_ms FLOAT NOT NULL DEFAULT 0,
    embedding_ms FLOAT NOT NULL DEFAULT 0,
    search_ms FLOAT NOT NULL DEFAULT 0,
    llm_ms FLOAT NOT NULL DEFAULT 0,

    cogs_usd NUMERIC(12,8) NOT NULL DEFAULT 0,
    charge_usd NUMERIC(12,8) NOT NULL DEFAULT 0,

    tenant_id UUID,
    api_key_id UUID,                          -- added in migration 003

    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);
-- Partitions auto-created by Celery Beat task (ensure_usage_partitions)
```

### Migrations

Manual SQL files in `backend/db/migrations/`:

| File | Description |
|------|-------------|
| `001_auth_tables.sql` | tenants, api_keys, tenant_oauth_links, refresh_tokens |
| `002_add_tenant_id.sql` | Add tenant_id to products, documents, chat_sessions, search_analytics, etc. |
| `003_add_api_key_id.sql` | Add api_key_id to usage_log, search_analytics, chat_sessions |
| `004_add_tenant_role.sql` | Add role column to tenants |
| `005_roles_and_prompts.sql` | roles, tenant_roles, prompt_templates tables |

### Current Indexes

```sql
CREATE INDEX idx_chunks_embedding ON chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 128);

CREATE INDEX idx_chunks_document ON chunks(document_id);
CREATE INDEX idx_chat_messages_session ON chat_messages(session_id);
CREATE INDEX idx_reindex_jobs_status ON reindex_jobs(status);
CREATE INDEX idx_documents_source_hash ON documents(source_hash) WHERE source_hash != '';
CREATE INDEX idx_upload_sessions_status ON upload_sessions(status);
CREATE INDEX idx_upload_sessions_expires ON upload_sessions(expires_at);

-- Chat message analytics indexes
CREATE INDEX idx_cma_session ON chat_message_analytics(session_id);
CREATE INDEX idx_cma_message ON chat_message_analytics(message_id);
CREATE INDEX idx_cma_model ON chat_message_analytics(model);
CREATE INDEX idx_cma_provider ON chat_message_analytics(llm_provider);
CREATE INDEX idx_cma_created ON chat_message_analytics(created_at);
CREATE INDEX idx_cma_similarity ON chat_message_analytics(top_similarity);

-- Search analytics indexes
CREATE INDEX idx_sa_source ON search_analytics(source);
CREATE INDEX idx_sa_tool ON search_analytics(tool_name);
CREATE INDEX idx_sa_created ON search_analytics(created_at);
CREATE INDEX idx_sa_product ON search_analytics(product_filter) WHERE product_filter IS NOT NULL;

-- Usage log indexes (partitioned table — indexes apply to all partitions)
CREATE INDEX idx_usage_log_channel ON usage_log (channel, created_at);
CREATE INDEX idx_usage_log_action ON usage_log (action, created_at);
CREATE INDEX idx_usage_log_request ON usage_log (request_id);
CREATE INDEX idx_usage_log_tenant ON usage_log (tenant_id, created_at) WHERE tenant_id IS NOT NULL;
CREATE INDEX idx_usage_log_model ON usage_log (llm_model, created_at) WHERE llm_model IS NOT NULL;
```

---

## Planned Schema (Multi-Tenant)

The tables below describe the target multi-tenant architecture. They extend the current schema with tenant isolation, vendor marketplace, billing, and artifact distribution.

### Core Tables (Planned)

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Tenants (organizations / accounts)
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL,
    tier TEXT NOT NULL DEFAULT 'free',       -- free | pro | team | enterprise
    -- Tier limits (denormalized from tier config for fast checks)
    max_devices INT NOT NULL DEFAULT 5,
    max_documents INT NOT NULL DEFAULT 5,
    max_searches_per_month INT NOT NULL DEFAULT 200,
    max_storage_mb INT NOT NULL DEFAULT 50,
    max_mcp_connections INT NOT NULL DEFAULT 1,
    max_downloads_per_month INT NOT NULL DEFAULT 0,  -- Free=0, Pro=50, Team/Ent=-1 (unlimited)
    rate_limit_rpm INT NOT NULL DEFAULT 10,  -- requests per minute
    -- Billing
    stripe_customer_id TEXT,                 -- Stripe customer ID
    stripe_subscription_id TEXT,             -- Stripe subscription ID
    overage_cap_usd NUMERIC(10,2),           -- optional hard cap on monthly overage
    -- Status
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- API Keys (multiple per tenant, hashed storage)
CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    key_hash TEXT NOT NULL UNIQUE,       -- SHA-256 of the actual key
    key_prefix TEXT NOT NULL,            -- "ipx_a1b2" for identification
    name TEXT NOT NULL DEFAULT '',
    scopes TEXT[] NOT NULL DEFAULT '{search,list}',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Devices (tenant-scoped catalog + optional vendor link)
CREATE TABLE devices (
    id SERIAL PRIMARY KEY,
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,  -- NULL for public vendor devices
    vendor_id UUID REFERENCES vendors(id),                     -- NULL for private tenant devices
    name TEXT NOT NULL,
    manufacturer TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',           -- video_surveillance | access_control | intercom | ...
    is_public BOOLEAN NOT NULL DEFAULT FALSE,    -- TRUE = visible in public catalog
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(COALESCE(tenant_id, vendor_id), manufacturer, model)
);

-- Firmware versions (per device)
CREATE TABLE firmware_versions (
    id SERIAL PRIMARY KEY,
    device_id INT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    version TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(device_id, version)
);

-- Documents (uploaded files metadata — all formats)
CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,   -- NULL for vendor-published
    vendor_id UUID REFERENCES vendors(id),                      -- NULL for tenant-uploaded
    device_id INT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    firmware_version_id INT NOT NULL REFERENCES firmware_versions(id),
    format TEXT NOT NULL DEFAULT 'markdown', -- markdown | swagger | postman | pdf | pdf_ocr | web
    source_hash TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    original_filename TEXT DEFAULT '',       -- preserve original file name
    s3_key TEXT NOT NULL DEFAULT '',
    file_size_bytes BIGINT NOT NULL DEFAULT 0,
    total_chunks INT NOT NULL DEFAULT 0,
    billable_units INT NOT NULL DEFAULT 1,  -- 1 (md/swagger/postman), 2 (pdf/web), 5 (ocr)
    status TEXT NOT NULL DEFAULT 'pending',  -- pending | processing | ready | error
    error_message TEXT,
    progress_percent INT NOT NULL DEFAULT 0,  -- 0-100, real-time ingestion progress
    progress_stage TEXT NOT NULL DEFAULT '',   -- converting | ocr | chunking | embedding | storing | ''
    -- OCR metrics (PDF only, NULL for other formats)
    ocr_ms FLOAT,
    ocr_images_total INT,
    ocr_images_success INT,
    ocr_images_empty INT,
    ocr_images_failed INT,
    detected_language TEXT,
    -- Download control
    is_downloadable BOOLEAN NOT NULL DEFAULT TRUE,
    download_policy TEXT NOT NULL DEFAULT 'public', -- public | search_only | pro_only
    download_count INT NOT NULL DEFAULT 0,
    ingested_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(COALESCE(tenant_id, vendor_id), device_id, firmware_version_id, source_hash)
);

-- Chunks (the core semantic search unit)
CREATE TABLE chunks (
    id BIGSERIAL PRIMARY KEY,
    document_id INT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL,             -- denormalized for search performance
    chunk_index INT NOT NULL,
    heading_path TEXT NOT NULL,           -- "Chapter 4 > Access Control > Door Control"
    heading_level INT NOT NULL,           -- 1, 2, or 3
    content TEXT NOT NULL,
    token_count INT NOT NULL DEFAULT 0,
    embedding vector(1024),              -- Gemini Matryoshka / local E5 native dims
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(document_id, chunk_index)
);

-- Vendor accounts (device manufacturers)
CREATE TABLE vendors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    website TEXT DEFAULT '',
    logo_url TEXT DEFAULT '',
    tier TEXT NOT NULL DEFAULT 'basic',       -- basic | pro | enterprise | platinum
    is_verified BOOLEAN NOT NULL DEFAULT FALSE,
    contact_email TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT '',        -- video_surveillance | access_control | ...
    -- Tier limits
    max_devices INT NOT NULL DEFAULT 20,
    max_documents INT NOT NULL DEFAULT 50,
    max_storage_bytes BIGINT NOT NULL DEFAULT 1073741824, -- 1 GB (Basic), 50 GB (Pro), 500 GB (Ent), unlimited (Plat)
    -- Billing
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Vendor API keys (separate from tenant API keys)
CREATE TABLE vendor_api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vendor_id UUID NOT NULL REFERENCES vendors(id) ON DELETE CASCADE,
    key_hash TEXT NOT NULL UNIQUE,
    key_prefix TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    scopes TEXT[] NOT NULL DEFAULT '{publish,analytics}',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Vendor analytics (daily aggregation of search stats per vendor)
CREATE TABLE vendor_analytics (
    id BIGSERIAL PRIMARY KEY,
    vendor_id UUID NOT NULL REFERENCES vendors(id),
    device_id INT REFERENCES devices(id),
    date DATE NOT NULL,
    search_count INT NOT NULL DEFAULT 0,
    unique_tenants INT NOT NULL DEFAULT 0,
    top_queries JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(vendor_id, device_id, date)
);

-- Vendor artifacts (firmware, SDKs, tools, drivers — binary file distribution)
CREATE TABLE vendor_artifacts (
    id BIGSERIAL PRIMARY KEY,
    vendor_id UUID NOT NULL REFERENCES vendors(id) ON DELETE CASCADE,
    device_id INT REFERENCES devices(id),
    firmware_version_id INT REFERENCES firmware_versions(id),
    artifact_type TEXT NOT NULL,          -- firmware | sdk | tool | driver | release_notes
    filename TEXT NOT NULL,               -- original filename: "DS-2CD2347_V5.7.21.bin"
    s3_key TEXT NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    sha256_hash TEXT NOT NULL,            -- integrity verification
    content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
    description TEXT DEFAULT '',
    release_notes_md TEXT DEFAULT '',     -- markdown; if non-empty, auto-indexed as chunks
    changelog_diff TEXT DEFAULT '',       -- diff vs previous version (auto-generated)
    -- Security scanning
    scan_status TEXT NOT NULL DEFAULT 'pending',  -- pending | scanning | clean | infected | error
    scan_result JSONB DEFAULT '{}',       -- { engine, threats_found, scanned_at }
    -- Access control
    is_public BOOLEAN NOT NULL DEFAULT TRUE,
    download_count INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Tenant ↔ Public Device subscriptions (when tenant adds vendor device from catalog)
CREATE TABLE tenant_devices (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    device_id INT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    added_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, device_id)
);

-- Usage log: ALREADY IMPLEMENTED — see "Current Schema" section above.
-- The current usage_log is partitioned by month (PARTITION BY RANGE),
-- tracks cogs_usd + charge_usd separately, includes full prompt
-- decomposition (query_tokens, context_tokens, history_tokens,
-- system_prompt_tokens), and has tenant_id as nullable UUID
-- (will become NOT NULL REFERENCES tenants(id) when multi-tenancy is added).
```

### Indexes

```sql
-- HNSW vector index (cosine similarity)
CREATE INDEX idx_chunks_embedding ON chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 128);

-- Tenant isolation (critical for multi-tenant performance)
CREATE INDEX idx_chunks_tenant ON chunks(tenant_id);
CREATE INDEX idx_chunks_document ON chunks(document_id);
CREATE INDEX idx_devices_tenant ON devices(tenant_id);
CREATE INDEX idx_documents_tenant ON documents(tenant_id);
CREATE INDEX idx_api_keys_hash ON api_keys(key_hash);
-- usage_log indexes: already defined in Current Schema section

-- Vendor indexes
CREATE INDEX idx_vendor_api_keys_hash ON vendor_api_keys(key_hash);
CREATE INDEX idx_vendor_analytics_date ON vendor_analytics(vendor_id, date);
CREATE INDEX idx_devices_vendor ON devices(vendor_id);
CREATE INDEX idx_devices_public ON devices(is_public) WHERE is_public = TRUE;
CREATE INDEX idx_tenant_devices ON tenant_devices(tenant_id);
CREATE INDEX idx_vendor_artifacts_vendor ON vendor_artifacts(vendor_id);
CREATE INDEX idx_vendor_artifacts_device ON vendor_artifacts(device_id);
CREATE INDEX idx_vendor_artifacts_scan ON vendor_artifacts(scan_status) WHERE scan_status = 'pending';

-- Row Level Security
ALTER TABLE devices ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE chunks ENABLE ROW LEVEL SECURITY;
```

---

## Vendor ↔ Tenant Documentation Sharing Model

### Public vs Private Documentation

```
Vendor publishes docs → "PUBLIC" catalog
  │
  │  visible to ALL tenants in public catalog
  │
  ▼
Tenant browses catalog: GET /api/v1/catalog/devices
  → sees "HikCentral Professional" by Hikvision (Verified ✓)
  → POST /api/v1/catalog/devices/{id}/add
  │
  ▼
Device + docs copied/linked to tenant's scope
  → tenant can now search this device's documentation via MCP
  → search queries are logged (for vendor analytics)

Tenant uploads own docs → "PRIVATE" (only that tenant)
  │
  │  invisible to other tenants and vendors
  │
  ▼
Private docs are tenant-scoped and never shared
```

**How it works technically:**
- `devices` table has optional `vendor_id` column
- Devices with `vendor_id` AND in `public_catalog` flag = visible to all
- When tenant "adds" a public device, we create a link (not copy) — the `chunks` table query uses `vendor_id` for public docs
- Private tenant docs have `vendor_id = NULL`
- Vector search query expands to: `WHERE (c.tenant_id = $tenant OR c.vendor_id IN (tenant's subscribed vendors))`

---

## Vector Search Query (Tenant-Isolated)

```sql
-- Search across tenant's own docs + subscribed public vendor docs
SELECT c.content, c.heading_path, c.chunk_index,
       d.title AS doc_title,
       dev.name AS device_name,
       fw.version AS firmware_version,
       v.name AS vendor_name,
       v.is_verified AS vendor_verified,
       1 - (c.embedding <=> $1) AS similarity
FROM chunks c
JOIN documents d ON c.document_id = d.id
JOIN devices dev ON d.device_id = dev.id
JOIN firmware_versions fw ON d.firmware_version_id = fw.id
LEFT JOIN vendors v ON dev.vendor_id = v.id
WHERE (
    c.tenant_id = $2                               -- tenant's own private docs
    OR dev.id IN (                                  -- public vendor docs the tenant subscribed to
        SELECT td.device_id FROM tenant_devices td
        WHERE td.tenant_id = $2
    )
)
  AND ($3::int IS NULL OR dev.id = $3)              -- optional device filter
  AND ($4::int IS NULL OR fw.id = $4)               -- optional firmware filter
ORDER BY c.embedding <=> $1
LIMIT $5;
```

---

## RLS Policies

```sql
-- Tenant can only see their own devices
CREATE POLICY tenant_devices ON devices
    FOR ALL
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- Tenant can only see their own documents
CREATE POLICY tenant_documents ON documents
    FOR ALL
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- Tenant can only search their own chunks (+ public vendor chunks)
CREATE POLICY tenant_chunks ON chunks
    FOR SELECT
    USING (
        tenant_id = current_setting('app.current_tenant_id')::uuid
        OR document_id IN (
            SELECT d.id FROM documents d
            JOIN devices dev ON d.device_id = dev.id
            WHERE dev.vendor_id IS NOT NULL AND dev.is_public = TRUE
        )
    );

-- Set tenant context on each request (in FastAPI middleware)
-- SET LOCAL app.current_tenant_id = '{tenant_id}';
```

---

## Vector Search Scaling

Three-stage scaling strategy for vector search. Each stage is triggered by data growth, not by time.

### Stage 1: pgvector Single Index (0–2M chunks)

Default configuration. No changes needed from the base schema above.

```
chunks table → single HNSW index → all tenants in one index
                                    post-filter by tenant_id
```

**Capacity**: ~2M chunks on a 64 GB RAM server (HNSW index ~12 GB + working memory).
**Search latency**: 20–80ms (p95).
**Limitation**: post-filtering means pgvector scans vectors from all tenants, then discards non-matching ones. At 2M+ chunks with 500+ tenants, recall degrades for small tenants (their chunks are "drowned" by larger tenants).

### Stage 2: pgvector HASH Partitioning (2–10M chunks)

Partition the `chunks` table by `tenant_id` hash. Each partition gets its own HNSW index.

```sql
-- Migration: recreate chunks table with partitioning
-- (Alembic migration, requires data copy)

CREATE TABLE chunks_partitioned (
    id BIGSERIAL,
    document_id INT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL,
    chunk_index INT NOT NULL,
    heading_path TEXT NOT NULL,
    heading_level INT NOT NULL,
    content TEXT NOT NULL,
    token_count INT NOT NULL DEFAULT 0,
    embedding vector(1536),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(document_id, chunk_index)
) PARTITION BY HASH (tenant_id);

-- Create 32 partitions (balance between granularity and planner overhead)
DO $$
BEGIN
    FOR i IN 0..31 LOOP
        EXECUTE format(
            'CREATE TABLE chunks_p%s PARTITION OF chunks_partitioned
             FOR VALUES WITH (MODULUS 32, REMAINDER %s)',
            i, i
        );
        EXECUTE format(
            'CREATE INDEX idx_chunks_p%s_embedding ON chunks_p%s
             USING hnsw (embedding vector_cosine_ops)
             WITH (m = 16, ef_construction = 128)',
            i, i
        );
        EXECUTE format(
            'CREATE INDEX idx_chunks_p%s_tenant ON chunks_p%s(tenant_id)',
            i, i
        );
    END LOOP;
END $$;

-- Swap tables
ALTER TABLE chunks RENAME TO chunks_old;
ALTER TABLE chunks_partitioned RENAME TO chunks;

-- Migrate data (can be done in batches for zero-downtime)
INSERT INTO chunks SELECT * FROM chunks_old;
DROP TABLE chunks_old;
```

**How partition pruning works**: when query has `WHERE tenant_id = $t`, PostgreSQL hashes `$t` and routes to exactly one partition (e.g., partition 7 of 32). Only that partition's HNSW index is scanned.

**Cross-tenant search (vendor public docs)**: partition pruning requires a single tenant_id. For the combined query (private + public docs), split into two queries in the application layer:

```python
# search/service.py — Stage 2 adaptation

async def search(tenant_id: UUID, query_embedding, filters, limit: int = 5):
    # Query 1: tenant's private docs (partition-pruned, fast)
    private_results = await db.execute(
        select(Chunk).where(
            Chunk.tenant_id == tenant_id,
            # ... device/firmware filters
        ).order_by(Chunk.embedding.cosine_distance(query_embedding))
        .limit(limit)
    )

    # Query 2: public vendor docs the tenant subscribes to
    subscribed_device_ids = await get_subscribed_devices(tenant_id)
    if subscribed_device_ids:
        public_results = await db.execute(
            select(Chunk).join(Document).where(
                Document.device_id.in_(subscribed_device_ids),
                Document.vendor_id.isnot(None),
                # ... device/firmware filters
            ).order_by(Chunk.embedding.cosine_distance(query_embedding))
            .limit(limit)
        )
    else:
        public_results = []

    # Merge by similarity score, return top N
    merged = sorted(
        private_results + public_results,
        key=lambda c: c.similarity, reverse=True
    )[:limit]
    return merged
```

**Capacity**: ~10M chunks on a 128 GB RAM server. Each partition holds ~300K chunks → HNSW index ~1.8 GB per partition, easily fits in RAM.
**Search latency**: 15–50ms (p95) — faster than Stage 1 due to smaller indexes.

### Scaling Decision Matrix

| Metric | Check | Action |
|--------|-------|--------|
| chunks count > 2M | `SELECT count(*) FROM chunks` | Start Stage 2 planning |
| HNSW index > 50% of shared_buffers | `pg_relation_size('idx_chunks_embedding')` | Migrate to Stage 2 |
| Search p95 latency > 200ms | monitoring | Investigate: add partitions, increase RAM |

At projected Year 3 scale (1,000 developers + 60 vendors ≈ 3M chunks), Stage 2 with 32 partitions provides sufficient headroom (up to 10M chunks on a 128 GB server). A dedicated vector database (Qdrant, Milvus) would only be needed if the platform grows significantly beyond these projections — a decision to revisit if and when that growth materializes.
