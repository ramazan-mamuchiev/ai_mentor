-- Speed up GET /api/v1/documents?product_id=... (product document list)
-- Composite index covers WHERE product_id = ? ORDER BY uploaded_at DESC
CREATE INDEX IF NOT EXISTS idx_documents_product_uploaded
    ON documents(product_id, uploaded_at DESC);
