CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

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
ALTER TABLE documents ADD COLUMN IF NOT EXISTS ocr_prompt_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS ocr_completion_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS ocr_model TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS detected_language TEXT;

-- Source container (archive filename or URL the document was extracted from)
ALTER TABLE documents ADD COLUMN IF NOT EXISTS source_container TEXT;

-- Timestamp when document entered 'processing' state (for accurate stale detection)
ALTER TABLE documents ADD COLUMN IF NOT EXISTS processing_started_at TIMESTAMPTZ;

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

-- Product keys extraction metrics (LLM-based search key generation)
ALTER TABLE documents ADD COLUMN IF NOT EXISTS product_keys_prompt_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS product_keys_completion_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS product_keys_ms FLOAT NOT NULL DEFAULT 0;

-- Confluence crawl checkpoint (resumable BFS state for long-running crawls)
ALTER TABLE documents ADD COLUMN IF NOT EXISTS crawl_checkpoint JSONB;

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

-- YAML front matter metadata (layer, topic, doc_number, related_docs)
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS layer TEXT;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS topic TEXT;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS doc_number TEXT;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS related_docs JSONB;
CREATE INDEX IF NOT EXISTS idx_chunks_layer ON chunks(layer);

-- Full-text search column (BM25 via tsvector for hybrid search)
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS tsv tsvector;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS language VARCHAR(10);
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS tsv_lang tsvector;

CREATE OR REPLACE FUNCTION chunks_tsv_trigger() RETURNS trigger AS $$
DECLARE
    entity_text TEXT := '';
    kw TEXT;
    lang_config REGCONFIG;
BEGIN
    IF NEW.entities IS NOT NULL AND NEW.entities != '{}' THEN
        FOR kw IN SELECT jsonb_array_elements_text(v)
            FROM jsonb_each(NEW.entities) AS e(k, v)
            WHERE jsonb_typeof(v) = 'array'
        LOOP
            entity_text := entity_text || ' ' || kw;
        END LOOP;
    END IF;

    -- Simple tsvector (no stemming, exact term matching)
    NEW.tsv :=
        setweight(to_tsvector('simple', COALESCE(NEW.heading_path, '')), 'A') ||
        setweight(to_tsvector('simple', entity_text), 'B') ||
        setweight(to_tsvector('simple', COALESCE(NEW.doc_type, '')), 'B') ||
        setweight(to_tsvector('simple', COALESCE(NEW.content_clean, NEW.content, '')), 'C');

    -- Language-aware tsvector (with stemming)
    IF NEW.language = 'ru' THEN
        lang_config := 'russian';
    ELSIF NEW.language = 'en' THEN
        lang_config := 'english';
    ELSE
        lang_config := 'simple';
    END IF;

    NEW.tsv_lang :=
        setweight(to_tsvector(lang_config, COALESCE(NEW.heading_path, '')), 'A') ||
        setweight(to_tsvector(lang_config, entity_text), 'B') ||
        setweight(to_tsvector(lang_config, COALESCE(NEW.content_clean, NEW.content, '')), 'C');

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_chunks_tsv ON chunks;
CREATE TRIGGER trg_chunks_tsv BEFORE INSERT OR UPDATE OF content, content_clean, heading_path, doc_type, entities, language ON chunks
    FOR EACH ROW EXECUTE FUNCTION chunks_tsv_trigger();

-- Backfill existing rows that lack tsv (using 'simple' config with setweight for multilingual support)
UPDATE chunks SET tsv =
    setweight(to_tsvector('simple', COALESCE(heading_path, '')), 'A') ||
    setweight(to_tsvector('simple', COALESCE(doc_type, '')), 'B') ||
    setweight(to_tsvector('simple', COALESCE(content_clean, content, '')), 'C')
WHERE tsv IS NULL;

-- GIN index for full-text search
CREATE INDEX IF NOT EXISTS idx_chunks_tsv ON chunks USING gin(tsv);
CREATE INDEX IF NOT EXISTS idx_chunks_tsv_lang ON chunks USING gin(tsv_lang);
CREATE INDEX IF NOT EXISTS idx_chunks_language ON chunks(language);

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

-- Summary buffer memory (conversation history summarization)
ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS history_summary TEXT;
ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS summary_up_to_message_id INT;

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

-- Feedback on assistant messages (thumbs up/down + optional comment)
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS feedback TEXT CHECK (feedback IN ('up', 'down'));
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS feedback_comment TEXT;

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

-- Product document list (WHERE product_id = ? ORDER BY uploaded_at DESC)
CREATE INDEX IF NOT EXISTS idx_documents_product_uploaded ON documents(product_id, uploaded_at DESC);

-- FK join acceleration (PostgreSQL does not auto-index FK columns)
CREATE INDEX IF NOT EXISTS idx_documents_firmware_version ON documents(firmware_version_id);

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

-- Migration: make session_id nullable (debug shares may not have a session)
ALTER TABLE shared_links ALTER COLUMN session_id DROP NOT NULL;

-- Migration: add TTL support for debug shares (NULL = permanent)
ALTER TABLE shared_links ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;

-- Completion tracking (finish_reason + continuations for truncation diagnostics)
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS finish_reason TEXT;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS continuations INT NOT NULL DEFAULT 0;

-- Extended RAG debug fields (persisted for session replay)
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS query_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS history_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS system_prompt_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS effective_top_k INT;

-- Classify step
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS classify_input TEXT;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS classify_product TEXT;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS classify_prompt_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS classify_completion_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS classify_total_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS classify_model TEXT;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS classify_ms FLOAT;

-- Product resolve step (LLM-based product name resolution)
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS resolve_prompt_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS resolve_completion_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS resolve_total_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS resolve_model TEXT;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS resolve_ms FLOAT;

-- Rerank step
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS rerank_prompt_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS rerank_completion_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS rerank_total_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS rerank_model TEXT;

-- Decompose step
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS decompose_used BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS decompose_sub_queries JSONB;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS decompose_sub_products JSONB;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS decompose_prompt_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS decompose_completion_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS decompose_total_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS decompose_model TEXT;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS decompose_ms FLOAT;

-- Web search step
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS web_search_used BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS web_search_queries JSONB;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS web_search_sources_count INT NOT NULL DEFAULT 0;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS web_search_prompt_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS web_search_completion_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS web_search_total_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS web_search_model TEXT;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS web_search_ms FLOAT;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS web_search_context_length INT NOT NULL DEFAULT 0;

-- Rewrite step
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS rewrite_prompt_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS rewrite_completion_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS rewrite_total_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS rewrite_model TEXT;

-- Rephrase / retry step
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS retry_used BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS rephrase_ms FLOAT;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS rephrase_query TEXT;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS rephrase_prompt_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS rephrase_completion_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS rephrase_total_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS rephrase_model TEXT;

-- Embedding API
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS embedding_api_tokens INT NOT NULL DEFAULT 0;

-- Summary step
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS summary_prompt_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS summary_completion_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS summary_total_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS summary_model TEXT;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS summary_ms FLOAT;

-- Document usage log (per-document attribution for author remuneration)
CREATE TABLE IF NOT EXISTS document_usage_log (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    request_id TEXT NOT NULL,
    session_id INT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    message_id INT NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
    document_id INT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    product_id INT REFERENCES products(id) ON DELETE SET NULL,

    chunk_id BIGINT,
    heading_path TEXT NOT NULL DEFAULT '',
    similarity FLOAT NOT NULL DEFAULT 0,
    context_tokens INT NOT NULL DEFAULT 0,

    query_text TEXT,
    query_type TEXT,
    sub_query TEXT,

    charge_usd NUMERIC(12,8) NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_dul_request ON document_usage_log(request_id);
CREATE INDEX IF NOT EXISTS idx_dul_document ON document_usage_log(document_id, created_at);
CREATE INDEX IF NOT EXISTS idx_dul_product ON document_usage_log(product_id, created_at);
CREATE INDEX IF NOT EXISTS idx_dul_session ON document_usage_log(session_id);
CREATE INDEX IF NOT EXISTS idx_dul_created ON document_usage_log(created_at);

-- Suggestion templates (question templates with {product} placeholder for empty-state chips)
CREATE TABLE IF NOT EXISTS suggestion_templates (
    id SERIAL PRIMARY KEY,
    role TEXT NOT NULL DEFAULT 'default',
    lang TEXT NOT NULL DEFAULT 'en',
    template TEXT NOT NULL,
    sort_order INT NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (role, lang, template)
);
CREATE INDEX IF NOT EXISTS idx_st_role_lang ON suggestion_templates(role, lang, is_active);

-- Seed suggestion templates (idempotent)
INSERT INTO suggestion_templates (role, lang, template, sort_order) VALUES
    ('default', 'en', 'Tell me about {product}', 1),
    ('default', 'ru', 'Расскажи про {product}', 1),
    ('default', 'en', 'What API methods does {product} have?', 2),
    ('default', 'ru', 'Какие API-методы есть у {product}?', 2),
    ('default', 'en', 'How does authentication work in {product}?', 3),
    ('default', 'ru', 'Как устроена авторизация в {product}?', 3),
    ('default', 'en', 'What events does {product} support?', 4),
    ('default', 'ru', 'Какие события поддерживает {product}?', 4),
    ('default', 'en', 'How to get started with {product}?', 5),
    ('default', 'ru', 'Как начать работу с {product}?', 5),
    ('default', 'en', 'What data formats does {product} use?', 6),
    ('default', 'ru', 'Какие форматы данных использует {product}?', 6),
    ('default', 'en', 'What are the API rate limits in {product}?', 7),
    ('default', 'ru', 'Какие ограничения API у {product}?', 7),
    ('default', 'en', 'How to handle errors in {product}?', 8),
    ('default', 'ru', 'Как обрабатывать ошибки в {product}?', 8),
    ('default', 'en', 'Does {product} support webhooks?', 9),
    ('default', 'ru', 'Поддерживает ли {product} вебхуки?', 9),
    ('default', 'en', 'How to subscribe to events in {product}?', 10),
    ('default', 'ru', 'Как подписаться на события в {product}?', 10),
    ('default', 'en', 'What SDK or libraries does {product} provide?', 11),
    ('default', 'ru', 'Какие SDK или библиотеки есть у {product}?', 11),
    ('default', 'en', 'How to configure {product} via API?', 12),
    ('default', 'ru', 'Как настроить {product} через API?', 12),
    ('default', 'en', 'What security features does {product} have?', 13),
    ('default', 'ru', 'Какие функции безопасности есть у {product}?', 13),
    ('default', 'en', 'How to migrate between versions of {product}?', 14),
    ('default', 'ru', 'Как мигрировать между версиями {product}?', 14),
    ('default', 'en', 'What protocols does {product} support?', 15),
    ('default', 'ru', 'Какие протоколы поддерживает {product}?', 15),
    ('default', 'en', 'Show the architecture of {product}', 16),
    ('default', 'ru', 'Покажи архитектуру {product}', 16)
ON CONFLICT (role, lang, template) DO NOTHING;

-- MCP request log (per-tool-call audit for MCP monitoring)
CREATE TABLE IF NOT EXISTS mcp_request_log (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    tenant_id UUID NOT NULL,
    api_key_id UUID NOT NULL,
    request_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    query_text TEXT,
    product_filter TEXT,
    version_filter TEXT,
    doc_type_filter TEXT,
    result_count INT NOT NULL DEFAULT 0,
    top_similarity FLOAT NOT NULL DEFAULT 0,
    response_length INT NOT NULL DEFAULT 0,
    query_tokens INT NOT NULL DEFAULT 0,
    response_tokens INT NOT NULL DEFAULT 0,
    embedding_tokens INT NOT NULL DEFAULT 0,
    rerank_prompt_tokens INT NOT NULL DEFAULT 0,
    rerank_completion_tokens INT NOT NULL DEFAULT 0,
    rerank_total_tokens INT NOT NULL DEFAULT 0,
    rerank_model TEXT,
    duration_ms FLOAT NOT NULL DEFAULT 0,
    embed_ms FLOAT NOT NULL DEFAULT 0,
    search_ms FLOAT NOT NULL DEFAULT 0,
    rerank_ms FLOAT NOT NULL DEFAULT 0,
    cogs_usd NUMERIC(12,8) NOT NULL DEFAULT 0,
    charge_usd NUMERIC(12,8) NOT NULL DEFAULT 0,
    client_ip TEXT,
    user_agent TEXT,
    error TEXT,
    status TEXT NOT NULL DEFAULT 'ok'
);

CREATE INDEX IF NOT EXISTS idx_mcp_req_log_tenant ON mcp_request_log(tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_mcp_req_log_api_key ON mcp_request_log(api_key_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_mcp_req_log_tool ON mcp_request_log(tool_name, created_at);
CREATE INDEX IF NOT EXISTS idx_mcp_req_log_request ON mcp_request_log(request_id);

-- Product resolve metrics (LLM-based product name resolution)
ALTER TABLE mcp_request_log ADD COLUMN IF NOT EXISTS resolve_prompt_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE mcp_request_log ADD COLUMN IF NOT EXISTS resolve_completion_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE mcp_request_log ADD COLUMN IF NOT EXISTS resolve_model TEXT;
ALTER TABLE mcp_request_log ADD COLUMN IF NOT EXISTS resolve_ms FLOAT NOT NULL DEFAULT 0;

-- Sources for RAG tool calls (search results metadata)
ALTER TABLE mcp_request_log ADD COLUMN IF NOT EXISTS sources JSONB;

-- Product search keys for LLM-based product resolution
CREATE TABLE IF NOT EXISTS product_search_keys (
    id SERIAL PRIMARY KEY,
    product_id INT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    document_id INT REFERENCES documents(id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'llm',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(product_id, document_id, key)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_psk_product_null_doc_key
    ON product_search_keys(product_id, key) WHERE document_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_psk_product ON product_search_keys(product_id);
CREATE INDEX IF NOT EXISTS idx_psk_document ON product_search_keys(document_id) WHERE document_id IS NOT NULL;

-- Migration: drop legacy product_aliases if it exists
DROP TABLE IF EXISTS product_aliases;

-- Migration: chat_session_id in usage_log for charge aggregation
ALTER TABLE usage_log ADD COLUMN IF NOT EXISTS chat_session_id INT;
CREATE INDEX IF NOT EXISTS idx_usage_log_chat_session ON usage_log (chat_session_id, created_at) WHERE chat_session_id IS NOT NULL;

-- RAG evaluation runs
CREATE TABLE IF NOT EXISTS rag_eval_runs (
    id SERIAL PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'running',
    triggered_by TEXT NOT NULL DEFAULT '',
    error_message TEXT,
    progress_percent INT NOT NULL DEFAULT 0,
    progress_stage TEXT NOT NULL DEFAULT '',
    sample_size INT NOT NULL DEFAULT 50,
    eval_model TEXT NOT NULL DEFAULT '',
    context_precision FLOAT,
    mrr FLOAT,
    empty_retrieval_rate FLOAT,
    similarity_p50 FLOAT,
    similarity_p75 FLOAT,
    similarity_p90 FLOAT,
    search_latency_p50_ms FLOAT,
    search_latency_p95_ms FLOAT,
    faithfulness FLOAT,
    answer_relevance FLOAT,
    feedback_positive_rate FLOAT,
    no_answer_rate FLOAT,
    vector_count INT,
    vector_search_ms FLOAT,
    hnsw_index_size_mb FLOAT,
    e2e_latency_p50_ms FLOAT,
    e2e_latency_p95_ms FLOAT,
    metrics_by_query_type JSONB,
    metrics_by_product JSONB,
    details JSONB
);

CREATE INDEX IF NOT EXISTS idx_rag_eval_runs_status ON rag_eval_runs(status);
CREATE INDEX IF NOT EXISTS idx_rag_eval_runs_started ON rag_eval_runs(started_at);

-- API lifecycle analysis (per-document and per-product merged)
-- document_id NULL = product-level (merged) lifecycle; NOT NULL = per-document lifecycle
CREATE TABLE IF NOT EXISTS api_lifecycles (
    id BIGSERIAL PRIMARY KEY,
    document_id INT REFERENCES documents(id) ON DELETE CASCADE,
    product_id INT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    phases JSONB NOT NULL DEFAULT '[]',
    unique_patterns JSONB NOT NULL DEFAULT '[]',
    dependency_chains JSONB NOT NULL DEFAULT '[]',
    code_skeleton TEXT,
    validation_issues JSONB NOT NULL DEFAULT '[]',
    validation_retries INT NOT NULL DEFAULT 0,
    prompt_tokens INT NOT NULL DEFAULT 0,
    completion_tokens INT NOT NULL DEFAULT 0,
    analysis_ms FLOAT NOT NULL DEFAULT 0,
    model TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_api_lifecycles_doc
    ON api_lifecycles(document_id) WHERE document_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_api_lifecycles_product_merged
    ON api_lifecycles(product_id) WHERE document_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_api_lifecycles_product ON api_lifecycles(product_id);
CREATE INDEX IF NOT EXISTS idx_api_lifecycles_status ON api_lifecycles(status);

-- Source document issues found during lifecycle analysis (annotations, not modifying originals)
CREATE TABLE IF NOT EXISTS doc_issue_annotations (
    id BIGSERIAL PRIMARY KEY,
    document_id INT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    product_id INT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    chunk_id BIGINT REFERENCES chunks(id) ON DELETE SET NULL,
    issue_type TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'warning',
    description TEXT NOT NULL,
    affected_entity TEXT,
    suggestion TEXT,
    detected_by TEXT NOT NULL DEFAULT 'lifecycle_analysis',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_doc_issues_document ON doc_issue_annotations(document_id);
CREATE INDEX IF NOT EXISTS idx_doc_issues_product ON doc_issue_annotations(product_id);
CREATE INDEX IF NOT EXISTS idx_doc_issues_type ON doc_issue_annotations(issue_type);

-- Document lifecycle analysis metrics
ALTER TABLE documents ADD COLUMN IF NOT EXISTS lifecycle_prompt_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS lifecycle_completion_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS lifecycle_ms FLOAT NOT NULL DEFAULT 0;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS lifecycle_status TEXT NOT NULL DEFAULT '';

-- Migration tracking
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
