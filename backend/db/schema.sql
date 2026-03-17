CREATE EXTENSION IF NOT EXISTS vector;

-- Devices (equipment catalog)
CREATE TABLE IF NOT EXISTS devices (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    manufacturer TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(manufacturer, model)
);

-- Firmware versions per device
CREATE TABLE IF NOT EXISTS firmware_versions (
    id SERIAL PRIMARY KEY,
    device_id INT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    version TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(device_id, version)
);

-- Documents (uploaded files metadata)
CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    device_id INT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    firmware_version_id INT NOT NULL REFERENCES firmware_versions(id),
    format TEXT NOT NULL DEFAULT 'markdown',
    source_path TEXT NOT NULL DEFAULT '',
    s3_key TEXT NOT NULL DEFAULT '',
    original_filename TEXT NOT NULL DEFAULT '',
    file_size_bytes BIGINT NOT NULL DEFAULT 0,
    source_hash TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    total_chunks INT NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    error_message TEXT,
    ingested_at TIMESTAMPTZ DEFAULT NOW()
);

-- Chunks (semantic search units with vector embeddings)
CREATE TABLE IF NOT EXISTS chunks (
    id BIGSERIAL PRIMARY KEY,
    document_id INT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INT NOT NULL,
    heading_path TEXT NOT NULL,
    heading_level INT NOT NULL DEFAULT 1,
    content TEXT NOT NULL,
    token_count INT NOT NULL DEFAULT 0,
    embedding vector(1536),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(document_id, chunk_index)
);

-- HNSW vector index (cosine similarity)
CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 128);

CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
