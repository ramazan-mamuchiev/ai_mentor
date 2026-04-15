-- Migration 003: Add api_key_id to audit/usage tables for per-key tracking
-- Also backfill chat_sessions.tenant_id for existing data before tenant isolation

ALTER TABLE usage_log ADD COLUMN IF NOT EXISTS api_key_id UUID;
CREATE INDEX IF NOT EXISTS idx_usage_log_api_key
  ON usage_log (api_key_id, created_at) WHERE api_key_id IS NOT NULL;

ALTER TABLE search_analytics ADD COLUMN IF NOT EXISTS api_key_id UUID;
CREATE INDEX IF NOT EXISTS idx_search_analytics_api_key
  ON search_analytics (api_key_id) WHERE api_key_id IS NOT NULL;

ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS api_key_id UUID;
CREATE INDEX IF NOT EXISTS idx_chat_sessions_api_key
  ON chat_sessions (api_key_id) WHERE api_key_id IS NOT NULL;

ALTER TABLE document_usage_log ADD COLUMN IF NOT EXISTS api_key_id UUID;
CREATE INDEX IF NOT EXISTS idx_dul_api_key
  ON document_usage_log (api_key_id) WHERE api_key_id IS NOT NULL;

-- Backfill: assign orphaned chat_sessions to the single existing tenant
UPDATE chat_sessions
   SET tenant_id = (SELECT id FROM tenants LIMIT 1)
 WHERE tenant_id IS NULL
   AND EXISTS (SELECT 1 FROM tenants);
