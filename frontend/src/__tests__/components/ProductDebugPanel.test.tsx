import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { ProductDebugPanel } from '../../components/ProductDebugPanel'
import type { ProductDebugInfo } from '../../types'

const mockDebug: ProductDebugInfo = {
  product_id: 1,
  product_name: 'Camera X',
  total_documents: 3,
  firmware_version_count: 2,
  total_file_size_bytes: 102400,
  sum_ingest_duration_ms: 15000.0,
  avg_ingest_duration_ms: 5000.0,
  sum_read_ms: 300.0,
  sum_convert_ms: 5000.0,
  sum_parse_ms: 2400.0,
  sum_embed_ms: 6000.0,
  sum_db_ms: 1300.0,
  total_chunks: 120,
  total_tokens: 25000,
  min_chunk_tokens: 30,
  max_chunk_tokens: 400,
  avg_chunk_tokens: 208.3,
  embedding_model: 'intfloat/multilingual-e5-large',
  total_embedding_tokens: 25000,
  total_rag_hit_count: 45,
  avg_rag_similarity: 0.82,
  last_rag_used_at: '2026-01-15T10:20:30Z',
  documents: [
    { id: 1, title: 'API Guide', format: 'pdf', file_size_bytes: 50000, total_chunks: 60, status: 'ready', indexed_at: '2026-01-15T10:20:30Z' },
    { id: 2, title: 'Proto Spec', format: 'proto', file_size_bytes: 30000, total_chunks: 40, status: 'ready', indexed_at: '2026-01-15T11:00:00Z' },
    { id: 3, title: 'Manual', format: 'pdf', file_size_bytes: 22400, total_chunks: 20, status: 'ready', indexed_at: null },
  ],
}

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('ProductDebugPanel', () => {
  it('shows loading spinner initially', () => {
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise(() => {})))
    render(<ProductDebugPanel productId={1} />)
    expect(document.querySelector('.doc-debug-loading')).toBeInTheDocument()
  })

  it('renders debug info after loading', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(mockDebug),
    }))

    render(<ProductDebugPanel productId={1} />)

    await waitFor(() => {
      expect(document.querySelector('.doc-debug-panel')).toBeInTheDocument()
      expect(document.querySelector('.doc-debug-loading')).not.toBeInTheDocument()
    })

    expect(screen.getByText('Camera X')).toBeInTheDocument()
  })

  it('displays document count', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(mockDebug),
    }))

    render(<ProductDebugPanel productId={1} />)

    await waitFor(() => {
      expect(screen.getByText('3')).toBeInTheDocument()
    })
  })

  it('displays timing bar', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(mockDebug),
    }))

    render(<ProductDebugPanel productId={1} />)

    await waitFor(() => {
      expect(document.querySelector('.doc-debug-timing-bar')).toBeInTheDocument()
    })
  })

  it('documents section is collapsed by default', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(mockDebug),
    }))

    render(<ProductDebugPanel productId={1} />)

    await waitFor(() => {
      expect(screen.getByText('Documents (3)')).toBeInTheDocument()
    })

    expect(screen.queryByText('API Guide')).not.toBeInTheDocument()
    expect(document.querySelector('.doc-debug-docs-table')).not.toBeInTheDocument()
  })

  it('expands documents table on toggle click', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(mockDebug),
    }))

    render(<ProductDebugPanel productId={1} />)

    await waitFor(() => {
      expect(screen.getByText('Documents (3)')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Documents (3)'))

    expect(screen.getByText('API Guide')).toBeInTheDocument()
    expect(screen.getByText('Proto Spec')).toBeInTheDocument()
    expect(screen.getByText('Manual')).toBeInTheDocument()
  })

  it('shows error state on API failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      text: () => Promise.resolve('Internal Server Error'),
    }))

    render(<ProductDebugPanel productId={1} />)

    await waitFor(() => {
      expect(document.querySelector('.doc-debug-error')).toBeInTheDocument()
    })
  })

  it('fetches data for the correct product ID', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(mockDebug),
    }))

    render(<ProductDebugPanel productId={42} />)

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        '/api/v1/products/42/debug',
        expect.anything(),
      )
    })
  })
})
