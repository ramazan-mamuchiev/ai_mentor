-- Add slug column to products for human-readable URLs.
-- Backfill existing rows: slug = lower(manufacturer || '-' || name), sanitised to [a-z0-9-].

ALTER TABLE products ADD COLUMN IF NOT EXISTS slug TEXT;

-- Backfill slugs from manufacturer + name
UPDATE products
SET slug = regexp_replace(
    regexp_replace(
        lower(
            CASE WHEN manufacturer != '' THEN manufacturer || ' ' || name
                 ELSE name
            END
        ),
        '[^a-z0-9]+', '-', 'g'
    ),
    '^-+|-+$', '', 'g'
)
WHERE slug IS NULL OR slug = '';

-- Handle duplicates by appending -<id>
UPDATE products p
SET slug = p.slug || '-' || p.id
WHERE EXISTS (
    SELECT 1 FROM products p2
    WHERE p2.slug = p.slug AND p2.id < p.id
);

-- Now enforce constraints
ALTER TABLE products ALTER COLUMN slug SET NOT NULL;
ALTER TABLE products ALTER COLUMN slug SET DEFAULT '';
CREATE UNIQUE INDEX IF NOT EXISTS idx_products_slug ON products (slug);
