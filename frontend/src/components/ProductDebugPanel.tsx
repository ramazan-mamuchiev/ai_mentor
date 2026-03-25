import { useEffect, useMemo, useState } from 'react'
import { ArrowUp, ArrowDown, ArrowUpDown, ChevronDown, ChevronRight, Loader2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { getProductDebug } from '../api/products'
import type { ProductDebugInfo } from '../types'
import { DebugPanelWrapper } from './DebugPanelWrapper'

type SortKey = 'title' | 'format' | 'file_size_bytes' | 'total_chunks' | 'status' | 'indexed_at'
type SortDir = 'asc' | 'desc'

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

function formatDateTime(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  const date = d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
  const time = d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  return `${date}\n${time}`
}

function TimingBar({ stages }: { stages: { label: string; ms: number | null; color: string }[] }) {
  const values = stages.map(s => s.ms ?? 0)
  const total = values.reduce((a, b) => a + b, 0)
  if (total === 0) return null

  const MIN_PCT = 3
  return (
    <div className="doc-debug-timing-bar">
      {stages.map((s, i) => {
        const ms = s.ms ?? 0
        const rawPct = total > 0 ? (ms / total) * 100 : 0
        const isZero = ms === 0
        return (
          <div
            key={i}
            className="doc-debug-timing-segment"
            style={{
              width: isZero ? '2px' : `${Math.max(MIN_PCT, rawPct)}%`,
              flexShrink: isZero ? 0 : undefined,
              background: s.color,
              opacity: isZero ? 0.45 : rawPct < 1 ? 0.45 : 1,
            }}
            title={`${s.label}: ${fmtMs(s.ms)} (${rawPct.toFixed(1)}%)`}
          />
        )
      })}
    </div>
  )
}

function DocSortIcon({ active, dir }: { active: boolean; dir: SortDir }) {
  if (!active) return <ArrowUpDown size={12} className="docs-sort-icon" />
  if (dir === 'asc') return <ArrowUp size={12} className="docs-sort-icon docs-sort-icon--active" />
  return <ArrowDown size={12} className="docs-sort-icon docs-sort-icon--active" />
}

function DocsSortableTable({
  documents,
  sortKey,
  sortDir,
  onSort,
}: {
  documents: ProductDebugInfo['documents']
  sortKey: SortKey | null
  sortDir: SortDir
  onSort: (key: SortKey) => void
}) {
  const { t } = useTranslation()

  const sorted = useMemo(() => {
    if (!sortKey) return documents
    const list = [...documents]
    const dir = sortDir === 'asc' ? 1 : -1
    list.sort((a, b) => {
      const av = a[sortKey]
      const bv = b[sortKey]
      if (av == null && bv == null) return 0
      if (av == null) return 1
      if (bv == null) return -1
      if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * dir
      return String(av).localeCompare(String(bv)) * dir
    })
    return list
  }, [documents, sortKey, sortDir])

  const cols: { key: SortKey; label: string }[] = [
    { key: 'title', label: 'Title' },
    { key: 'format', label: 'Format' },
    { key: 'file_size_bytes', label: 'Size' },
    { key: 'total_chunks', label: 'Chunks' },
    { key: 'status', label: 'Status' },
    { key: 'indexed_at', label: t('docs.table.indexed') },
  ]

  return (
    <table className="doc-debug-docs-table">
      <thead>
        <tr>
          {cols.map(col => (
            <th
              key={col.key}
              className="doc-debug-th--sortable"
              onClick={() => onSort(col.key)}
            >
              <span className="doc-debug-th-label">
                {col.label}
                <DocSortIcon active={sortKey === col.key} dir={sortDir} />
              </span>
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {sorted.map(doc => (
          <tr key={doc.id}>
            <td>{doc.title}</td>
            <td><span className="docs-format">{doc.format}</span></td>
            <td>{fmtBytes(doc.file_size_bytes)}</td>
            <td>{fmt(doc.total_chunks)}</td>
            <td><span className={`docs-status docs-status--${doc.status}`}>{doc.status}</span></td>
            <td><span className="docs-date docs-date--twoline">{formatDateTime(doc.indexed_at)}</span></td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

interface ContentProps {
  manufacturerSlug: string
  productSlug: string
}

export function ProductDebugContent({ manufacturerSlug, productSlug }: ContentProps) {
  const { t } = useTranslation()
  const [debug, setDebug] = useState<ProductDebugInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [docsExpanded, setDocsExpanded] = useState(false)
  const [sortKey, setSortKey] = useState<SortKey | null>(null)
  const [sortDir, setSortDir] = useState<SortDir>('asc')

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getProductDebug(manufacturerSlug, productSlug)
      .then(data => { if (!cancelled) setDebug(data) })
      .catch(e => { if (!cancelled) setError(String(e)) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [manufacturerSlug, productSlug])

  if (loading) {
    return (
      <div className="doc-debug-loading">
        <Loader2 size={16} className="spin-icon" />
      </div>
    )
  }

  if (error || !debug) {
    return (
      <div className="doc-debug-error">
        {error || 'Failed to load debug info'}
      </div>
    )
  }

  const timingStages = [
    { label: t('docDebug.readTime'), ms: debug.sum_read_ms, color: 'var(--doc-debug-read, #4dabf7)' },
    { label: t('docDebug.convertTime'), ms: debug.sum_convert_ms, color: 'var(--doc-debug-convert, #69db7c)' },
    { label: t('docDebug.parseTime'), ms: debug.sum_parse_ms, color: 'var(--doc-debug-parse, #ffd43b)' },
    { label: t('docDebug.extractTime'), ms: debug.sum_extract_ms, color: 'var(--doc-debug-extract, #20c997)' },
    { label: t('docDebug.embedTime'), ms: debug.sum_embed_ms, color: 'var(--doc-debug-embed, #ff922b)' },
    { label: t('docDebug.dbTime'), ms: debug.sum_db_ms, color: 'var(--doc-debug-db, #da77f2)' },
  ]

  return (
    <div className="doc-debug-grid right-panel-doc-debug">
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
          <div className="doc-debug-row"><span>{t('docDebug.extractTime')}</span><code>{fmtMs(debug.sum_extract_ms)}</code></div>
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
          <div className="doc-debug-row"><span>{t('docDebug.extractTotalTokens')}</span><code>{fmt(debug.total_extract_tokens)}</code></div>
        </div>

        <div className="doc-debug-section">
          <div className="doc-debug-section-title">{t('docDebug.ragUsage')}</div>
          <div className="doc-debug-row"><span>{t('docDebug.ragHitCount')}</span><code>{fmt(debug.total_rag_hit_count)}</code></div>
          <div className="doc-debug-row"><span>{t('docDebug.ragAvgSimilarity')}</span><code>{fmtPct(debug.avg_rag_similarity)}</code></div>
          <div className="doc-debug-row"><span>{t('docDebug.ragLastUsed')}</span><code>{debug.last_rag_used_at ? new Date(debug.last_rag_used_at).toLocaleString() : '—'}</code></div>
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
              <DocsSortableTable
                documents={debug.documents}
                sortKey={sortKey}
                sortDir={sortDir}
                onSort={(key) => {
                  if (sortKey === key) {
                    setSortDir(prev => prev === 'asc' ? 'desc' : 'asc')
                  } else {
                    setSortKey(key)
                    setSortDir('asc')
                  }
                }}
              />
            )}
          </div>
        )}
    </div>
  )
}

interface Props {
  manufacturerSlug: string
  productSlug: string
  onCollapse?: () => void
}

export function ProductDebugPanel({ manufacturerSlug, productSlug, onCollapse }: Props) {
  return (
    <DebugPanelWrapper onCollapse={onCollapse}>
      <ProductDebugContent manufacturerSlug={manufacturerSlug} productSlug={productSlug} />
    </DebugPanelWrapper>
  )
}
