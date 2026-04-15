-- Migration: Remove firmware_versions table, move version to products
-- This migration flattens the product+version model: each unique (product, version)
-- becomes a separate row in products.

BEGIN;

-- 1. Add version column to products
ALTER TABLE products ADD COLUMN IF NOT EXISTS version TEXT NOT NULL DEFAULT '';

-- 2. For each (product, firmware_version) pair, create a separate product row
-- with the version from firmware_versions (only if the table still exists).
DO $$
DECLARE
    r RECORD;
    new_product_id INT;
    has_fw_table BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = current_schema() AND table_name = 'firmware_versions'
    ) INTO has_fw_table;

    IF NOT has_fw_table THEN
        RETURN;
    END IF;

    -- Single-version products: just update product.version
    UPDATE products p
    SET version = fw.version
    FROM firmware_versions fw
    WHERE fw.product_id = p.id
    AND (SELECT COUNT(*) FROM firmware_versions WHERE product_id = p.id) = 1;

    -- Multi-version products: create new product rows and reassign documents
    FOR r IN (
        SELECT fw.id AS fw_id, fw.product_id, fw.version,
               p.name, p.manufacturer, p.model, p.category, p.tenant_id, p.sync_status,
               ROW_NUMBER() OVER (PARTITION BY fw.product_id ORDER BY fw.version) AS rn
        FROM firmware_versions fw
        JOIN products p ON p.id = fw.product_id
        WHERE (SELECT COUNT(*) FROM firmware_versions WHERE product_id = fw.product_id) > 1
    ) LOOP
        IF r.rn = 1 THEN
            UPDATE products SET version = r.version WHERE id = r.product_id;
        ELSE
            INSERT INTO products (name, manufacturer, model, version, category, slug, tenant_id, sync_status, created_at)
            VALUES (r.name, r.manufacturer, r.model, r.version, r.category,
                    LOWER(REGEXP_REPLACE(
                        TRIM(COALESCE(NULLIF(r.manufacturer, ''), '') || ' ' || r.name || ' ' || r.version),
                        '[^a-z0-9]+', '-', 'gi'
                    )),
                    r.tenant_id, r.sync_status, NOW())
            RETURNING id INTO new_product_id;

            UPDATE documents SET product_id = new_product_id
            WHERE product_id = r.product_id AND firmware_version_id = r.fw_id;

            UPDATE api_lifecycles SET product_id = new_product_id
            WHERE product_id = r.product_id;

            UPDATE product_search_keys SET product_id = new_product_id
            WHERE product_id = r.product_id
            AND document_id IN (SELECT id FROM documents WHERE product_id = new_product_id);

            UPDATE doc_issue_annotations SET product_id = new_product_id
            WHERE product_id = r.product_id
            AND document_id IN (SELECT id FROM documents WHERE product_id = new_product_id);
        END IF;
    END LOOP;
END $$;

-- 3. Update unique constraint on products
ALTER TABLE products DROP CONSTRAINT IF EXISTS products_manufacturer_model_key;
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'products_manufacturer_model_version_key'
    ) THEN
        ALTER TABLE products ADD CONSTRAINT products_manufacturer_model_version_key UNIQUE (manufacturer, model, version);
    END IF;
END $$;

-- 4. Update product slugs to include version
UPDATE products SET slug = LOWER(REGEXP_REPLACE(
    TRIM(
        CASE WHEN manufacturer != '' THEN manufacturer || ' ' ELSE '' END
        || name
        || CASE WHEN version != '' THEN ' ' || version ELSE '' END
    ),
    '[^a-z0-9]+', '-', 'gi'
)) WHERE version != '';

-- 5. Drop firmware_version_id from documents
ALTER TABLE documents DROP COLUMN IF EXISTS firmware_version_id;

-- 6. Drop firmware_versions table
DROP TABLE IF EXISTS firmware_versions;

-- 7. Drop the old index if it exists
DROP INDEX IF EXISTS idx_documents_firmware_version;

COMMIT;
