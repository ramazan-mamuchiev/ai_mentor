-- Drop unused icon column from product_categories
ALTER TABLE product_categories DROP COLUMN IF EXISTS icon;
