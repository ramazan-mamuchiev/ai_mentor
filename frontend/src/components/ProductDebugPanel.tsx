import { useEffect, useMemo, useState, useCallback } from 'react'
import { Key, Loader2, Play, RefreshCw, AlertTriangle, CheckCircle, XCircle, ChevronDown, ChevronUp } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { getProductDebug, getProductUsageStats, getProductLifecycle, analyzeProductLifecycle } from '../api/products'
import type { ProductDebugInfo, ProductUsageStats } from '../types'
import type { ProductLifecycle } from '../api/products'
import { DebugPanelWrapper } from './DebugPanelWrapper'
import { SearchKeysModal } from './SearchKeysModal'
import { fmtUsd } from '../utils/format'

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

function ProductLifecycleSection({ productId }: { productId: number }) {
  const { t } = useTranslation()
  const [lc, setLc] = useState<ProductLifecycle | null>(null)
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const [skeletonExpanded, setSkeletonExpanded] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    getProductLifecycle(productId)
      .then(setLc)
      .catch(() => setLc(null))
      .finally(() => setLoading(false))
  }, [productId])

  useEffect(() => { load() }, [load])

  const handleRun = async () => {
    setRunning(true)
    try {
      await analyzeProductLifecycle(productId)
      setTimeout(load, 5000)
    } catch { /* ignore */ }
    finally { setRunning(false) }
  }

  if (loading) return null

  const merged = lc?.merged
  const hasData = merged && merged.status === 'ready'
  const phases = merged?.phases ?? []
  const patterns = merged?.unique_patterns ?? []
  const deps = merged?.dependency_chains ?? []
  const docLcs = lc?.document_lifecycles ?? []
  const issues = lc?.doc_issues ?? []

  return (
    <div className="doc-debug-section lifecycle-section">
      <div className="doc-debug-section-title lifecycle-section-header">
        <span>{t('lifecycle.title')}</span>
        <button
          className="lifecycle-run-btn"
          onClick={handleRun}
          disabled={running}
          title={hasData ? t('lifecycle.rerun') : t('lifecycle.run')}
        >
          {running ? <Loader2 size={12} className="spin-icon" /> :
           hasData ? <RefreshCw size={12} /> : <Play size={12} />}
          {hasData ? t('lifecycle.rerunAll') : t('lifecycle.runAll')}
        </button>
      </div>

      {docLcs.length > 0 && (
        <div className="doc-debug-row">
          <span>{t('lifecycle.docAnalyses')}</span>
          <code>{docLcs.filter(d => d.status === 'ready').length} / {docLcs.length}</code>
        </div>
      )}

      {!hasData && !merged && (
        <div className="doc-debug-row">
          <span>{t('lifecycle.notAnalyzed')}</span>
        </div>
      )}

      {merged && merged.status === 'error' && (
        <div className="doc-debug-row doc-debug-row--warning">
          <span>{t('lifecycle.error')}</span>
          <code>{t('lifecycle.mergeFailed')}</code>
        </div>
      )}

      {hasData && merged && (
        <>
          <div className="doc-debug-row">
            <span>{t('lifecycle.statusLabel')}</span>
            <span className="lifecycle-status lifecycle-status--ready">
              <CheckCircle size={12} /> {t('lifecycle.status.ready')}
            </span>
          </div>

          {phases.length > 0 && (
            <div className="lifecycle-subsection">
              <button className="lifecycle-toggle" onClick={() => setExpanded(!expanded)}>
                {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                {t('lifecycle.phases')} ({phases.length})
              </button>
              {expanded && (
                <div className="lifecycle-phases">
                  {[...phases].sort((a, b) => a.step_order - b.step_order).map((p, i) => (
                    <div key={i} className={`lifecycle-phase lifecycle-phase--${p.phase_name}`}>
                      <div className="lifecycle-phase-header">
                        <span className="lifecycle-phase-order">{p.step_order}</span>
                        <span className="lifecycle-phase-action">{p.action}</span>
                        {p.is_required && <span className="lifecycle-phase-required">REQ</span>}
                      </div>
                      {p.api_call && <code className="lifecycle-phase-api">{p.api_call}</code>}
                      {p.notes && <div className="lifecycle-phase-notes">{p.notes}</div>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {patterns.length > 0 && (
            <div className="lifecycle-subsection">
              <div className="lifecycle-subsection-title">{t('lifecycle.patterns')} ({patterns.length})</div>
              {patterns.map((p, i) => (
                <div key={i} className="lifecycle-pattern">
                  <strong>{p.pattern}</strong>: {p.description}
                </div>
              ))}
            </div>
          )}

          {deps.length > 0 && (
            <div className="lifecycle-subsection">
              <div className="lifecycle-subsection-title">{t('lifecycle.dependencies')} ({deps.length})</div>
              {deps.map((d, i) => (
                <div key={i} className="lifecycle-dep">
                  {d.from_action} → {d.to_action}
                </div>
              ))}
            </div>
          )}

          {merged.code_skeleton && (
            <div className="lifecycle-subsection">
              <button className="lifecycle-toggle" onClick={() => setSkeletonExpanded(!skeletonExpanded)}>
                {skeletonExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                {t('lifecycle.codeSkeleton')}
              </button>
              {skeletonExpanded && (
                <pre className="lifecycle-code-skeleton">{merged.code_skeleton}</pre>
              )}
            </div>
          )}

          {issues.length > 0 && (
            <div className="lifecycle-subsection">
              <div className="lifecycle-subsection-title lifecycle-issues-title">
                <AlertTriangle size={14} /> {t('lifecycle.docIssues')} ({issues.length})
              </div>
              {issues.map((issue, i) => (
                <div key={i} className={`lifecycle-issue lifecycle-issue--${issue.severity}`}>
                  <span className="lifecycle-issue-type">{issue.issue_type}</span>
                  <span>{issue.description}</span>
                </div>
              ))}
            </div>
          )}

          <div className="doc-debug-row"><span>{t('lifecycle.analysisTime')}</span><code>{fmtMs(merged.analysis_ms)}</code></div>
          <div className="doc-debug-row"><span>{t('lifecycle.promptTokens')}</span><code>{fmt(merged.prompt_tokens)}</code></div>
          <div className="doc-debug-row"><span>{t('lifecycle.completionTokens')}</span><code>{fmt(merged.completion_tokens)}</code></div>
          {merged.model && <div className="doc-debug-row"><span>{t('lifecycle.model')}</span><code className="doc-debug-embed-model">{merged.model}</code></div>}
        </>
      )}
    </div>
  )
}

interface ContentProps {
  productId?: number
  initialDebug?: ProductDebugInfo
  initialUsage?: ProductUsageStats | null
}

export function ProductDebugContent({ productId, initialDebug, initialUsage }: ContentProps) {
  const { t } = useTranslation()
  const [debug, setDebug] = useState<ProductDebugInfo | null>(initialDebug ?? null)
  const [usage, setUsage] = useState<ProductUsageStats | null>(initialUsage ?? null)
  const [loading, setLoading] = useState(!initialDebug)
  const [error, setError] = useState<string | null>(null)
  const [showKeysModal, setShowKeysModal] = useState(false)

  useEffect(() => {
    if (initialDebug || productId == null) return
    let cancelled = false
    setLoading(true)
    setError(null)
    Promise.all([
      getProductDebug(productId),
      getProductUsageStats(productId).catch(() => null),
    ])
      .then(([d, u]) => { if (!cancelled) { setDebug(d); setUsage(u) } })
      .catch(e => { if (!cancelled) setError(String(e)) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [productId, initialDebug])

  const docsSummary = useMemo(() => {
    if (!debug?.documents.length) return null
    const docs = debug.documents
    const byStatus = new Map<string, number>()
    const byFormat = new Map<string, number>()
    let totalSize = 0
    let totalChunks = 0
    let lastIndexed: string | null = null

    for (const d of docs) {
      byStatus.set(d.status, (byStatus.get(d.status) ?? 0) + 1)
      byFormat.set(d.format, (byFormat.get(d.format) ?? 0) + 1)
      totalSize += d.file_size_bytes
      totalChunks += d.total_chunks
      if (d.indexed_at && (!lastIndexed || d.indexed_at > lastIndexed)) {
        lastIndexed = d.indexed_at
      }
    }

    return {
      count: docs.length,
      byStatus: [...byStatus.entries()].sort((a, b) => b[1] - a[1]),
      byFormat: [...byFormat.entries()].sort((a, b) => b[1] - a[1]),
      totalSize,
      totalChunks,
      avgSize: totalSize / docs.length,
      avgChunks: totalChunks / docs.length,
      lastIndexed,
    }
  }, [debug?.documents])

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
          <div className="doc-debug-section-title">{t('searchKeys.sectionTitle')}</div>
          <div className="doc-debug-row"><span>{t('searchKeys.totalKeys')}</span><code>{fmt(debug.search_keys_total)}</code></div>
          <div className="doc-debug-row"><span>{t('searchKeys.llmKeys')}</span><code>{fmt(debug.search_keys_llm)}</code></div>
          <div className="doc-debug-row"><span>{t('searchKeys.chunkKeys')}</span><code>{fmt(debug.search_keys_chunk)}</code></div>
          {debug.search_keys_total > 0 && (
            <div className="doc-debug-row">
              <button className="sk-view-btn" onClick={() => setShowKeysModal(true)}>
                <Key size={12} />
                {t('searchKeys.viewKeys')}
              </button>
            </div>
          )}
        </div>

        {showKeysModal && (
          <SearchKeysModal
            mode="product"
            entityId={debug.product_id}
            entityTitle={debug.product_name}
            onClose={() => setShowKeysModal(false)}
          />
        )}

        <div className="doc-debug-section">
          <div className="doc-debug-section-title">{t('docDebug.ragUsage')}</div>
          <div className="doc-debug-row"><span>{t('docDebug.ragHitCount')}</span><code>{fmt(debug.total_rag_hit_count)}</code></div>
          <div className="doc-debug-row"><span>{t('docDebug.ragAvgSimilarity')}</span><code>{fmtPct(debug.avg_rag_similarity)}</code></div>
          <div className="doc-debug-row"><span>{t('docDebug.ragLastUsed')}</span><code>{debug.last_rag_used_at ? new Date(debug.last_rag_used_at).toLocaleString() : '—'}</code></div>
        </div>

        <div className="doc-debug-section">
          <div className="doc-debug-section-title">{t('docDebug.usageAnalytics')}</div>
          {usage && usage.total_usages > 0 ? (
            <>
              <div className="doc-debug-row doc-debug-row-total"><span>{t('docDebug.totalUsages')}</span><code>{fmt(usage.total_usages)}</code></div>
              <div className="doc-debug-row"><span>{t('docDebug.uniqueSessions')}</span><code>{fmt(usage.unique_sessions)}</code></div>
              <div className="doc-debug-row"><span>{t('docDebug.uniqueDocuments')}</span><code>{fmt(usage.unique_documents)}</code></div>
              {(usage.thumbs_up > 0 || usage.thumbs_down > 0) && (
                <>
                  <div className="doc-debug-row"><span>{t('docDebug.thumbsUp')}</span><code>{fmt(usage.thumbs_up)}</code></div>
                  <div className="doc-debug-row"><span>{t('docDebug.thumbsDown')}</span><code>{fmt(usage.thumbs_down)}</code></div>
                  <div className="doc-debug-row"><span>{t('docDebug.totalRated')}</span><code>{fmt(usage.total_rated)}</code></div>
                </>
              )}
              <div className="doc-debug-row"><span>{t('docDebug.totalContextTokens')}</span><code>{fmt(usage.total_context_tokens)}</code></div>
              <div className="doc-debug-row"><span>{t('docDebug.totalChargeUsd')}</span><code>{fmtUsd(usage.total_charge_usd)}</code></div>
              <div className="doc-debug-row"><span>{t('docDebug.avgSimilarity')}</span><code>{fmtPct(usage.avg_similarity)}</code></div>
              <div className="doc-debug-row"><span>{t('docDebug.firstUsedAt')}</span><code>{usage.first_used_at ? new Date(usage.first_used_at).toLocaleString() : '—'}</code></div>
              <div className="doc-debug-row"><span>{t('docDebug.lastUsedAt')}</span><code>{usage.last_used_at ? new Date(usage.last_used_at).toLocaleString() : '—'}</code></div>
              {usage.documents.length > 0 && (
                <div className="doc-debug-row doc-debug-row-wide">
                  <span>Top documents</span>
                  <code className="debug-query-value">
                    {usage.documents.slice(0, 10).map(d =>
                      `#${d.document_id} ${d.title} — ${d.total_usages} uses, ${fmt(d.total_context_tokens)} tok${d.thumbs_up || d.thumbs_down ? `, +${d.thumbs_up} / -${d.thumbs_down}` : ''}`
                    ).join('\n')}
                  </code>
                </div>
              )}
            </>
          ) : (
            <div className="doc-debug-row"><span>{t('docDebug.noUsageData')}</span><code>—</code></div>
          )}
        </div>

        <ProductLifecycleSection productId={debug.product_id} />

        {docsSummary && (
          <div className="doc-debug-section">
            <div className="doc-debug-section-title">{t('docDebug.documentsSummary')}</div>
            <div className="doc-debug-row doc-debug-row-total"><span>{t('docDebug.totalDocs')}</span><code>{fmt(docsSummary.count)}</code></div>
            <div className="doc-debug-row"><span>{t('docDebug.totalSize')}</span><code>{fmtBytes(docsSummary.totalSize)}</code></div>
            <div className="doc-debug-row"><span>{t('docDebug.avgSize')}</span><code>{fmtBytes(docsSummary.avgSize)}</code></div>
            <div className="doc-debug-row"><span>{t('docDebug.avgChunksPerDoc')}</span><code>{docsSummary.avgChunks.toFixed(1)}</code></div>
            <div className="doc-debug-row"><span>{t('docDebug.lastIndexedAt')}</span><code>{docsSummary.lastIndexed ? new Date(docsSummary.lastIndexed).toLocaleString() : '—'}</code></div>
            {docsSummary.byFormat.length > 0 && (
              <div className="doc-debug-row"><span>{t('docDebug.formats')}</span><code>{docsSummary.byFormat.map(([f, c]) => `${f} (${c})`).join(', ')}</code></div>
            )}
            {docsSummary.byStatus.length > 0 && (
              <div className="doc-debug-row"><span>{t('docDebug.statuses')}</span><code>{docsSummary.byStatus.map(([s, c]) => `${s} (${c})`).join(', ')}</code></div>
            )}
          </div>
        )}
    </div>
  )
}

interface Props {
  productId: number
  onCollapse?: () => void
}

export function ProductDebugPanel({ productId, onCollapse }: Props) {
  return (
    <DebugPanelWrapper onCollapse={onCollapse}>
      <ProductDebugContent productId={productId} />
    </DebugPanelWrapper>
  )
}
