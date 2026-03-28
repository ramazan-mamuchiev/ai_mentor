-- 006: i18n engine + product taxonomy
-- Languages, translations, product categories, tags, search keywords

-- Languages reference table
CREATE TABLE IF NOT EXISTS languages (
    id SERIAL PRIMARY KEY,
    code VARCHAR(10) NOT NULL UNIQUE,
    name_native TEXT NOT NULL,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INT NOT NULL DEFAULT 0,
    is_system BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Translations table (unified for UI strings + taxonomy labels)
CREATE TABLE IF NOT EXISTS translations (
    id SERIAL PRIMARY KEY,
    language_id INT NOT NULL REFERENCES languages(id) ON DELETE CASCADE,
    namespace VARCHAR(50) NOT NULL DEFAULT 'ui',
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    is_system BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(language_id, namespace, key)
);

CREATE INDEX IF NOT EXISTS idx_translations_lookup
    ON translations(language_id, namespace);
CREATE INDEX IF NOT EXISTS idx_translations_key
    ON translations(namespace, key);

-- Product categories (tenant-agnostic)
CREATE TABLE IF NOT EXISTS product_categories (
    id SERIAL PRIMARY KEY,
    slug VARCHAR(100) NOT NULL UNIQUE,
    icon VARCHAR(50) DEFAULT '',
    sort_order INT NOT NULL DEFAULT 0,
    is_system BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Tags (tenant-agnostic)
CREATE TABLE IF NOT EXISTS tags (
    id SERIAL PRIMARY KEY,
    slug VARCHAR(100) NOT NULL UNIQUE,
    is_system BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Product <-> Tag many-to-many
CREATE TABLE IF NOT EXISTS product_tag_links (
    product_id INT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    tag_id INT NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (product_id, tag_id)
);

-- Search keywords per product (for BM25 boost)
CREATE TABLE IF NOT EXISTS search_keywords (
    id SERIAL PRIMARY KEY,
    product_id INT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    keyword TEXT NOT NULL,
    is_system BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT uq_search_keywords_product_keyword UNIQUE (product_id, keyword)
);

-- Add category_id FK to products (ON DELETE SET NULL: deleting category unlinks products)
ALTER TABLE products ADD COLUMN IF NOT EXISTS category_id INT REFERENCES product_categories(id) ON DELETE SET NULL;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_products_category_id ON products(category_id);
CREATE INDEX IF NOT EXISTS idx_search_keywords_product ON search_keywords(product_id);
CREATE INDEX IF NOT EXISTS idx_product_tag_links_tag ON product_tag_links(tag_id);

-- pg_trgm indexes for ILIKE text search (suggest + products?q=)
CREATE INDEX IF NOT EXISTS idx_products_name_trgm ON products USING gin (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_products_manufacturer_trgm ON products USING gin (manufacturer gin_trgm_ops);
