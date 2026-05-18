-- Migration 002: Add tenant_id to all data tables for multi-tenancy

ALTER TABLE products ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS idx_products_tenant ON products(tenant_id) WHERE tenant_id IS NOT NULL;

ALTER TABLE documents ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS idx_documents_tenant ON documents(tenant_id) WHERE tenant_id IS NOT NULL;

ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS idx_chat_sessions_tenant ON chat_sessions(tenant_id) WHERE tenant_id IS NOT NULL;

ALTER TABLE shared_links ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS idx_shared_links_tenant ON shared_links(tenant_id) WHERE tenant_id IS NOT NULL;

ALTER TABLE search_analytics ADD COLUMN IF NOT EXISTS tenant_id UUID;
CREATE INDEX IF NOT EXISTS idx_search_analytics_tenant ON search_analytics(tenant_id) WHERE tenant_id IS NOT NULL;

ALTER TABLE reindex_jobs ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS idx_reindex_jobs_tenant ON reindex_jobs(tenant_id) WHERE tenant_id IS NOT NULL;

ALTER TABLE upload_sessions ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS idx_upload_sessions_tenant ON upload_sessions(tenant_id) WHERE tenant_id IS NOT NULL;

ALTER TABLE document_usage_log ADD COLUMN IF NOT EXISTS tenant_id UUID;
CREATE INDEX IF NOT EXISTS idx_dul_tenant ON document_usage_log(tenant_id) WHERE tenant_id IS NOT NULL;
