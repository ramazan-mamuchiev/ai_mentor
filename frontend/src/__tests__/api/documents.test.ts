import { describe, it, expect, vi, beforeEach } from 'vitest'
import { getDocumentDebug } from '../../api/documents'

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('getDocumentDebug', () => {
  it('calls correct API endpoint and returns data', async () => {
    const debugData = {
      document_id: 5,
      title: 'API Guide',
      original_filename: 'api.md',
      format: 'markdown',
      status: 'ready',
      source_hash: 'abc123',
      file_size_bytes: 50000,
      ingested_at: '2026-01-01T00:00:00Z',
      ingest_duration_ms: 3000,
      read_ms: 50,
      convert_ms: 0,
      parse_ms: 500,
      embed_ms: 2000,
      db_ms: 450,
      total_chunks: 20,
      total_tokens: 4000,
      min_chunk_tokens: 80,
      max_chunk_tokens: 300,
      avg_chunk_tokens: 200,
      embedding_model: 'intfloat/multilingual-e5-large',
      embedding_dims: 1024,
      embedding_tokens: 4000,
      rag_hit_count: 10,
      rag_avg_similarity: 0.85,
      rag_last_used_at: '2026-01-15T12:00:00Z',
      product_name: 'Camera',
      firmware_version: '1.0',
    }

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(debugData),
    }))

    const result = await getDocumentDebug(5)

    expect(result).toEqual(debugData)
    expect(fetch).toHaveBeenCalledWith(
      '/api/v1/documents/5/debug',
      expect.objectContaining({
        headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
      }),
    )
  })

  it('throws on 404', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      text: () => Promise.resolve('Document not found'),
    }))

    await expect(getDocumentDebug(999)).rejects.toThrow('API error 404')
  })
})
