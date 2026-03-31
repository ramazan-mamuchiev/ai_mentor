-- Add YAML front matter metadata columns to chunks
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS layer TEXT;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS topic TEXT;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS doc_number TEXT;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS related_docs JSONB;

CREATE INDEX IF NOT EXISTS idx_chunks_layer ON chunks(layer);
