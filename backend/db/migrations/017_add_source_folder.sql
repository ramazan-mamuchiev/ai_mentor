-- Add source_folder to documents: relative directory path within an archive.
-- Enables filtering by architectural layer (BL/, INTEGRATION/, MMSS/) or proto domain.
ALTER TABLE documents ADD COLUMN IF NOT EXISTS source_folder TEXT NOT NULL DEFAULT '';
