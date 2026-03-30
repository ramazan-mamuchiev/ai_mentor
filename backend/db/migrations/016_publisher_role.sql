-- 016: Add publisher role + new permission keys for admin
-- Publisher role: can upload, delete, reindex, and sync documentation

INSERT INTO roles (slug, name, description, is_system, priority, permissions)
VALUES (
    'publisher',
    'Documentation Publisher',
    'Can upload, delete, reindex and sync documentation',
    TRUE,
    50,
    '{
      "features": {
        "chat": true,
        "chat.feedback": true,
        "documents.upload": true,
        "documents.delete": true,
        "documents.view": true,
        "documents.reindex": true,
        "documents.sync": true,
        "products.view": true,
        "products.edit": false,
        "products.delete": false,
        "share": true,
        "reindex": true,
        "analytics": true,
        "settings": true,
        "admin": false,
        "mcp": true
      },
      "limits": {
        "max_documents": 500,
        "max_tokens_per_day": 100000,
        "max_file_size_mb": 100,
        "max_sessions": 500,
        "max_api_keys": 10
      },
      "chat_context": {
        "suggestion_template_role": "default",
        "allowed_query_types": ["overview","technical","code","comparison","troubleshooting","chitchat"]
      }
    }'
) ON CONFLICT (slug) DO NOTHING;

-- Add new permission keys to admin role
UPDATE roles
SET permissions = permissions
    || jsonb_build_object('features',
        (permissions->'features')
            || '{"documents.reindex": true, "documents.sync": true}'::jsonb
       )
WHERE slug = 'admin';

-- Add new permission keys (false) to user role for consistency
UPDATE roles
SET permissions = permissions
    || jsonb_build_object('features',
        (permissions->'features')
            || '{"documents.reindex": false, "documents.sync": false}'::jsonb
       )
WHERE slug = 'user';
