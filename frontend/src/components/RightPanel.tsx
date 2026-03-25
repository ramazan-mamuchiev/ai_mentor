import { useCallback, useEffect, useRef, useState } from 'react'
import { Bug, FileSearch, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { DebugInfo, SourceInfo } from '../types'
import { SourceCard } from './SourceCard'
import { MarkdownPreviewModal } from './MarkdownPreviewModal'

const MOBILE_BP = 768
const RATIO_KEY = 'ipcodex-right-panel-ratio'
const DEFAULT_RATIO = 0.3
const MIN_RATIO = 0.15
const MAX_RATIO = 0.55

function loadRatio(): number {
  try {
    const v = localStorage.getItem(RATIO_KEY)
    if (v) {
      const n = parseFloat(v)
      if (!isNaN(n) && n >= MIN_RATIO && n <= MAX_RATIO) return n
    }
  } catch { /* ignore */ }
  return DEFAULT_RATIO
}

function useIsMobile() {
  const [mobile, setMobile] = useState(
    () => typeof window !== 'undefined' && window.innerWidth < MOBILE_BP,
  )
  useEffect(() => {
    const mq = window.matchMedia(`(max-width: ${MOBILE_BP - 1}px)`)
    const handler = (e: MediaQueryListEvent) => setMobile(e.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])
  return mobile
}

function fmt(n: number | undefined | null): string {
  return n != null ? n.toLocaleString() : '—'
}

function fmtSec(ms: number | undefined | null): string {
  return ms != null ? (ms / 1000).toFixed(1) + 's' : '—'
}

function fmtPct(v: number | undefined | null): string {
  return v != null ? (v * 100).toFixed(1) + '%' : '—'
}

interface SourcesContent {
  mode: 'sources'
  sources: SourceInfo[]
}

interface DebugContent {
  mode: 'debug'
  debug: DebugInfo
}

type PanelContent = SourcesContent | DebugContent

interface Props {
  content: PanelContent
  sessionId?: number
  messageId?: number
  onClose: () => void
}

function DebugPanelContent({ debug }: { debug: DebugInfo }) {
  const { t } = useTranslation()
  const promptTotal = (debug.query_tokens ?? 0) + (debug.context_tokens ?? 0)
    + (debug.history_tokens ?? 0) + (debug.system_prompt_tokens ?? 0)
  const hasTiming = debug.total_ms != null || debug.rag_ms != null
  const hasLlm = debug.model != null
  const hasRag = debug.chunks_found != null
  const hasContext = debug.product_filter != null || debug.search_query != null || debug.chunks_found != null

  return (
    <div className="debug-grid right-panel-debug">
      <div className="debug-section">
        <div className="debug-section-title">{t('debug.billing')}</div>
        <div className="debug-row"><span>{t('debug.userInputTokens')}</span><code>{fmt(debug.user_input_tokens)}</code></div>
        <div className="debug-row"><span>{t('debug.userOutputTokens')}</span><code>{fmt(debug.user_output_tokens)}</code></div>
        <div className="debug-row debug-row-total"><span>{t('debug.userTotalTokens')}</span><code>{fmt((debug.user_input_tokens ?? 0) + (debug.user_output_tokens ?? 0))}</code></div>
      </div>
      <div className="debug-section">
        <div className="debug-section-title">{t('debug.llmCost')}</div>
        <div className="debug-row debug-row-sub"><span>{t('debug.queryTokens')}</span><code>{fmt(debug.query_tokens)}</code></div>
        <div className="debug-row debug-row-sub"><span>{t('debug.ctxTokens')}</span><code>{fmt(debug.context_tokens)}</code></div>
        <div className="debug-row debug-row-sub"><span>{t('debug.historyTokens')}</span><code>{fmt(debug.history_tokens)}</code></div>
        <div className="debug-row debug-row-sub"><span>{t('debug.systemTokens')}</span><code>{fmt(debug.system_prompt_tokens)}</code></div>
        <div className="debug-row debug-row-subtotal"><span>{t('debug.llmPromptTokens')}</span><code>{fmt(debug.llm_prompt_tokens || promptTotal)}</code></div>
        <div className="debug-row"><span>{t('debug.llmCompletionTokens')}</span><code>{fmt(debug.llm_completion_tokens)}</code></div>
        <div className="debug-row debug-row-total"><span>{t('debug.llmTotalTokens')}</span><code>{fmt(debug.llm_total_tokens)}</code></div>
      </div>
      {(debug.rerank_total_tokens ?? 0) > 0 && (
        <div className="debug-section">
          <div className="debug-section-title">{t('debug.rerankCost')}</div>
          <div className="debug-row"><span>{t('debug.rerankPromptTokens')}</span><code>{fmt(debug.rerank_prompt_tokens)}</code></div>
          <div className="debug-row"><span>{t('debug.rerankCompletionTokens')}</span><code>{fmt(debug.rerank_completion_tokens)}</code></div>
          <div className="debug-row debug-row-total"><span>{t('debug.rerankTotalTokens')}</span><code>{fmt(debug.rerank_total_tokens)}</code></div>
          {debug.rerank_model && <div className="debug-row debug-row-config"><span>{t('debug.rerankModel')}</span><code>{debug.rerank_model}</code></div>}
        </div>
      )}
      {debug.query_type && (
        <div className="debug-section">
          <div className="debug-section-title">{t('debug.classifyCost')}</div>
          <div className="debug-row"><span>{t('debug.queryType')}</span><code>{debug.query_type}</code></div>
          {(debug.classify_total_tokens ?? 0) > 0 && (
            <>
              <div className="debug-row"><span>{t('debug.classifyPromptTokens')}</span><code>{fmt(debug.classify_prompt_tokens)}</code></div>
              <div className="debug-row"><span>{t('debug.classifyCompletionTokens')}</span><code>{fmt(debug.classify_completion_tokens)}</code></div>
              <div className="debug-row debug-row-total"><span>{t('debug.classifyTotalTokens')}</span><code>{fmt(debug.classify_total_tokens)}</code></div>
            </>
          )}
          {debug.classify_model && <div className="debug-row debug-row-config"><span>{t('debug.classifyModel')}</span><code>{debug.classify_model}</code></div>}
          {debug.classify_ms != null && <div className="debug-row debug-row-config"><span>{t('debug.classifyTime')}</span><code>{(debug.classify_ms / 1000).toFixed(2)}s</code></div>}
          {debug.prompt_hash && <div className="debug-row debug-row-config"><span>{t('debug.promptHash')}</span><code>{debug.prompt_hash}</code></div>}
        </div>
      )}
      {(debug.summary_total_tokens ?? 0) > 0 && (
        <div className="debug-section">
          <div className="debug-section-title">{t('debug.summaryCost')}</div>
          <div className="debug-row"><span>{t('debug.summaryPromptTokens')}</span><code>{fmt(debug.summary_prompt_tokens)}</code></div>
          <div className="debug-row"><span>{t('debug.summaryCompletionTokens')}</span><code>{fmt(debug.summary_completion_tokens)}</code></div>
          <div className="debug-row debug-row-total"><span>{t('debug.summaryTotalTokens')}</span><code>{fmt(debug.summary_total_tokens)}</code></div>
          {debug.summary_model && <div className="debug-row debug-row-config"><span>{t('debug.summaryModel')}</span><code>{debug.summary_model}</code></div>}
          {debug.summary_ms != null && <div className="debug-row debug-row-config"><span>{t('debug.summaryTime')}</span><code>{(debug.summary_ms / 1000).toFixed(2)}s</code></div>}
        </div>
      )}
      {debug.retry_used && (
        <div className="debug-section">
          <div className="debug-section-title">{t('debug.retryUsed')}</div>
          <div className="debug-row"><span>{t('debug.rephraseMs')}</span><code>{debug.rephrase_ms != null ? (debug.rephrase_ms / 1000).toFixed(2) + 's' : '—'}</code></div>
          {debug.rephrase_query && <div className="debug-row debug-row-wide"><span>{t('debug.rephraseQuery')}</span><code className="debug-query-value">{debug.rephrase_query}</code></div>}
        </div>
      )}
      {hasTiming && (
        <div className="debug-section">
          <div className="debug-section-title">{t('debug.timing')}</div>
          <div className="debug-row"><span>{t('debug.total')}</span><code>{fmtSec(debug.total_ms)}</code></div>
          <div className="debug-row"><span>{t('debug.rag')}</span><code>{fmtSec(debug.rag_ms)}</code></div>
          <div className="debug-row"><span>{t('debug.llmTime')}</span><code>{fmtSec(debug.llm_ms)}</code></div>
          <div className="debug-row"><span>{t('debug.search')}</span><code>{fmtSec(debug.search_ms)}</code></div>
          {(debug.first_token_ms ?? 0) > 0 && <div className="debug-row"><span>{t('debug.firstToken')}</span><code>{(debug.first_token_ms! / 1000).toFixed(2)}s</code></div>}
        </div>
      )}
      {hasLlm && (
        <div className="debug-section">
          <div className="debug-section-title">{t('debug.llm')}</div>
          <div className="debug-row"><span>{t('debug.model')}</span><code>{debug.model}</code></div>
          {debug.llm_provider && <div className="debug-row"><span>{t('debug.provider')}</span><code>{debug.llm_provider}</code></div>}
          <div className="debug-row"><span>{t('debug.speed')}</span><code>{debug.tokens_per_sec ?? '—'} tok/s</code></div>
          <div className="debug-row"><span>{t('debug.response')}</span><code>{fmt(debug.response_length)} chars</code></div>
          <div className="debug-row"><span>{t('debug.tokens')}</span><code>{fmt(debug.token_count)}</code></div>
          <div className="debug-row debug-row-config"><span>{t('debug.temperature')}</span><code>{debug.temperature ?? '—'}</code></div>
          <div className="debug-row debug-row-config"><span>{t('debug.maxTokens')}</span><code>{fmt(debug.max_tokens)}</code></div>
          {debug.finish_reason && <div className="debug-row debug-row-config"><span>{t('debug.finishReason')}</span><code className={debug.finish_reason !== 'stop' ? 'debug-warning-badge' : ''}>{debug.finish_reason}</code></div>}
          {(debug.continuations ?? 0) > 0 && <div className="debug-row debug-row-config"><span>{t('debug.continuations')}</span><code className="debug-warning-badge">{debug.continuations}</code></div>}
        </div>
      )}
      {hasRag && (
        <div className="debug-section">
          <div className="debug-section-title">{t('debug.ragSection')}</div>
          <div className="debug-row"><span>{t('debug.chunks')}</span><code>{fmt(debug.chunks_found)}</code></div>
          <div className="debug-row"><span>{t('debug.topSim')}</span><code>{fmtPct(debug.top_similarity)}</code></div>
          <div className="debug-row"><span>{t('debug.minSim')}</span><code>{fmtPct(debug.min_similarity)}</code></div>
          <div className="debug-row"><span>{t('debug.historyMsgs')}</span><code>{fmt(debug.history_messages)}</code></div>
          <div className="debug-row"><span>{t('debug.promptMsgs')}</span><code>{fmt(debug.prompt_messages)}</code></div>
          <div className="debug-row"><span>{t('debug.embed')}</span><code className="debug-embed">{debug.embedding_model ?? '—'}</code></div>
        </div>
      )}
      {hasContext && (
        <div className="debug-section">
          <div className="debug-section-title">{t('debug.context')}</div>
          <div className="debug-row"><span>{t('debug.productFilter')}</span><code className={debug.product_filter ? '' : 'debug-none'}>{debug.product_filter ?? 'none'}</code></div>
          <div className="debug-row"><span>{t('debug.versionFilter')}</span><code className={debug.version_filter ? '' : 'debug-none'}>{debug.version_filter ?? 'none'}</code></div>
          <div className="debug-row"><span>{t('debug.autoProduct')}</span><code className={debug.auto_product ? '' : 'debug-none'}>{debug.auto_product ?? 'none'}</code></div>
          <div className="debug-row"><span>{t('debug.docContext')}</span><code className={debug.doc_context ? '' : 'debug-none'}>{debug.doc_context ?? 'none'}</code></div>
          <div className="debug-row"><span>{t('debug.detectedDoc')}</span><code className={debug.detected_doc_context ? '' : 'debug-none'}>{debug.detected_doc_context ?? 'none'}</code></div>
          <div className="debug-row debug-row-wide">
            <span>{t('debug.searchQuery')}</span>
            <code className={debug.search_query ? 'debug-query-value' : 'debug-none'}>{debug.search_query ?? 'none'}</code>
          </div>
          {debug.status && debug.status !== 'success' && (
            <div className="debug-row debug-row-wide debug-status-row">
              <span>{t('debug.status')}</span>
              <code className={debug.status === 'error' ? 'debug-error-badge' : 'debug-stopped-badge'}>
                {debug.status === 'error' ? t('debug.statusError') : t('debug.statusStopped')}
                {debug.status_detail ? `: ${debug.status_detail}` : ''}
              </code>
            </div>
          )}
        </div>
      )}
      {(!hasContext && debug.status && debug.status !== 'success') && (
        <div className="debug-section">
          <div className="debug-section-title">{t('debug.status')}</div>
          <div className="debug-row debug-row-wide debug-status-row">
            <span>{t('debug.status')}</span>
            <code className={debug.status === 'error' ? 'debug-error-badge' : 'debug-stopped-badge'}>
              {debug.status === 'error' ? t('debug.statusError') : t('debug.statusStopped')}
              {debug.status_detail ? `: ${debug.status_detail}` : ''}
            </code>
          </div>
        </div>
      )}
    </div>
  )
}

export function RightPanel({ content, sessionId, messageId, onClose }: Props) {
  const { t } = useTranslation()
  const isMobile = useIsMobile()
  const [previewTarget, setPreviewTarget] = useState<{ id: number; title: string } | null>(null)
  const [ratio, setRatio] = useState(loadRatio)
  const dragging = useRef(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    try { localStorage.setItem(RATIO_KEY, ratio.toFixed(4)) } catch { /* ignore */ }
  }, [ratio])

  const onPointerDown = useCallback((e: React.PointerEvent) => {
    e.preventDefault()
    dragging.current = true
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
    ;(e.target as HTMLElement).setPointerCapture?.(e.pointerId)
  }, [])

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    if (!dragging.current) return
    const parent = containerRef.current?.parentElement
    if (!parent) return
    const rect = parent.getBoundingClientRect()
    const newRatio = 1 - (e.clientX - rect.left) / rect.width
    setRatio(Math.max(MIN_RATIO, Math.min(MAX_RATIO, newRatio)))
  }, [])

  const onPointerUp = useCallback(() => {
    if (!dragging.current) return
    dragging.current = false
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
  }, [])

  const widthPercent = `${(ratio * 100).toFixed(2)}%`
  const panelStyle = isMobile ? undefined : { width: widthPercent, minWidth: widthPercent }

  const isSourcesMode = content.mode === 'sources'
  const title = isSourcesMode
    ? t('chat.sourcesPanel.title', { count: content.sources.length })
    : t('chat.debugPanel.title')
  const Icon = isSourcesMode ? FileSearch : Bug

  return (
    <>
      {isMobile && (
        <div className="sources-panel-backdrop" onClick={onClose} />
      )}
      {!isMobile && (
        <div
          className="sources-panel-splitter"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
        />
      )}
      <div ref={containerRef} className="sources-panel" style={panelStyle}>
        <div className="sources-panel-header">
          <div className="sources-panel-header-content">
            <div className="sources-panel-header-icon">
              <Icon size={14} />
            </div>
            <div className="sources-panel-header-text">
              <span className="sources-panel-title">{title}</span>
              {(sessionId != null || messageId != null) && (
                <span className="sources-panel-ids">
                  {sessionId != null && `S#${sessionId}`}
                  {sessionId != null && messageId != null && ' '}
                  {messageId != null && `M#${messageId}`}
                </span>
              )}
            </div>
          </div>
          <button className="sources-panel-close" onClick={onClose}>
            <X size={14} />
          </button>
        </div>
        <div className="sources-panel-body">
          {isSourcesMode ? (
            content.sources.map((s, i) => (
              <SourceCard
                key={i}
                source={s}
                index={i + 1}
                onPreview={(id, title) => setPreviewTarget({ id, title })}
              />
            ))
          ) : (
            <DebugPanelContent debug={content.debug} />
          )}
        </div>
        {previewTarget && (
          <MarkdownPreviewModal
            documentId={previewTarget.id}
            documentTitle={previewTarget.title}
            onClose={() => setPreviewTarget(null)}
          />
        )}
      </div>
    </>
  )
}
