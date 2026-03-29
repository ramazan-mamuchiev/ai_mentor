-- 012: Product search keys for LLM-based product resolution
-- Replaces product_aliases with product_search_keys (flat key list, no key_type)

-- Drop legacy table
DROP TABLE IF EXISTS product_aliases;

-- Create new table
CREATE TABLE IF NOT EXISTS product_search_keys (
    id SERIAL PRIMARY KEY,
    product_id INT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    document_id INT REFERENCES documents(id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'llm',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(product_id, document_id, key)
);
CREATE INDEX IF NOT EXISTS idx_psk_product ON product_search_keys(product_id);
CREATE INDEX IF NOT EXISTS idx_psk_document ON product_search_keys(document_id) WHERE document_id IS NOT NULL;

-- Product resolve metrics on mcp_request_log
ALTER TABLE mcp_request_log ADD COLUMN IF NOT EXISTS resolve_prompt_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE mcp_request_log ADD COLUMN IF NOT EXISTS resolve_completion_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE mcp_request_log ADD COLUMN IF NOT EXISTS resolve_model TEXT;
ALTER TABLE mcp_request_log ADD COLUMN IF NOT EXISTS resolve_ms FLOAT NOT NULL DEFAULT 0;

-- Product resolve metrics on chat_message_analytics
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS resolve_prompt_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS resolve_completion_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS resolve_total_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS resolve_model TEXT;
ALTER TABLE chat_message_analytics ADD COLUMN IF NOT EXISTS resolve_ms FLOAT;

-- Product keys extraction metrics on documents
ALTER TABLE documents ADD COLUMN IF NOT EXISTS product_keys_prompt_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS product_keys_completion_tokens INT NOT NULL DEFAULT 0;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS product_keys_ms FLOAT NOT NULL DEFAULT 0;
