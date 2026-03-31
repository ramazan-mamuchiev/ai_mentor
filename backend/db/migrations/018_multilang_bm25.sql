-- Migration 018: Language-aware BM25
-- Adds language column to chunks and a stemmed tsvector (tsv_lang)
-- for proper morphological matching (russian/english).

ALTER TABLE chunks ADD COLUMN IF NOT EXISTS language VARCHAR(10);
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS tsv_lang tsvector;

CREATE INDEX IF NOT EXISTS idx_chunks_tsv_lang ON chunks USING gin(tsv_lang);
CREATE INDEX IF NOT EXISTS idx_chunks_language ON chunks(language);
