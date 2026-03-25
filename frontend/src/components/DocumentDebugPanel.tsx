import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { getDocumentDebug } from '../api/documents'
import type { DocumentDebugInfo } from '../types'
import { DebugPanelWrapper } from './DebugPanelWrapper'

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

interface ContentProps {
  documentId: number
}

export function DocumentDebugContent({ documentId }: ContentProps) {
  const { t } = useTranslation()
  const [debug, setDebug] = useState<DocumentDebugInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getDocumentDebug(documentId)
      .then(data => { if (!cancelled) setDebug(data) })
      .catch(e => { if (!cancelled) setError(String(e)) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [documentId])

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
