import { useCallback, useEffect, useRef, useState } from 'react'
import { Bug, FileSearch, Share2, X, Database } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { DebugInfo, SourceInfo, McpSourceInfo } from '../types'
import type { McpRequestDetail } from '../api/admin'
import { SourceCard } from './SourceCard'
import { MarkdownPreviewModal } from './MarkdownPreviewModal'
import { ShareModal } from './ShareModal'

const MOBILE_BP = 768
const RATIO_KEY = 'lexiro-right-panel-ratio'
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

interface McpDebugPanelMode {
  mode: 'mcp-debug'
  detail: McpRequestDetail
}

interface McpSourcesPanelMode {
  mode: 'mcp-sources'
  sources: McpSourceInfo[]
}

type PanelContent = SourcesContent | DebugContent | McpDebugPanelMode | McpSourcesPanelMode

interface Props {
  content: PanelContent
  sessionId?: string
  messageId?: number
  onClose: () => void
  onSwitchToSources?: () => void
}

export function DebugPanelContent({ debug }: { debug: DebugInfo }) {
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
        {debug.model && <div className="debug-row debug-row-config"><span>{t('debug.model')}</span><code>{debug.model}</code></div>}
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
          {debug.classify_input && (
            <div className="debug-row debug-row-wide"><span>{t('debug.classifyInput')}</span><code className="debug-query-value">{debug.classify_input}</code></div>
          )}
          {debug.classify_product && (
            <div className="debug-row"><span>{t('debug.classifyProduct')}</span><code>{debug.classify_product}</code></div>
          )}
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
      {debug.decompose_used && (
        <div className="debug-section">
          <div className="debug-section-title">{t('debug.decompose')}</div>
          <div className="debug-row"><span>{t('debug.decomposeUsed')}</span><code>✓</code></div>
          {debug.decompose_sub_queries && debug.decompose_sub_queries.length > 0 && (
            <div className="debug-row debug-row-wide">
              <span>{t('debug.decomposeSubQueries')}</span>
              <code className="debug-query-value">{debug.decompose_sub_queries.map((q, i) => `${i + 1}. ${q}`).join('\n')}</code>
            </div>
          )}
          {debug.decompose_sub_products && debug.decompose_sub_products.some(Boolean) && (
            <div className="debug-row debug-row-wide">
              <span>{t('debug.decomposeSubProducts')}</span>
              <code className="debug-query-value">{debug.decompose_sub_products.map((p, i) => `${i + 1}. ${p ?? '—'}`).join('\n')}</code>
            </div>
          )}
          {(debug.decompose_total_tokens ?? 0) > 0 && (
            <>
              <div className="debug-row"><span>{t('debug.decomposePromptTokens')}</span><code>{fmt(debug.decompose_prompt_tokens)}</code></div>
              <div className="debug-row"><span>{t('debug.decomposeCompletionTokens')}</span><code>{fmt(debug.decompose_completion_tokens)}</code></div>
              <div className="debug-row debug-row-total"><span>{t('debug.decomposeTotalTokens')}</span><code>{fmt(debug.decompose_total_tokens)}</code></div>
            </>
          )}
          {debug.decompose_model && <div className="debug-row debug-row-config"><span>{t('debug.decomposeModel')}</span><code>{debug.decompose_model}</code></div>}
          {debug.decompose_ms != null && <div className="debug-row debug-row-config"><span>{t('debug.decomposeTime')}</span><code>{(debug.decompose_ms / 1000).toFixed(2)}s</code></div>}
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
      {debug.web_search_used && (
        <div className="debug-section">
          <div className="debug-section-title">{t('debug.webSearchCost')}</div>
          <div className="debug-row"><span>{t('debug.webSearchUsed')}</span><code>✓</code></div>
          {debug.web_search_queries && debug.web_search_queries.length > 0 && (
            <div className="debug-row debug-row-wide">
              <span>{t('debug.webSearchQueries')}</span>
              <code className="debug-query-value">{debug.web_search_queries.join('\n')}</code>
            </div>
          )}
          {(debug.web_search_sources_count ?? 0) > 0 && (
            <div className="debug-row"><span>{t('debug.webSearchSources')}</span><code>{fmt(debug.web_search_sources_count)}</code></div>
          )}
          {(debug.web_search_total_tokens ?? 0) > 0 && (
            <>
              <div className="debug-row"><span>{t('debug.webSearchPromptTokens')}</span><code>{fmt(debug.web_search_prompt_tokens)}</code></div>
              <div className="debug-row"><span>{t('debug.webSearchCompletionTokens')}</span><code>{fmt(debug.web_search_completion_tokens)}</code></div>
              <div className="debug-row debug-row-total"><span>{t('debug.webSearchTotalTokens')}</span><code>{fmt(debug.web_search_total_tokens)}</code></div>
            </>
          )}
          {debug.web_search_model && <div className="debug-row debug-row-config"><span>{t('debug.webSearchModel')}</span><code>{debug.web_search_model}</code></div>}
          {debug.web_search_ms != null && <div className="debug-row debug-row-config"><span>{t('debug.webSearchTime')}</span><code>{(debug.web_search_ms / 1000).toFixed(2)}s</code></div>}
          {(debug.web_search_context_length ?? 0) > 0 && <div className="debug-row debug-row-config"><span>{t('debug.webSearchCtxLen')}</span><code>{fmt(debug.web_search_context_length)} chars</code></div>}
        </div>
      )}
      {(debug.rewrite_total_tokens ?? 0) > 0 && (
        <div className="debug-section">
          <div className="debug-section-title">{t('debug.rewriteCost')}</div>
          <div className="debug-row"><span>{t('debug.rewritePromptTokens')}</span><code>{fmt(debug.rewrite_prompt_tokens)}</code></div>
          <div className="debug-row"><span>{t('debug.rewriteCompletionTokens')}</span><code>{fmt(debug.rewrite_completion_tokens)}</code></div>
          <div className="debug-row debug-row-total"><span>{t('debug.rewriteTotalTokens')}</span><code>{fmt(debug.rewrite_total_tokens)}</code></div>
          {debug.rewrite_model && <div className="debug-row debug-row-config"><span>{t('debug.rewriteModel')}</span><code>{debug.rewrite_model}</code></div>}
        </div>
      )}
      {debug.retry_used && (
        <div className="debug-section">
          <div className="debug-section-title">{t('debug.retryUsed')}</div>
          <div className="debug-row"><span>{t('debug.rephraseMs')}</span><code>{debug.rephrase_ms != null ? (debug.rephrase_ms / 1000).toFixed(2) + 's' : '—'}</code></div>
          {debug.rephrase_query && <div className="debug-row debug-row-wide"><span>{t('debug.rephraseQuery')}</span><code className="debug-query-value">{debug.rephrase_query}</code></div>}
          {(debug.rephrase_total_tokens ?? 0) > 0 && (
            <>
              <div className="debug-row"><span>{t('debug.rephrasePromptTokens')}</span><code>{fmt(debug.rephrase_prompt_tokens)}</code></div>
              <div className="debug-row"><span>{t('debug.rephraseCompletionTokens')}</span><code>{fmt(debug.rephrase_completion_tokens)}</code></div>
              <div className="debug-row debug-row-total"><span>{t('debug.rephraseTotalTokens')}</span><code>{fmt(debug.rephrase_total_tokens)}</code></div>
            </>
          )}
          {debug.rephrase_model && <div className="debug-row debug-row-config"><span>{t('debug.rephraseModel')}</span><code>{debug.rephrase_model}</code></div>}
        </div>
      )}
      {(debug.embedding_api_tokens ?? 0) > 0 && (
        <div className="debug-section">
          <div className="debug-section-title">{t('debug.embeddingApiCost')}</div>
          <div className="debug-row"><span>{t('debug.embeddingApiTokens')}</span><code>{fmt(debug.embedding_api_tokens)}</code></div>
          <div className="debug-row debug-row-config"><span>{t('debug.embeddingModel')}</span><code>{debug.embedding_model ?? '—'}</code></div>
        </div>
      )}
      {(() => {
        const grandPrompt = (debug.llm_prompt_tokens ?? 0) + (debug.rerank_prompt_tokens ?? 0)
          + (debug.classify_prompt_tokens ?? 0) + (debug.summary_prompt_tokens ?? 0)
          + (debug.rewrite_prompt_tokens ?? 0) + (debug.decompose_prompt_tokens ?? 0)
          + (debug.web_search_prompt_tokens ?? 0) + (debug.rephrase_prompt_tokens ?? 0)
        const grandCompletion = (debug.llm_completion_tokens ?? 0) + (debug.rerank_completion_tokens ?? 0)
          + (debug.classify_completion_tokens ?? 0) + (debug.summary_completion_tokens ?? 0)
          + (debug.rewrite_completion_tokens ?? 0) + (debug.decompose_completion_tokens ?? 0)
          + (debug.web_search_completion_tokens ?? 0) + (debug.rephrase_completion_tokens ?? 0)
        const grandEmbedding = debug.embedding_api_tokens ?? 0
        const grandTotal = grandPrompt + grandCompletion + grandEmbedding
        if (grandTotal <= 0) return null
        return (
          <div className="debug-section debug-section-grand">
            <div className="debug-section-title">{t('debug.grandTotal')}</div>
            <div className="debug-row"><span>{t('debug.grandTotalPrompt')}</span><code>{fmt(grandPrompt)}</code></div>
            <div className="debug-row"><span>{t('debug.grandTotalCompletion')}</span><code>{fmt(grandCompletion)}</code></div>
            <div className="debug-row debug-row-total"><span>{t('debug.grandTotalTokens')}</span><code>{fmt(grandPrompt + grandCompletion)}</code></div>
            {grandEmbedding > 0 && <div className="debug-row"><span>{t('debug.grandTotalEmbedding')}</span><code>{fmt(grandEmbedding)}</code></div>}
          </div>
        )
      })()}
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
          <div className="debug-row"><span>{t('debug.chunks')}</span><code>{fmt(debug.chunks_found)}{debug.effective_top_k ? ` / ${debug.effective_top_k}` : ''}</code></div>
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

function fmtMs(ms: number | null | undefined): string {
  if (ms == null) return '—'
  return ms < 1000 ? `${Math.round(ms)}ms` : `${(ms / 1000).toFixed(2)}s`
}

function fmtUsd(v: string | null | undefined): string {
  if (v == null) return '—'
  const n = parseFloat(v)
  return isNaN(n) ? v : `$${n.toFixed(6)}`
}

export function McpDebugPanelContent({ detail, onSwitchToSources }: { detail: McpRequestDetail; onSwitchToSources?: () => void }) {
  const { t } = useTranslation()
  const resolveTotal = (detail.resolve_prompt_tokens ?? 0) + (detail.resolve_completion_tokens ?? 0)
  const rerankTotal = (detail.rerank_total_tokens ?? 0)
  const totalTokens = detail.query_tokens + detail.response_tokens + detail.embedding_tokens
    + rerankTotal + resolveTotal

  return (
    <div className="debug-grid right-panel-debug">
      <div className="debug-section">
        <div className="debug-section-title">{t('debug.mcp.query')}</div>
        <div className="debug-row"><span>{t('debug.mcp.toolName')}</span><code>{detail.tool_name}</code></div>
        {detail.query_text && <div className="debug-row debug-row-wide"><span>{t('debug.mcp.queryText')}</span><code className="debug-query-value">{detail.query_text}</code></div>}
        {detail.product_filter && <div className="debug-row"><span>{t('debug.mcp.productFilter')}</span><code>{detail.product_filter}</code></div>}
        {detail.version_filter && <div className="debug-row"><span>{t('debug.mcp.versionFilter')}</span><code>{detail.version_filter}</code></div>}
        {detail.doc_type_filter && <div className="debug-row"><span>{t('debug.mcp.docTypeFilter')}</span><code>{detail.doc_type_filter}</code></div>}
      </div>

      <div className="debug-section">
        <div className="debug-section-title">{t('debug.mcp.results')}</div>
        <div className="debug-row"><span>{t('debug.mcp.resultCount')}</span><code>{fmt(detail.result_count)}</code></div>
        <div className="debug-row"><span>{t('debug.mcp.topSimilarity')}</span><code>{fmtPct(detail.top_similarity)}</code></div>
        <div className="debug-row"><span>{t('debug.mcp.responseLength')}</span><code>{fmt(detail.response_length)} chars</code></div>
      </div>

      <div className="debug-section">
        <div className="debug-section-title">{t('debug.mcp.timing')}</div>
        <div className="debug-row debug-row-total"><span>{t('debug.mcp.totalDuration')}</span><code>{fmtMs(detail.duration_ms)}</code></div>
        {(detail.embed_ms ?? 0) > 0 && <div className="debug-row"><span>{t('debug.mcp.embedMs')}</span><code>{fmtMs(detail.embed_ms)}</code></div>}
        {(detail.search_ms ?? 0) > 0 && <div className="debug-row"><span>{t('debug.mcp.searchMs')}</span><code>{fmtMs(detail.search_ms)}</code></div>}
        {(detail.rerank_ms ?? 0) > 0 && <div className="debug-row"><span>{t('debug.mcp.rerankMs')}</span><code>{fmtMs(detail.rerank_ms)}</code></div>}
        {(detail.resolve_ms ?? 0) > 0 && <div className="debug-row"><span>{t('debug.mcp.resolveMs')}</span><code>{fmtMs(detail.resolve_ms)}</code></div>}
      </div>

      <div className="debug-section">
        <div className="debug-section-title">{t('debug.mcp.tokens')}</div>
        <div className="debug-row"><span>{t('debug.mcp.queryTokens')}</span><code>{fmt(detail.query_tokens)}</code></div>
        <div className="debug-row"><span>{t('debug.mcp.responseTokens')}</span><code>{fmt(detail.response_tokens)}</code></div>
        {detail.embedding_tokens > 0 && <div className="debug-row"><span>{t('debug.mcp.embeddingTokens')}</span><code>{fmt(detail.embedding_tokens)}</code></div>}
        {rerankTotal > 0 && (
          <>
            <div className="debug-row"><span>{t('debug.mcp.rerankPrompt')}</span><code>{fmt(detail.rerank_prompt_tokens)}</code></div>
            <div className="debug-row"><span>{t('debug.mcp.rerankCompletion')}</span><code>{fmt(detail.rerank_completion_tokens)}</code></div>
            <div className="debug-row"><span>{t('debug.mcp.rerankTotal')}</span><code>{fmt(detail.rerank_total_tokens)}</code></div>
            {detail.rerank_model && <div className="debug-row debug-row-config"><span>{t('debug.mcp.rerankModel')}</span><code>{detail.rerank_model}</code></div>}
          </>
        )}
        {resolveTotal > 0 && (
          <>
            <div className="debug-row"><span>{t('debug.mcp.resolvePrompt')}</span><code>{fmt(detail.resolve_prompt_tokens)}</code></div>
            <div className="debug-row"><span>{t('debug.mcp.resolveCompletion')}</span><code>{fmt(detail.resolve_completion_tokens)}</code></div>
            {detail.resolve_model && <div className="debug-row debug-row-config"><span>{t('debug.mcp.resolveModel')}</span><code>{detail.resolve_model}</code></div>}
          </>
        )}
        <div className="debug-row debug-row-total"><span>{t('debug.mcp.totalTokens')}</span><code>{fmt(totalTokens)}</code></div>
      </div>

      <div className="debug-section">
        <div className="debug-section-title">{t('debug.mcp.cost')}</div>
        <div className="debug-row"><span>{t('debug.mcp.cogs')}</span><code>{fmtUsd(detail.cogs_usd)}</code></div>
        <div className="debug-row debug-row-total"><span>{t('debug.mcp.charge')}</span><code>{fmtUsd(detail.charge_usd)}</code></div>
      </div>

      <div className="debug-section">
        <div className="debug-section-title">{t('debug.mcp.client')}</div>
        <div className="debug-row"><span>{t('debug.mcp.requestId')}</span><code style={{ fontSize: 10 }}>{detail.request_id}</code></div>
        {detail.client_ip && <div className="debug-row"><span>{t('debug.mcp.clientIp')}</span><code>{detail.client_ip}</code></div>}
        {detail.user_agent && <div className="debug-row debug-row-wide"><span>{t('debug.mcp.userAgent')}</span><code className="debug-query-value" style={{ fontSize: 10 }}>{detail.user_agent}</code></div>}
        {detail.key_prefix && <div className="debug-row"><span>{t('debug.mcp.keyPrefix')}</span><code>{detail.key_prefix}</code></div>}
      </div>

      {detail.error && (
        <div className="debug-section">
          <div className="debug-section-title">{t('debug.mcp.error')}</div>
          <div className="debug-row debug-row-wide">
            <span>{t('debug.status')}</span>
            <code className="debug-error-badge">{detail.error}</code>
          </div>
        </div>
      )}

      {detail.sources && detail.sources.length > 0 && onSwitchToSources && (
        <div className="debug-section">
          <button
            className="mcp-sources-button"
            onClick={onSwitchToSources}
          >
            <FileSearch size={14} />
            {t('debug.mcp.viewSources', { count: detail.sources.length })}
          </button>
        </div>
      )}
    </div>
  )
}

function mcpSourceToSourceInfo(s: McpSourceInfo): SourceInfo {
  return {
    document_id: s.document_id,
    doc_title: s.doc_title,
    heading_path: s.heading_path,
    similarity: s.similarity,
    content_preview: s.content_preview ?? '',
    product_name: s.product_name,
    firmware_version: s.firmware_version ?? '',
    doc_type: s.doc_type,
  }
}

export function RightPanel({ content, sessionId, messageId, onClose, onSwitchToSources }: Props) {
  const { t } = useTranslation()
  const isMobile = useIsMobile()
  const [previewTarget, setPreviewTarget] = useState<{ id: number; title: string } | null>(null)
  const [shareModal, setShareModal] = useState(false)
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
  const isMcpDebug = content.mode === 'mcp-debug'
  const isMcpSources = content.mode === 'mcp-sources'
  const title = isSourcesMode
    ? t('chat.sourcesPanel.title', { count: content.sources.length })
    : isMcpSources
      ? t('chat.sourcesPanel.title', { count: content.sources.length })
      : isMcpDebug
        ? t('debug.mcp.panelTitle')
        : t('chat.debugPanel.title')
  const Icon = (isSourcesMode || isMcpSources) ? FileSearch : isMcpDebug ? Database : Bug

  const mcpSubtitle = isMcpDebug
    ? `${content.detail.tool_name} · ${sessionId?.slice(0, 8) ?? ''}`
    : isMcpSources
      ? sessionId?.slice(0, 8) ?? ''
      : null

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
              <Icon size={18} />
            </div>
            <div className="sources-panel-header-text">
              <span className="sources-panel-title">{title}</span>
              {mcpSubtitle ? (
                <span className="sources-panel-ids">{mcpSubtitle}</span>
              ) : (sessionId != null || messageId != null) ? (
                <span className="sources-panel-ids">
                  {sessionId != null ? `S: ${sessionId.slice(0, 8)}` : ''}{sessionId != null && messageId != null ? ' · ' : ''}{messageId != null ? `M: ${messageId}` : ''}
                </span>
              ) : null}
            </div>
          </div>
          <div className="sources-panel-header-actions">
            {!isSourcesMode && !isMcpDebug && !isMcpSources && messageId != null && (
              <button
                className="sources-panel-share"
                onClick={() => setShareModal(true)}
              >
                <Share2 size={14} />
              </button>
            )}
            <button className="sources-panel-close" onClick={onClose}>
              <X size={14} />
            </button>
          </div>
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
          ) : isMcpDebug ? (
            <McpDebugPanelContent detail={content.detail} onSwitchToSources={onSwitchToSources} />
          ) : isMcpSources ? (
            content.sources.map((s, i) => (
              <SourceCard
                key={i}
                source={mcpSourceToSourceInfo(s)}
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
        {shareModal && messageId != null && (
          <ShareModal
            type="debug_chat"
            id={messageId}
            onClose={() => setShareModal(false)}
          />
        )}
      </div>
    </>
  )
}
