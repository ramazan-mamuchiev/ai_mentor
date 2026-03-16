# IPCodex — Database Schema & Data Model

> Part of [IPCodex Architecture](PLAN.md)

---

## Database Schema (Multi-Tenant)

### Core Tables

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
    embedding vector(1536),              -- fixed dims (OpenAI native, local zero-padded)
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

-- Usage log (for billing and analytics)
CREATE TABLE usage_log (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    action TEXT NOT NULL,                -- search | ingest | storage_snapshot
    tokens_input INT NOT NULL DEFAULT 0, -- query tokens (search) or doc tokens (ingest)
    chunks_returned INT NOT NULL DEFAULT 0,
    duration_ms INT NOT NULL DEFAULT 0,
    billable_units INT NOT NULL DEFAULT 1, -- 1 search = 1 unit, 1 ingest = 1 unit
    cost_usd NUMERIC(10,8) DEFAULT 0,     -- calculated internal cost for analytics
    created_at TIMESTAMPTZ DEFAULT NOW()
);
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
CREATE INDEX idx_usage_tenant_date ON usage_log(tenant_id, created_at);

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
