CREATE EXTENSION IF NOT EXISTS vector;

-- Products (integration product catalog, formerly "devices")
CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    manufacturer TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(manufacturer, model)
);

-- Product slugs for human-readable URLs
ALTER TABLE products ADD COLUMN IF NOT EXISTS slug TEXT NOT NULL DEFAULT '';
ALTER TABLE products ADD COLUMN IF NOT EXISTS manufacturer_slug TEXT NOT NULL DEFAULT '';
CREATE UNIQUE INDEX IF NOT EXISTS idx_products_slug ON products(manufacturer_slug, slug) WHERE slug != '';

-- Firmware / API versions per product
CREATE TABLE IF NOT EXISTS firmware_versions (
    id SERIAL PRIMARY KEY,
    product_id INT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    version TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(product_id, version)
);

-- Documents (uploaded files metadata)
CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    product_id INT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    firmware_version_id INT NOT NULL REFERENCES firmware_versions(id),
    format TEXT NOT NULL DEFAULT 'markdown',
    source_path TEXT NOT NULL DEFAULT '',
    s3_key TEXT NOT NULL DEFAULT '',
    original_filename TEXT NOT NULL DEFAULT '',
    file_size_bytes BIGINT NOT NULL DEFAULT 0,
    source_hash TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    total_chunks INT NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    error_message TEXT,
    uploaded_at TIMESTAMPTZ DEFAULT NOW(),
    indexed_at TIMESTAMPTZ
);

-- Migration: rename ingested_at -> uploaded_at, add indexed_at
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='documents' AND column_name='ingested_at') THEN
        ALTER TABLE documents RENAME COLUMN ingested_at TO uploaded_at;
    END IF;
END $$;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS indexed_at TIMESTAMPTZ;
UPDATE documents SET indexed_at = uploaded_at WHERE status = 'ready' AND indexed_at IS NULL;

-- Document indexing metrics (added for debug panel)
ALTER TABLE documents ADD COLUMN IF NOT EXISTS ingest_duration_ms FLOAT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS read_ms FLOAT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS convert_ms FLOAT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS parse_ms FLOAT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS embed_ms FLOAT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS db_ms FLOAT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS total_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS min_chunk_tokens INT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS max_chunk_tokens INT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS avg_chunk_tokens FLOAT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS embedding_model TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS embedding_dims INT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS embedding_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS rag_hit_count INT NOT NULL DEFAULT 0;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS rag_avg_similarity FLOAT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS rag_last_used_at TIMESTAMPTZ;

-- Progress tracking for real-time ingestion feedback
ALTER TABLE documents ADD COLUMN IF NOT EXISTS progress_percent INT NOT NULL DEFAULT 0;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS progress_stage TEXT NOT NULL DEFAULT '';

-- Celery task ID for cancellation support
ALTER TABLE documents ADD COLUMN IF NOT EXISTS celery_task_id TEXT;

-- OCR metrics and language detection
ALTER TABLE documents ADD COLUMN IF NOT EXISTS ocr_ms FLOAT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS ocr_images_total INT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS ocr_images_success INT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS ocr_images_empty INT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS ocr_images_failed INT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS detected_language TEXT;

-- Source container (archive filename or URL the document was extracted from)
ALTER TABLE documents ADD COLUMN IF NOT EXISTS source_container TEXT;

-- Fix FK: documents.firmware_version_id should CASCADE on delete
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'documents_firmware_version_id_fkey'
        AND table_name = 'documents'
    ) THEN
        ALTER TABLE documents DROP CONSTRAINT documents_firmware_version_id_fkey;
        ALTER TABLE documents ADD CONSTRAINT documents_firmware_version_id_fkey
            FOREIGN KEY (firmware_version_id) REFERENCES firmware_versions(id) ON DELETE CASCADE;
    END IF;
END $$;

-- Converted Markdown stored in S3 (full text before chunking, for preview/download)
ALTER TABLE documents ADD COLUMN IF NOT EXISTS converted_s3_key TEXT;

-- Metadata extraction metrics (LLM-based entity/doc_type extraction)
ALTER TABLE documents ADD COLUMN IF NOT EXISTS extract_ms FLOAT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS extract_prompt_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS extract_completion_tokens INT NOT NULL DEFAULT 0;

-- Chunks (semantic search units with vector embeddings)
CREATE TABLE IF NOT EXISTS chunks (
    id BIGSERIAL PRIMARY KEY,
    document_id INT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INT NOT NULL,
    heading_path TEXT NOT NULL,
    heading_level INT NOT NULL DEFAULT 1,
    content TEXT NOT NULL,
    parent_content TEXT,
    token_count INT NOT NULL DEFAULT 0,
    embedding vector(1024),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(document_id, chunk_index)
);

-- Cleaned content for BM25 (Markdown stripped in Python, populated during ingestion)
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS content_clean TEXT;

-- Chunk metadata: doc_type and extracted entities (LLM-based)
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS doc_type TEXT DEFAULT 'other';
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS entities JSONB DEFAULT '{}';
CREATE INDEX IF NOT EXISTS idx_chunks_doc_type ON chunks(doc_type);
CREATE INDEX IF NOT EXISTS idx_chunks_entities ON chunks USING gin(entities jsonb_path_ops);

-- Full-text search column (BM25 via tsvector for hybrid search)
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS tsv tsvector;

CREATE OR REPLACE FUNCTION chunks_tsv_trigger() RETURNS trigger AS $$
DECLARE
    entity_text TEXT := '';
    kw TEXT;
BEGIN
    IF NEW.entities IS NOT NULL AND NEW.entities != '{}' THEN
        FOR kw IN SELECT jsonb_array_elements_text(v)
            FROM jsonb_each(NEW.entities) AS e(k, v)
            WHERE jsonb_typeof(v) = 'array'
        LOOP
            entity_text := entity_text || ' ' || kw;
        END LOOP;
    END IF;

    NEW.tsv := to_tsvector('english',
        COALESCE(NEW.heading_path, '') || ' ' ||
        COALESCE(NEW.doc_type, '') || ' ' ||
        entity_text || ' ' ||
        COALESCE(NEW.content_clean, NEW.content, ''));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_chunks_tsv ON chunks;
CREATE TRIGGER trg_chunks_tsv BEFORE INSERT OR UPDATE OF content, content_clean, heading_path, doc_type, entities ON chunks
    FOR EACH ROW EXECUTE FUNCTION chunks_tsv_trigger();

-- Backfill existing rows
UPDATE chunks SET tsv = to_tsvector('english',
    COALESCE(heading_path, '') || ' ' ||
    COALESCE(doc_type, '') || ' ' ||
    COALESCE(content_clean, content, ''));

-- GIN index for full-text search
CREATE INDEX IF NOT EXISTS idx_chunks_tsv ON chunks USING gin(tsv);

-- HNSW vector index (cosine similarity)
CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 128);

CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);

-- Chat sessions
CREATE TABLE IF NOT EXISTS chat_sessions (
    id SERIAL PRIMARY KEY,
    title TEXT,
    product_filter TEXT,
    version_filter TEXT,
    doc_context TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Migration: add product_id FK for strict product filtering
ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS product_id INT REFERENCES products(id) ON DELETE SET NULL;
ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS product_filter_source TEXT;

-- Chat messages
CREATE TABLE IF NOT EXISTS chat_messages (
    id SERIAL PRIMARY KEY,
    session_id INT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    sources JSONB,
    duration_ms FLOAT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id);

-- Chat message analytics (per-response debug/metrics for RAG answers)
CREATE TABLE IF NOT EXISTS chat_message_analytics (
    id SERIAL PRIMARY KEY,
    message_id INT NOT NULL UNIQUE REFERENCES chat_messages(id) ON DELETE CASCADE,
    session_id INT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    user_message_id INT REFERENCES chat_messages(id) ON DELETE SET NULL,
    -- LLM
    llm_provider TEXT NOT NULL,
    model TEXT NOT NULL,
    temperature FLOAT NOT NULL DEFAULT 0,
    max_tokens INT NOT NULL DEFAULT 0,
    token_count INT NOT NULL DEFAULT 0,
    tokens_per_sec FLOAT NOT NULL DEFAULT 0,
    response_length INT NOT NULL DEFAULT 0,
    -- Timing
    total_ms FLOAT NOT NULL DEFAULT 0,
    rag_ms FLOAT NOT NULL DEFAULT 0,
    llm_ms FLOAT NOT NULL DEFAULT 0,
    search_ms FLOAT NOT NULL DEFAULT 0,
    first_token_ms FLOAT NOT NULL DEFAULT 0,
    rag_build_ms FLOAT NOT NULL DEFAULT 0,
    -- RAG
    chunks_found INT NOT NULL DEFAULT 0,
    top_similarity FLOAT NOT NULL DEFAULT 0,
    min_similarity FLOAT NOT NULL DEFAULT 0,
    context_tokens INT NOT NULL DEFAULT 0,
    history_messages INT NOT NULL DEFAULT 0,
    prompt_messages INT NOT NULL DEFAULT 0,
    embedding_model TEXT NOT NULL DEFAULT '',
    -- Context
    doc_context TEXT,
    auto_product TEXT,
    detected_doc_context TEXT,
    search_query TEXT,
    -- Billing
    user_input_tokens INT NOT NULL DEFAULT 0,
    user_output_tokens INT NOT NULL DEFAULT 0,
    llm_prompt_tokens INT NOT NULL DEFAULT 0,
    llm_completion_tokens INT NOT NULL DEFAULT 0,
    llm_total_tokens INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cma_session ON chat_message_analytics(session_id);
CREATE INDEX IF NOT EXISTS idx_cma_message ON chat_message_analytics(message_id);
CREATE INDEX IF NOT EXISTS idx_cma_model ON chat_message_analytics(model);
CREATE INDEX IF NOT EXISTS idx_cma_provider ON chat_message_analytics(llm_provider);
CREATE INDEX IF NOT EXISTS idx_cma_created ON chat_message_analytics(created_at);
CREATE INDEX IF NOT EXISTS idx_cma_similarity ON chat_message_analytics(top_similarity);

-- Prompt tracking (query_type + prompt_hash for reproducibility)
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS query_type TEXT;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS prompt_hash TEXT;

-- Search analytics (per-query metrics for MCP tools and API search)
CREATE TABLE IF NOT EXISTS search_analytics (
    id BIGSERIAL PRIMARY KEY,
    source TEXT NOT NULL,                    -- "mcp" | "api" | "chat_rag"
    tool_name TEXT NOT NULL,                 -- "search_documentation" | "get_api_endpoint" | "list_products"
    query TEXT NOT NULL DEFAULT '',
    product_filter TEXT,
    version_filter TEXT,
    result_count INT NOT NULL DEFAULT 0,
    top_similarity FLOAT NOT NULL DEFAULT 0,
    duration_ms FLOAT NOT NULL DEFAULT 0,
    embedding_model TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sa_source ON search_analytics(source);
CREATE INDEX IF NOT EXISTS idx_sa_tool ON search_analytics(tool_name);
CREATE INDEX IF NOT EXISTS idx_sa_created ON search_analytics(created_at);
CREATE INDEX IF NOT EXISTS idx_sa_product ON search_analytics(product_filter) WHERE product_filter IS NOT NULL;

-- Reindex jobs (background reindexing operations)
CREATE TABLE IF NOT EXISTS reindex_jobs (
    id SERIAL PRIMARY KEY,
    mode TEXT NOT NULL,                     -- "reingest" or "reembed"
    status TEXT NOT NULL DEFAULT 'pending', -- pending | running | completed | failed | cancelled | stale
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

CREATE INDEX IF NOT EXISTS idx_reindex_jobs_status ON reindex_jobs(status);

-- Deduplication index on document content hash
CREATE INDEX IF NOT EXISTS idx_documents_source_hash ON documents(source_hash) WHERE source_hash != '';

-- Upload sessions (TUS resumable upload protocol)
CREATE TABLE IF NOT EXISTS upload_sessions (
    id TEXT PRIMARY KEY,
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

CREATE INDEX IF NOT EXISTS idx_upload_sessions_status ON upload_sessions(status);
CREATE INDEX IF NOT EXISTS idx_upload_sessions_expires ON upload_sessions(expires_at);

-- Usage log (append-only billing audit trail, partitioned by month)
CREATE TABLE IF NOT EXISTS usage_log (
    id BIGSERIAL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    channel TEXT NOT NULL,                          -- 'chat' | 'mcp'
    action TEXT NOT NULL,                           -- 'chat_completion' | 'search_documentation' | 'get_api_endpoint' | 'list_products'
    request_id TEXT NOT NULL,                       -- UUID v4 for deduplication and audit

    llm_provider TEXT,                              -- 'openai' (OpenAI-compatible: Gemini, GPT, etc.)
    llm_model TEXT,                                 -- 'gemini-2.5-flash', 'gemini-2.5-pro', etc.
    prompt_tokens INT NOT NULL DEFAULT 0,           -- from LLM API: usage.prompt_tokens
    completion_tokens INT NOT NULL DEFAULT 0,       -- from LLM API: usage.completion_tokens
    total_tokens INT NOT NULL DEFAULT 0,            -- prompt_tokens + completion_tokens

    context_chunks INT NOT NULL DEFAULT 0,          -- RAG chunks used in prompt
    context_tokens INT NOT NULL DEFAULT 0,          -- sum of chunk token_count from RAG
    history_messages INT NOT NULL DEFAULT 0,        -- chat history messages in prompt
    query_tokens INT NOT NULL DEFAULT 0,            -- approximate tokens of user query text only
    history_tokens INT NOT NULL DEFAULT 0,          -- approximate tokens of chat history in prompt
    system_prompt_tokens INT NOT NULL DEFAULT 0,    -- approximate tokens of system prompt (incl. RAG header)

    query_text TEXT,                                -- user query / search query (for audit)
    result_count INT NOT NULL DEFAULT 0,            -- search results returned
    response_tokens INT NOT NULL DEFAULT 0,         -- approximate token count of response text
    response_length INT NOT NULL DEFAULT 0,         -- len() of response text in characters
    top_similarity FLOAT NOT NULL DEFAULT 0,

    product_filter TEXT,
    version_filter TEXT,

    duration_ms FLOAT NOT NULL DEFAULT 0,
    embedding_ms FLOAT NOT NULL DEFAULT 0,
    search_ms FLOAT NOT NULL DEFAULT 0,
    llm_ms FLOAT NOT NULL DEFAULT 0,

    cogs_usd NUMERIC(12,8) NOT NULL DEFAULT 0,     -- our cost: actual LLM API / infra cost
    charge_usd NUMERIC(12,8) NOT NULL DEFAULT 0,   -- client charge: user-facing price (for billing)

    tenant_id UUID,                                 -- reserved for multi-tenant (nullable for now)

    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

-- Initial partitions (current month + next 2 months)
CREATE TABLE IF NOT EXISTS usage_log_2026_03 PARTITION OF usage_log
    FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');
CREATE TABLE IF NOT EXISTS usage_log_2026_04 PARTITION OF usage_log
    FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');
CREATE TABLE IF NOT EXISTS usage_log_2026_05 PARTITION OF usage_log
    FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');

CREATE INDEX IF NOT EXISTS idx_usage_log_channel ON usage_log (channel, created_at);
CREATE INDEX IF NOT EXISTS idx_usage_log_action ON usage_log (action, created_at);
CREATE INDEX IF NOT EXISTS idx_usage_log_request ON usage_log (request_id);
CREATE INDEX IF NOT EXISTS idx_usage_log_tenant ON usage_log (tenant_id, created_at) WHERE tenant_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_usage_log_model ON usage_log (llm_model, created_at) WHERE llm_model IS NOT NULL;

-- Shared links (public snapshots of chat sessions or individual messages)
CREATE TABLE IF NOT EXISTS shared_links (
    id SERIAL PRIMARY KEY,
    token TEXT UNIQUE NOT NULL,
    session_id INT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    message_id INT REFERENCES chat_messages(id) ON DELETE CASCADE,
    share_type TEXT NOT NULL,           -- 'session' | 'message'
    title TEXT NOT NULL DEFAULT '',
    snapshot_json JSONB NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    view_count INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_shared_links_token ON shared_links(token);
CREATE INDEX IF NOT EXISTS idx_shared_links_session ON shared_links(session_id);
