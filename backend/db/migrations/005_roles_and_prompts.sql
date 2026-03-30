-- 005: RBAC roles directory + prompt templates
-- Creates roles, tenant_roles, prompt_templates tables
-- Seeds system roles (admin, user) and migrates existing Tenant.role data

-- === Roles ===
CREATE TABLE IF NOT EXISTS roles (
    id SERIAL PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    is_system BOOLEAN NOT NULL DEFAULT FALSE,
    priority INTEGER NOT NULL DEFAULT 0,
    permissions JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tenant_roles (
    id SERIAL PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    assigned_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, role_id)
);
CREATE INDEX IF NOT EXISTS idx_tenant_roles_tenant ON tenant_roles(tenant_id);

-- Seed system roles
INSERT INTO roles (slug, name, description, is_system, priority, permissions)
VALUES (
    'admin', 'Administrator', 'Full platform access', TRUE, 100,
    '{"features":{"chat":true,"chat.feedback":true,"documents.upload":true,"documents.delete":true,"documents.view":true,"documents.reindex":true,"documents.sync":true,"products.view":true,"products.edit":true,"products.delete":true,"share":true,"reindex":true,"analytics":true,"settings":true,"admin":true,"admin.tenants":true,"admin.documents":true,"admin.chats":true,"admin.logs":true,"admin.stats":true,"admin.roles":true,"admin.prompts":true,"mcp":true},"limits":{},"chat_context":{"suggestion_template_role":"default","allowed_query_types":["overview","technical","code","comparison","troubleshooting","chitchat"]}}'
), (
    'user', 'Standard User', 'Default access for new users', TRUE, 0,
    '{"features":{"chat":true,"chat.feedback":true,"documents.upload":false,"documents.delete":false,"documents.view":true,"documents.reindex":false,"documents.sync":false,"products.view":true,"products.edit":false,"products.delete":false,"share":true,"reindex":false,"analytics":true,"settings":true,"admin":false,"mcp":true},"limits":{"max_documents":100,"max_tokens_per_day":50000,"max_file_size_mb":50,"max_sessions":500,"max_api_keys":5},"chat_context":{"suggestion_template_role":"default","allowed_query_types":["overview","technical","code","comparison","troubleshooting","chitchat"]}}'
), (
    'publisher', 'Documentation Publisher', 'Can upload, delete, reindex and sync documentation', TRUE, 50,
    '{"features":{"chat":true,"chat.feedback":true,"documents.upload":true,"documents.delete":true,"documents.view":true,"documents.reindex":true,"documents.sync":true,"products.view":true,"products.edit":false,"products.delete":false,"share":true,"reindex":true,"analytics":true,"settings":true,"admin":false,"mcp":true},"limits":{"max_documents":500,"max_tokens_per_day":100000,"max_file_size_mb":100,"max_sessions":500,"max_api_keys":10},"chat_context":{"suggestion_template_role":"default","allowed_query_types":["overview","technical","code","comparison","troubleshooting","chitchat"]}}'
) ON CONFLICT (slug) DO NOTHING;

-- Migrate existing tenants: assign role based on old Tenant.role column
INSERT INTO tenant_roles (tenant_id, role_id, assigned_at)
SELECT t.id, r.id, NOW()
FROM tenants t
JOIN roles r ON r.slug = t.role
WHERE NOT EXISTS (
    SELECT 1 FROM tenant_roles tr WHERE tr.tenant_id = t.id AND tr.role_id = r.id
);

-- === Prompt Templates ===
CREATE TABLE IF NOT EXISTS prompt_templates (
    id SERIAL PRIMARY KEY,
    query_type TEXT NOT NULL,
    role_id INTEGER REFERENCES roles(id) ON DELETE CASCADE,
    parent_id INTEGER REFERENCES prompt_templates(id) ON DELETE SET NULL,
    is_system BOOLEAN NOT NULL DEFAULT FALSE,
    is_customized BOOLEAN NOT NULL DEFAULT FALSE,
    body TEXT NOT NULL DEFAULT '',
    classifier_hint TEXT NOT NULL DEFAULT '',
    max_response_tokens INTEGER,
    rag_top_k INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(query_type, role_id)
);
CREATE INDEX IF NOT EXISTS idx_prompt_templates_query_type ON prompt_templates(query_type);
