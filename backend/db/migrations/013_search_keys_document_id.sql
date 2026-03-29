-- 013: Add document_id to product_search_keys for per-document key tracking
-- LLM keys (source='llm') keep document_id NULL (they belong to the product).
-- Chunk keys (source='chunk') get document_id set to the originating document.

ALTER TABLE product_search_keys ADD COLUMN IF NOT EXISTS document_id INT REFERENCES documents(id) ON DELETE CASCADE;

-- Replace old unique constraint (product_id, key) with (product_id, document_id, key)
-- so different documents of the same product can have the same key.
ALTER TABLE product_search_keys DROP CONSTRAINT IF EXISTS product_search_keys_product_id_key_key;
ALTER TABLE product_search_keys ADD CONSTRAINT product_search_keys_product_id_document_id_key_key
    UNIQUE (product_id, document_id, key);

-- Partial unique index for LLM keys where document_id IS NULL
-- (UNIQUE constraint treats NULLs as distinct, so we need this for dedup)
CREATE UNIQUE INDEX IF NOT EXISTS idx_psk_product_null_doc_key
    ON product_search_keys(product_id, key) WHERE document_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_psk_document ON product_search_keys(document_id) WHERE document_id IS NOT NULL;
