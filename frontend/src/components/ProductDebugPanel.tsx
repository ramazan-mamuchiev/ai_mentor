import { useEffect, useState } from 'react'
import { ChevronDown, ChevronRight, Loader2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { getProductDebug } from '../api/products'
import type { ProductDebugInfo } from '../types'

function fmt(n: number | undefined | null): string {
  return n != null ? n.toLocaleString() : '—'
}

function fmtMs(ms: number | undefined | null): string {
  if (ms == null) return '—'
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function fmtPct(v: number | undefined | null): string {
  return v != null ? (v * 100).toFixed(1) + '%' : '—'
}

function fmtBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${(bytes / Math.pow(k, i)).toFixed(i > 0 ? 1 : 0)} ${sizes[i]}`
}

function fmtDate(iso: string | null): string {
  if (!iso) return '—'
  try {
    const m = iso.match(/^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})/)
    if (!m) return iso
    return `${m[1]} ${m[2]}`
  } catch {
    return iso
  }
}

function TimingBar({ stages }: { stages: { label: string; ms: number | null; color: string }[] }) {
  const values = stages.map(s => s.ms ?? 0)
  const total = values.reduce((a, b) => a + b, 0)
  if (total === 0) return null

  const MIN_PCT = 3
  return (
    <div className="doc-debug-timing-bar">
      {stages.map((s, i) => {
        const rawPct = total > 0 ? ((s.ms ?? 0) / total) * 100 : 0
        const pct = Math.max(MIN_PCT, rawPct)
        return (
          <div
            key={i}
            className="doc-debug-timing-segment"
            style={{ width: `${pct}%`, background: s.color, opacity: rawPct < 1 ? 0.45 : 1 }}
            title={`${s.label}: ${fmtMs(s.ms)} (${rawPct.toFixed(1)}%)`}
          />
        )
      })}
    </div>
  )
}

interface Props {
  productId: number
}

export function ProductDebugPanel({ productId }: Props) {
  const { t } = useTranslation()
  const [debug, setDebug] = useState<ProductDebugInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [docsExpanded, setDocsExpanded] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getProductDebug(productId)
      .then(data => { if (!cancelled) setDebug(data) })
      .catch(e => { if (!cancelled) setError(String(e)) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [productId])

  if (loading) {
    return (
      <div className="doc-debug-panel doc-debug-loading">
        <Loader2 size={16} className="spin-icon" />
      </div>
    )
  }

  if (error || !debug) {
    return (
      <div className="doc-debug-panel doc-debug-error">
        {error || 'Failed to load debug info'}
      </div>
    )
  }

  const timingStages = [
    { label: t('docDebug.readTime'), ms: debug.sum_read_ms, color: 'var(--doc-debug-read, #4dabf7)' },
    { label: t('docDebug.convertTime'), ms: debug.sum_convert_ms, color: 'var(--doc-debug-convert, #69db7c)' },
    { label: t('docDebug.parseTime'), ms: debug.sum_parse_ms, color: 'var(--doc-debug-parse, #ffd43b)' },
    { label: t('docDebug.embedTime'), ms: debug.sum_embed_ms, color: 'var(--doc-debug-embed, #ff922b)' },
    { label: t('docDebug.dbTime'), ms: debug.sum_db_ms, color: 'var(--doc-debug-db, #da77f2)' },
  ]

  return (
    <div className="doc-debug-panel">
      <div className="doc-debug-grid">
        <div className="doc-debug-section">
          <div className="doc-debug-section-title">Product Summary</div>
          <div className="doc-debug-row"><span>Product</span><code>{debug.product_name}</code></div>
          <div className="doc-debug-row"><span>Documents</span><code>{fmt(debug.total_documents)}</code></div>
          <div className="doc-debug-row"><span>Firmware versions</span><code>{fmt(debug.firmware_version_count)}</code></div>
          <div className="doc-debug-row"><span>Total size</span><code>{fmtBytes(debug.total_file_size_bytes)}</code></div>
        </div>

        <div className="doc-debug-section">
          <div className="doc-debug-section-title">{t('docDebug.indexing')}</div>
          <div className="doc-debug-row doc-debug-row-total"><span>Total time (sum)</span><code>{fmtMs(debug.sum_ingest_duration_ms)}</code></div>
          <div className="doc-debug-row"><span>Avg per document</span><code>{fmtMs(debug.avg_ingest_duration_ms)}</code></div>
          <div className="doc-debug-row"><span>{t('docDebug.readTime')}</span><code>{fmtMs(debug.sum_read_ms)}</code></div>
          <div className="doc-debug-row"><span>{t('docDebug.convertTime')}</span><code>{fmtMs(debug.sum_convert_ms)}</code></div>
          <div className="doc-debug-row"><span>{t('docDebug.parseTime')}</span><code>{fmtMs(debug.sum_parse_ms)}</code></div>
          <div className="doc-debug-row"><span>{t('docDebug.embedTime')}</span><code>{fmtMs(debug.sum_embed_ms)}</code></div>
          <div className="doc-debug-row"><span>{t('docDebug.dbTime')}</span><code>{fmtMs(debug.sum_db_ms)}</code></div>
          <TimingBar stages={timingStages} />
        </div>

        <div className="doc-debug-section">
          <div className="doc-debug-section-title">{t('docDebug.chunks')}</div>
          <div className="doc-debug-row"><span>{t('docDebug.totalChunks')}</span><code>{fmt(debug.total_chunks)}</code></div>
          <div className="doc-debug-row doc-debug-row-total"><span>{t('docDebug.totalTokens')}</span><code>{fmt(debug.total_tokens)}</code></div>
          <div className="doc-debug-row"><span>{t('docDebug.minTokens')}</span><code>{fmt(debug.min_chunk_tokens)}</code></div>
          <div className="doc-debug-row"><span>{t('docDebug.maxTokens')}</span><code>{fmt(debug.max_chunk_tokens)}</code></div>
          <div className="doc-debug-row"><span>{t('docDebug.avgTokens')}</span><code>{debug.avg_chunk_tokens != null ? debug.avg_chunk_tokens.toFixed(1) : '—'}</code></div>
        </div>

        <div className="doc-debug-section">
          <div className="doc-debug-section-title">{t('docDebug.embedding')}</div>
          <div className="doc-debug-row"><span>{t('docDebug.embeddingModel')}</span><code className="doc-debug-embed-model">{debug.embedding_model ?? '—'}</code></div>
          <div className="doc-debug-row doc-debug-row-total"><span>{t('docDebug.embeddingTokens')}</span><code>{fmt(debug.total_embedding_tokens)}</code></div>
        </div>

        <div className="doc-debug-section">
          <div className="doc-debug-section-title">{t('docDebug.ragUsage')}</div>
          <div className="doc-debug-row"><span>{t('docDebug.ragHitCount')}</span><code>{fmt(debug.total_rag_hit_count)}</code></div>
          <div className="doc-debug-row"><span>{t('docDebug.ragAvgSimilarity')}</span><code>{fmtPct(debug.avg_rag_similarity)}</code></div>
          <div className="doc-debug-row"><span>{t('docDebug.ragLastUsed')}</span><code>{fmtDate(debug.last_rag_used_at)}</code></div>
        </div>

        {debug.documents.length > 0 && (
          <div className="doc-debug-section doc-debug-section--wide">
            <button
              className="doc-debug-section-toggle"
              onClick={() => setDocsExpanded(v => !v)}
            >
              {docsExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              <span className="doc-debug-section-title">Documents ({debug.documents.length})</span>
            </button>
            {docsExpanded && (
              <table className="doc-debug-docs-table">
                <thead>
                  <tr>
                    <th>Title</th>
                    <th>Format</th>
                    <th>Size</th>
                    <th>Chunks</th>
                    <th>Status</th>
                    <th>{t('docs.table.indexed')}</th>
                  </tr>
                </thead>
                <tbody>
                  {debug.documents.map(doc => (
                    <tr key={doc.id}>
                      <td>{doc.title}</td>
                      <td><span className="docs-format">{doc.format}</span></td>
                      <td>{fmtBytes(doc.file_size_bytes)}</td>
                      <td>{fmt(doc.total_chunks)}</td>
                      <td><span className={`docs-status docs-status--${doc.status}`}>{doc.status}</span></td>
                      <td>{fmtDate(doc.indexed_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
