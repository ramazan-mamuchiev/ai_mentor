import { useEffect, useState, useCallback } from 'react'
import { Key, Loader2, Play, RefreshCw, AlertTriangle, CheckCircle, XCircle, ChevronDown, ChevronUp } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { getDocumentDebug, getDocumentUsageStats, getDocumentLifecycle, analyzeDocumentLifecycle } from '../api/documents'
import type { DocumentDebugInfo, DocumentUsageStats } from '../types'
import type { DocumentLifecycle } from '../api/documents'
import { DebugPanelWrapper } from './DebugPanelWrapper'
import { SearchKeysModal } from './SearchKeysModal'
import { SkeletonCodeViewer } from './SkeletonCodeViewer'
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

function fmtRate(value: number | null, unit: string): string {
  if (value == null || !isFinite(value) || value <= 0) return '—'
  if (value >= 1000) return `${(value / 1000).toFixed(1)}K ${unit}`
  return `${value.toFixed(1)} ${unit}`
}

function calcRate(amount: number | null | undefined, ms: number | null | undefined): number | null {
  if (amount == null || ms == null || ms <= 0) return null
  return (amount / ms) * 1000
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

function LifecycleStatusBadge({ status }: { status: string }) {
  const { t } = useTranslation()
  const icon = status === 'ready' ? <CheckCircle size={12} /> :
    status === 'error' ? <XCircle size={12} /> :
    status === 'processing' || status === 'pending' ? <Loader2 size={12} className="spin-icon" /> : null
  return (
    <span className={`lifecycle-status lifecycle-status--${status}`}>
      {icon} {t(`lifecycle.status.${status}`, status)}
    </span>
  )
}

function LifecycleSection({ documentId }: { documentId: number }) {
  const { t } = useTranslation()
  const [lc, setLc] = useState<DocumentLifecycle | null>(null)
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const [skeletonExpanded, setSkeletonExpanded] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    getDocumentLifecycle(documentId)
      .then(setLc)
      .catch(() => setLc(null))
      .finally(() => setLoading(false))
  }, [documentId])

  useEffect(() => { load() }, [load])

  const handleRun = async () => {
    setRunning(true)
    try {
      await analyzeDocumentLifecycle(documentId)
      setTimeout(load, 2000)
    } catch { /* ignore */ }
    finally { setRunning(false) }
  }

  if (loading) return null

  const hasData = lc && lc.status !== 'not_analyzed'
  const phases = lc?.phases ?? []
  const patterns = lc?.unique_patterns ?? []
  const deps = lc?.dependency_chains ?? []
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
          {hasData ? t('lifecycle.rerun') : t('lifecycle.run')}
        </button>
      </div>

      {!hasData && (
        <div className="doc-debug-row">
          <span>{t('lifecycle.notAnalyzed')}</span>
        </div>
      )}

      {hasData && lc && (
        <>
          <div className="doc-debug-row">
            <span>{t('lifecycle.statusLabel')}</span>
            <LifecycleStatusBadge status={lc.status} />
          </div>

          {lc.error_message && (
            <div className="doc-debug-row doc-debug-row--warning">
              <span>{t('lifecycle.error')}</span>
              <code>{lc.error_message}</code>
            </div>
          )}

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
                      {p.inputs.length > 0 && <div className="lifecycle-phase-io">← {p.inputs.join(', ')}</div>}
                      {p.outputs.length > 0 && <div className="lifecycle-phase-io">→ {p.outputs.join(', ')}</div>}
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
                  {p.code_hint && <code className="lifecycle-code-hint">{p.code_hint}</code>}
                </div>
              ))}
            </div>
          )}

          {deps.length > 0 && (
            <div className="lifecycle-subsection">
              <div className="lifecycle-subsection-title">{t('lifecycle.dependencies')} ({deps.length})</div>
              {deps.map((d, i) => (
                <div key={i} className="lifecycle-dep">
                  {d.from_action} → {d.to_action} <span className="lifecycle-dep-data">({d.data_flow})</span>
                </div>
              ))}
            </div>
          )}

          {lc.code_skeleton && lc.product_id && (
            <div className="lifecycle-subsection">
              <button className="lifecycle-toggle" onClick={() => setSkeletonExpanded(!skeletonExpanded)}>
                {skeletonExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                {t('lifecycle.codeSkeleton')}
              </button>
              {skeletonExpanded && (
                <SkeletonCodeViewer
                  productId={lc.product_id}
                  documentId={documentId}
                  pythonSkeleton={lc.code_skeleton}
                />
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
                  {issue.suggestion && <div className="lifecycle-issue-suggestion">→ {issue.suggestion}</div>}
                </div>
              ))}
            </div>
          )}

          <div className="doc-debug-row"><span>{t('lifecycle.analysisTime')}</span><code>{fmtMs(lc.analysis_ms)}</code></div>
          <div className="doc-debug-row"><span>{t('lifecycle.promptTokens')}</span><code>{fmt(lc.prompt_tokens)}</code></div>
          <div className="doc-debug-row"><span>{t('lifecycle.completionTokens')}</span><code>{fmt(lc.completion_tokens)}</code></div>
          {lc.model && <div className="doc-debug-row"><span>{t('lifecycle.model')}</span><code className="doc-debug-embed-model">{lc.model}</code></div>}
          {lc.validation_retries != null && lc.validation_retries > 0 && (
            <div className="doc-debug-row"><span>{t('lifecycle.retries')}</span><code>{lc.validation_retries}</code></div>
          )}
        </>
      )}
    </div>
  )
}

interface ContentProps {
  documentId?: number
  initialDebug?: DocumentDebugInfo
  initialUsage?: DocumentUsageStats | null
}

export function DocumentDebugContent({ documentId, initialDebug, initialUsage }: ContentProps) {
  const { t } = useTranslation()
  const [debug, setDebug] = useState<DocumentDebugInfo | null>(initialDebug ?? null)
  const [usage, setUsage] = useState<DocumentUsageStats | null>(initialUsage ?? null)
  const [loading, setLoading] = useState(!initialDebug)
  const [error, setError] = useState<string | null>(null)
  const [showKeysModal, setShowKeysModal] = useState(false)

  useEffect(() => {
    if (initialDebug || documentId == null) return
    let cancelled = false
    setLoading(true)
    setError(null)
    Promise.all([
      getDocumentDebug(documentId),
      getDocumentUsageStats(documentId).catch(() => null),
    ])
      .then(([d, u]) => { if (!cancelled) { setDebug(d); setUsage(u) } })
      .catch(e => { if (!cancelled) setError(String(e)) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [documentId, initialDebug])

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
    { label: t('docDebug.readTime'), ms: debug.read_ms, color: 'var(--doc-debug-read, #4dabf7)' },
    { label: t('docDebug.convertTime'), ms: debug.convert_ms, color: 'var(--doc-debug-convert, #69db7c)' },
    { label: t('docDebug.ocrTime'), ms: debug.ocr_ms, color: 'var(--doc-debug-ocr, #ff6b6b)' },
    { label: t('docDebug.parseTime'), ms: debug.parse_ms, color: 'var(--doc-debug-parse, #ffd43b)' },
    { label: t('docDebug.extractTime'), ms: debug.extract_ms, color: 'var(--doc-debug-extract, #20c997)' },
    { label: t('docDebug.embedTime'), ms: debug.embed_ms, color: 'var(--doc-debug-embed, #ff922b)' },
    { label: t('docDebug.dbTime'), ms: debug.db_ms, color: 'var(--doc-debug-db, #da77f2)' },
  ]

  return (
    <div className="doc-debug-grid right-panel-doc-debug">
        <div className="doc-debug-section">
          <div className="doc-debug-section-title">{t('docDebug.file')}</div>
          <div className="doc-debug-row"><span>{t('docDebug.format')}</span><code>{debug.format}</code></div>
          <div className="doc-debug-row"><span>{t('docDebug.size')}</span><code>{fmtBytes(debug.file_size_bytes)}</code></div>
          <div className="doc-debug-row"><span>{t('docDebug.hash')}</span><code className="doc-debug-hash">{debug.source_hash.slice(0, 12)}...</code></div>
          <div className="doc-debug-row"><span>{t('docDebug.uploadedAt')}</span><code>{fmtDate(debug.uploaded_at)}</code></div>
          <div className="doc-debug-row"><span>{t('docDebug.indexedAt')}</span><code>{fmtDate(debug.indexed_at)}</code></div>
          <div className="doc-debug-row"><span>{t('docDebug.status')}</span><code>{debug.status}</code></div>
          {debug.detected_language && (
            <div className="doc-debug-row"><span>{t('docDebug.detectedLanguage')}</span><code>{debug.detected_language}</code></div>
          )}
          {debug.error_message && (
            <div className="doc-debug-row doc-debug-row--warning"><span>{t('docDebug.warning')}</span><code title={debug.error_message}>{debug.error_message.length > 80 ? debug.error_message.slice(0, 80) + '…' : debug.error_message}</code></div>
          )}
        </div>

        <div className="doc-debug-section">
          <div className="doc-debug-section-title">{t('docDebug.indexing')}</div>
          <div className="doc-debug-row doc-debug-row-total"><span>{t('docDebug.totalTime')}</span><code>{fmtMs(debug.ingest_duration_ms)}</code></div>
          <div className="doc-debug-row"><span>{t('docDebug.readTime')}</span><code>{fmtMs(debug.read_ms)}</code></div>
          <div className="doc-debug-row"><span>{t('docDebug.convertTime')}</span><code>{fmtMs(debug.convert_ms)}</code></div>
          <div className="doc-debug-row"><span>{t('docDebug.ocrTime')}</span><code>{fmtMs(debug.ocr_ms)}</code></div>
          <div className="doc-debug-row"><span>{t('docDebug.parseTime')}</span><code>{fmtMs(debug.parse_ms)}</code></div>
          <div className="doc-debug-row"><span>{t('docDebug.extractTime')}</span><code>{fmtMs(debug.extract_ms)}</code></div>
          <div className="doc-debug-row"><span>{t('docDebug.embedTime')}</span><code>{fmtMs(debug.embed_ms)}</code></div>
          <div className="doc-debug-row"><span>{t('docDebug.dbTime')}</span><code>{fmtMs(debug.db_ms)}</code></div>
          <TimingBar stages={timingStages} />
        </div>

        {debug.ocr_images_total != null && (
          <div className="doc-debug-section">
            <div className="doc-debug-section-title">{t('docDebug.ocr')}</div>
            <div className="doc-debug-row"><span>{t('docDebug.ocrTotal')}</span><code>{fmt(debug.ocr_images_total)}</code></div>
            <div className="doc-debug-row"><span>{t('docDebug.ocrSuccess')}</span><code>{fmt(debug.ocr_images_success)}</code></div>
            <div className="doc-debug-row"><span>{t('docDebug.ocrEmpty')}</span><code>{fmt(debug.ocr_images_empty)}</code></div>
            <div className="doc-debug-row"><span>{t('docDebug.ocrFailed')}</span><code>{fmt(debug.ocr_images_failed)}</code></div>
            {debug.ocr_model && <div className="doc-debug-row"><span>{t('docDebug.ocrModel')}</span><code className="doc-debug-embed-model">{debug.ocr_model}</code></div>}
            {(debug.ocr_prompt_tokens != null && debug.ocr_prompt_tokens > 0) && (
              <>
                <div className="doc-debug-row"><span>{t('docDebug.ocrPromptTokens')}</span><code>{fmt(debug.ocr_prompt_tokens)}</code></div>
                <div className="doc-debug-row"><span>{t('docDebug.ocrCompletionTokens')}</span><code>{fmt(debug.ocr_completion_tokens)}</code></div>
                <div className="doc-debug-row doc-debug-row-total"><span>{t('docDebug.ocrTotalTokens')}</span><code>{fmt((debug.ocr_prompt_tokens ?? 0) + (debug.ocr_completion_tokens ?? 0))}</code></div>
              </>
            )}
          </div>
        )}

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
          <div className="doc-debug-row"><span>{t('docDebug.embeddingDims')}</span><code>{debug.embedding_dims != null ? fmt(debug.embedding_dims) : '—'}</code></div>
          <div className="doc-debug-row doc-debug-row-total"><span>{t('docDebug.embeddingTokens')}</span><code>{fmt(debug.embedding_tokens)}</code></div>
        </div>

        {debug.extract_ms != null && (
          <div className="doc-debug-section">
            <div className="doc-debug-section-title">{t('docDebug.extraction')}</div>
            <div className="doc-debug-row"><span>{t('docDebug.extractTime')}</span><code>{fmtMs(debug.extract_ms)}</code></div>
            <div className="doc-debug-row"><span>{t('docDebug.extractModel')}</span><code className="doc-debug-embed-model">{debug.extract_model ?? '—'}</code></div>
            <div className="doc-debug-row"><span>{t('docDebug.extractPromptTokens')}</span><code>{fmt(debug.extract_prompt_tokens)}</code></div>
            <div className="doc-debug-row"><span>{t('docDebug.extractCompletionTokens')}</span><code>{fmt(debug.extract_completion_tokens)}</code></div>
            <div className="doc-debug-row doc-debug-row-total"><span>{t('docDebug.extractTotalTokens')}</span><code>{fmt((debug.extract_prompt_tokens ?? 0) + (debug.extract_completion_tokens ?? 0))}</code></div>
          </div>
        )}

        <LifecycleSection documentId={debug.document_id} />

        <div className="doc-debug-section">
          <div className="doc-debug-section-title">{t('searchKeys.sectionTitle')}</div>
          <div className="doc-debug-row"><span>{t('searchKeys.chunkKeys')}</span><code>{fmt(debug.search_keys_count)}</code></div>
          {debug.search_keys_count > 0 && (
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
            mode="document"
            entityId={debug.document_id}
            entityTitle={debug.title}
            onClose={() => setShowKeysModal(false)}
          />
        )}

        <div className="doc-debug-section">
          <div className="doc-debug-section-title">{t('docDebug.performance')}</div>
          <div className="doc-debug-row"><span>{t('docDebug.perfThroughput')}</span><code>{fmtRate(calcRate(debug.file_size_bytes / 1024, debug.ingest_duration_ms), 'KB/s')}</code></div>
          <div className="doc-debug-row"><span>{t('docDebug.perfRead')}</span><code>{fmtRate(calcRate(debug.file_size_bytes / 1024, debug.read_ms), 'KB/s')}</code></div>
          <div className="doc-debug-row"><span>{t('docDebug.perfParse')}</span><code>{fmtRate(calcRate(debug.total_chunks, debug.parse_ms), 'chunks/s')}</code></div>
          <div className="doc-debug-row"><span>{t('docDebug.perfEmbed')}</span><code>{fmtRate(calcRate(debug.embedding_tokens, debug.embed_ms), 'tok/s')}</code></div>
          <div className="doc-debug-row"><span>{t('docDebug.perfDb')}</span><code>{fmtRate(calcRate(debug.total_chunks, debug.db_ms), 'chunks/s')}</code></div>
        </div>

        <div className="doc-debug-section">
          <div className="doc-debug-section-title">{t('docDebug.ragUsage')}</div>
          <div className="doc-debug-row"><span>{t('docDebug.ragHitCount')}</span><code>{fmt(debug.rag_hit_count)}</code></div>
          <div className="doc-debug-row"><span>{t('docDebug.ragAvgSimilarity')}</span><code>{fmtPct(debug.rag_avg_similarity)}</code></div>
          <div className="doc-debug-row"><span>{t('docDebug.ragLastUsed')}</span><code>{fmtDate(debug.rag_last_used_at)}</code></div>
        </div>

        <div className="doc-debug-section">
          <div className="doc-debug-section-title">{t('docDebug.usageAnalytics')}</div>
          {usage && usage.total_usages > 0 ? (
            <>
              <div className="doc-debug-row doc-debug-row-total"><span>{t('docDebug.totalUsages')}</span><code>{fmt(usage.total_usages)}</code></div>
              <div className="doc-debug-row"><span>{t('docDebug.uniqueSessions')}</span><code>{fmt(usage.unique_sessions)}</code></div>
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
              <div className="doc-debug-row"><span>{t('docDebug.firstUsedAt')}</span><code>{fmtDate(usage.first_used_at)}</code></div>
              <div className="doc-debug-row"><span>{t('docDebug.lastUsedAt')}</span><code>{fmtDate(usage.last_used_at)}</code></div>
              {usage.top_headings.length > 0 && (
                <div className="doc-debug-row doc-debug-row-wide">
                  <span>{t('docDebug.topHeadings')}</span>
                  <code className="debug-query-value">{usage.top_headings.map(h => `${h.heading_path} (${h.count})`).join('\n')}</code>
                </div>
              )}
              {usage.recent_usages.length > 0 && (
                <div className="doc-debug-row doc-debug-row-wide">
                  <span>{t('docDebug.recentUsages')}</span>
                  <code className="debug-query-value">
                    {usage.recent_usages.slice(0, 5).map(u =>
                      `${fmtDate(u.created_at)} | S#${u.session_id} | ${u.query_type ?? '—'} | sim=${fmtPct(u.similarity)} | ${u.context_tokens}tok`
                    ).join('\n')}
                  </code>
                </div>
              )}
            </>
          ) : (
            <div className="doc-debug-row"><span>{t('docDebug.noUsageData')}</span><code>—</code></div>
          )}
        </div>

        <div className="doc-debug-section">
          <div className="doc-debug-section-title">{t('docDebug.identifiers')}</div>
          <div className="doc-debug-row"><span>{t('docDebug.documentId')}</span><code>#{debug.document_id}</code></div>
          <div className="doc-debug-row"><span>{t('docDebug.product')}</span><code>{debug.product_name || '—'}</code></div>
          <div className="doc-debug-row"><span>{t('docDebug.firmware')}</span><code>{debug.firmware_version || '—'}</code></div>
        </div>
    </div>
  )
}

interface Props {
  documentId: number
  onCollapse?: () => void
}

export function DocumentDebugPanel({ documentId, onCollapse }: Props) {
  return (
    <DebugPanelWrapper onCollapse={onCollapse}>
      <DocumentDebugContent documentId={documentId} />
    </DebugPanelWrapper>
  )
}
