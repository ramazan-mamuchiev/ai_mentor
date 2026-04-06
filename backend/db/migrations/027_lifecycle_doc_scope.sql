-- Migration: Add doc_scope to api_lifecycles for vendor vs protocol classification.
-- doc_scope values: 'vendor_specific', 'industry_protocol', 'device_family', 'unknown'
-- Used to adjust quality scoring and issue severity based on document type.

BEGIN;

ALTER TABLE api_lifecycles ADD COLUMN IF NOT EXISTS doc_scope TEXT NOT NULL DEFAULT 'unknown';

COMMIT;
