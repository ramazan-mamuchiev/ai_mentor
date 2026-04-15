-- Migration 010: MCP request log for per-tool-call audit and monitoring
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
