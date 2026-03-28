-- Rollback: remove i18n, taxonomy tables and slug columns from products.
-- Idempotent: uses IF EXISTS / CASCADE everywhere.

-- 1. Drop translations (depends on languages)
DROP TABLE IF EXISTS translations CASCADE;

-- 2. Drop languages
DROP TABLE IF EXISTS languages CASCADE;

-- 3. Drop taxonomy link tables first (FKs)
DROP TABLE IF EXISTS product_tag_links CASCADE;
DROP TABLE IF EXISTS search_keywords CASCADE;

-- 4. Drop taxonomy tables
DROP TABLE IF EXISTS tags CASCADE;
DROP TABLE IF EXISTS product_categories CASCADE;

-- 5. Drop slug columns and category_id FK from products
ALTER TABLE products DROP CONSTRAINT IF EXISTS products_manufacturer_slug_slug_key;
DROP INDEX IF EXISTS idx_products_slug;
DROP INDEX IF EXISTS idx_products_category_id;
ALTER TABLE products DROP COLUMN IF EXISTS slug;
ALTER TABLE products DROP COLUMN IF EXISTS manufacturer_slug;
ALTER TABLE products DROP COLUMN IF EXISTS category_id;
