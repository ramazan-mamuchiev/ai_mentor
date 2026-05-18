-- 022: Backfill products.category for known catalog rows (one-time data fix).
--
-- Preview before deploy (same filters as UPDATEs):
--   SELECT id, slug, name, manufacturer, category FROM products ORDER BY id;
--
--   SELECT id, slug, name, manufacturer, category FROM products
--   WHERE coalesce(category, '') = ''
--     AND manufacturer ILIKE '%axxon%soft%'
--     AND name ILIKE '%confluence%'
--     AND name ILIKE '%dev%';
--
--   SELECT id, slug, name, manufacturer, category FROM products
--   WHERE coalesce(category, '') = ''
--     AND (
--       name ILIKE 'ai_mentor%'
--       OR (manufacturer ILIKE '%voitehovich%' AND name ILIKE '%ai_mentor%')
--     );
--
--   SELECT id, slug, name, manufacturer, category FROM products
--   WHERE coalesce(category, '') = ''
--     AND manufacturer ILIKE '%trezor%'
--     AND name ILIKE '%k-2%';
--
--   SELECT id, slug, name, manufacturer, category FROM products
--   WHERE coalesce(category, '') = ''
--     AND manufacturer ILIKE '%axxon%soft%'
--     AND name ILIKE '%axxonone%';

UPDATE products
SET category = 'internal_docs'
WHERE coalesce(category, '') = ''
  AND manufacturer ILIKE '%axxon%soft%'
  AND name ILIKE '%confluence%'
  AND name ILIKE '%dev%';

UPDATE products
SET category = 'platform'
WHERE coalesce(category, '') = ''
  AND (
    name ILIKE 'ai_mentor%'
    OR (manufacturer ILIKE '%voitehovich%' AND name ILIKE '%ai_mentor%')
  );

UPDATE products
SET category = 'perimeter_security'
WHERE coalesce(category, '') = ''
  AND manufacturer ILIKE '%trezor%'
  AND name ILIKE '%k-2%';

UPDATE products
SET category = 'video_surveillance'
WHERE coalesce(category, '') = ''
  AND manufacturer ILIKE '%axxon%soft%'
  AND name ILIKE '%axxonone%';
