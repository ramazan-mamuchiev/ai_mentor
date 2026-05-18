-- 013: Add sources JSONB to mcp_request_log (RAG search results metadata)
ALTER TABLE mcp_request_log ADD COLUMN IF NOT EXISTS sources JSONB;
