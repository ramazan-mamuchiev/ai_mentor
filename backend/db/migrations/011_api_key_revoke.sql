-- 011: Add revoke tracking columns to api_keys
ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS revoked_at TIMESTAMPTZ;
ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS revoke_reason TEXT;

-- Backfill revoked_at for already-deactivated keys
UPDATE api_keys SET revoked_at = NOW() WHERE is_active = false AND revoked_at IS NULL;
