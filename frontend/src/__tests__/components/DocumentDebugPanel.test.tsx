import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { DocumentDebugPanel } from '../../components/DocumentDebugPanel'
import type { DocumentDebugInfo } from '../../types'

const mockDebug: DocumentDebugInfo = {
  document_id: 5,
  title: 'API Guide',
  original_filename: 'api.md',
  format: 'markdown',
  status: 'ready',
  source_hash: 'abc123def456789012345678',
  file_size_bytes: 102400,
  uploaded_at: '2026-01-01T12:30:45Z',
  indexed_at: '2026-01-01T12:35:00Z',
  ingest_duration_ms: 5200.5,
  read_ms: 100.0,
  convert_ms: 0.0,
  parse_ms: 800.0,
  embed_ms: 3500.0,
  db_ms: 800.5,
  total_chunks: 42,
  total_tokens: 8500,
  min_chunk_tokens: 50,
  max_chunk_tokens: 350,
  avg_chunk_tokens: 202.4,
  embedding_model: 'intfloat/multilingual-e5-large',
  embedding_dims: 1024,
  embedding_tokens: 8500,
  rag_hit_count: 15,
  rag_avg_similarity: 0.8234,
  rag_last_used_at: '2026-01-15T10:20:30Z',
  product_name: 'Camera X',
  firmware_version: '2.0',
}

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('DocumentDebugPanel', () => {
  it('shows loading spinner initially', () => {
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise(() => {})))
    render(<DocumentDebugPanel documentId={5} />)
    expect(document.querySelector('.doc-debug-loading')).toBeInTheDocument()
  })

  it('renders debug info after loading', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(mockDebug),
    }))

    render(<DocumentDebugPanel documentId={5} />)

    await waitFor(() => {
      expect(document.querySelector('.debug-panel-box')).toBeInTheDocument()
      expect(document.querySelector('.doc-debug-loading')).not.toBeInTheDocument()
    })

    expect(screen.getByText('markdown')).toBeInTheDocument()
    expect(screen.getByText('ready')).toBeInTheDocument()
    expect(screen.getByText('#5')).toBeInTheDocument()
    expect(screen.getByText('Camera X')).toBeInTheDocument()
    expect(screen.getByText('2.0')).toBeInTheDocument()
  })

  it('displays timing metrics', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(mockDebug),
    }))

    render(<DocumentDebugPanel documentId={5} />)

    await waitFor(() => {
      expect(screen.getByText('5.2s')).toBeInTheDocument()
    })

    expect(screen.getByText('100ms')).toBeInTheDocument()
    expect(screen.getByText('800ms')).toBeInTheDocument()
    expect(screen.getByText('3.5s')).toBeInTheDocument()
  })

  it('displays token statistics', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(mockDebug),
    }))

    render(<DocumentDebugPanel documentId={5} />)

    await waitFor(() => {
      expect(screen.getByText('42')).toBeInTheDocument()
    })
  })

  it('displays embedding model info', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(mockDebug),
    }))

    render(<DocumentDebugPanel documentId={5} />)

    await waitFor(() => {
      expect(screen.getByText('intfloat/multilingual-e5-large')).toBeInTheDocument()
    })
  })

  it('displays RAG usage stats', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(mockDebug),
    }))

    render(<DocumentDebugPanel documentId={5} />)

    await waitFor(() => {
      expect(screen.getByText('15')).toBeInTheDocument()
      expect(screen.getByText('82.3%')).toBeInTheDocument()
    })
  })

  it('shows error state on API failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      text: () => Promise.resolve('Internal Server Error'),
    }))

    render(<DocumentDebugPanel documentId={5} />)

    await waitFor(() => {
      expect(document.querySelector('.doc-debug-error')).toBeInTheDocument()
    })
  })

  it('handles null optional fields gracefully', async () => {
    const minimalDebug: DocumentDebugInfo = {
      ...mockDebug,
      ingest_duration_ms: null,
      read_ms: null,
      convert_ms: null,
      parse_ms: null,
      embed_ms: null,
      db_ms: null,
      min_chunk_tokens: null,
      max_chunk_tokens: null,
      avg_chunk_tokens: null,
      embedding_model: null,
      embedding_dims: null,
      rag_avg_similarity: null,
      rag_last_used_at: null,
    }

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(minimalDebug),
    }))

    render(<DocumentDebugPanel documentId={5} />)

    await waitFor(() => {
      expect(document.querySelector('.debug-panel-box')).toBeInTheDocument()
    })

    const dashes = screen.getAllByText('—')
    expect(dashes.length).toBeGreaterThan(5)
  })

  it('renders timing bar when timing data is present', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(mockDebug),
    }))

    render(<DocumentDebugPanel documentId={5} />)

    await waitFor(() => {
      expect(document.querySelector('.doc-debug-timing-bar')).toBeInTheDocument()
    })

    const segments = document.querySelectorAll('.doc-debug-timing-segment')
    expect(segments.length).toBeGreaterThan(0)
  })

  it('fetches data for the correct document ID', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(mockDebug),
    }))

    render(<DocumentDebugPanel documentId={42} />)

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        '/api/v1/documents/42/debug',
        expect.anything(),
      )
    })
  })
})
