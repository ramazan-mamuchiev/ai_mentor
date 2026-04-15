-- Migration: Support chunked lifecycle extraction for large documents.
-- Large docs now produce multiple lifecycle rows per document (one per batch + merged).
-- batch_index NULL = merged/single lifecycle; integer = batch-level partial lifecycle.

BEGIN;

-- Add batch_index column
ALTER TABLE api_lifecycles ADD COLUMN IF NOT EXISTS batch_index INT;

-- Drop the old unique index that enforced 1:1 document→lifecycle
DROP INDEX IF EXISTS idx_api_lifecycles_doc;

-- Replace with non-unique index (large docs may have N rows per document_id)
CREATE INDEX IF NOT EXISTS idx_api_lifecycles_doc
    ON api_lifecycles(document_id) WHERE document_id IS NOT NULL;

-- Tighten the merged lifecycle constraint: only one product-level merged row
-- (document_id IS NULL AND batch_index IS NULL)
DROP INDEX IF EXISTS idx_api_lifecycles_product_merged;
CREATE UNIQUE INDEX IF NOT EXISTS idx_api_lifecycles_product_merged
    ON api_lifecycles(product_id) WHERE document_id IS NULL AND batch_index IS NULL;

COMMIT;
