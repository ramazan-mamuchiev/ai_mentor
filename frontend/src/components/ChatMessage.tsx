import { useState } from 'react'
import { AlertTriangle, Bot, Bug, FileSearch, Loader2, RefreshCw, User } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { ChatMessage as ChatMessageType, DebugInfo, SourceInfo } from '../types'
import { MarkdownRenderer } from './MarkdownRenderer'
import { DebugPanelWrapper } from './DebugPanelWrapper'

function fmt(n: number | undefined | null): string {
  return n != null ? n.toLocaleString() : '—'
}

function fmtSec(ms: number | undefined | null): string {
  return ms != null ? (ms / 1000).toFixed(1) + 's' : '—'
}

function fmtPct(v: number | undefined | null): string {
  return v != null ? (v * 100).toFixed(1) + '%' : '—'
}

function DebugPanel({ debug, onCollapse }: { debug: DebugInfo; onCollapse?: () => void }) {
  const { t } = useTranslation()
  const promptTotal = (debug.query_tokens ?? 0) + (debug.context_tokens ?? 0)
    + (debug.history_tokens ?? 0) + (debug.system_prompt_tokens ?? 0)
  const hasTiming = debug.total_ms != null || debug.rag_ms != null
  const hasLlm = debug.model != null
  const hasRag = debug.chunks_found != null
  const hasContext = debug.product_filter != null || debug.search_query != null || debug.chunks_found != null
  return (
    <DebugPanelWrapper onCollapse={onCollapse} className="debug-panel">
      <div className="debug-grid">
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
          <div className="debug-section debug-section-full">
            <div className="debug-section-title">{t('debug.context')}</div>
            <div className="debug-context-grid">
              <div className="debug-row"><span>{t('debug.productFilter')}</span><code className={debug.product_filter ? '' : 'debug-none'}>{debug.product_filter ?? 'none'}</code></div>
              <div className="debug-row"><span>{t('debug.versionFilter')}</span><code className={debug.version_filter ? '' : 'debug-none'}>{debug.version_filter ?? 'none'}</code></div>
              <div className="debug-row"><span>{t('debug.autoProduct')}</span><code className={debug.auto_product ? '' : 'debug-none'}>{debug.auto_product ?? 'none'}</code></div>
              <div className="debug-row"><span>{t('debug.docContext')}</span><code className={debug.doc_context ? '' : 'debug-none'}>{debug.doc_context ?? 'none'}</code></div>
              <div className="debug-row"><span>{t('debug.detectedDoc')}</span><code className={debug.detected_doc_context ? '' : 'debug-none'}>{debug.detected_doc_context ?? 'none'}</code></div>
            </div>
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
          <div className="debug-section debug-section-full">
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
    </DebugPanelWrapper>
  )
}

interface Props {
  message: ChatMessageType
  isStreaming?: boolean
  streamingContent?: string
  streamingSources?: SourceInfo[]
  onRetry?: () => void
  onShowSources?: (sources: SourceInfo[], sessionId?: number, messageId?: number) => void
}

export function ChatMessageComponent({ message, isStreaming, streamingContent, streamingSources, onRetry, onShowSources }: Props) {
  const { t } = useTranslation()
  const content = isStreaming ? (streamingContent || '') : message.content
  const sources = isStreaming ? (streamingSources || []) : (message.sources || [])
  const isUser = message.role === 'user'
  const isWaiting = isStreaming && !content
  const isError = !!message.error_code
  const [debugExpanded, setDebugExpanded] = useState(false)
  const debug = message.debug

  return (
    <div className={`message ${message.role}`}>
      <div className="message-avatar">
        {isUser ? <User size={16} /> : <Bot size={16} />}
      </div>
      <div className="message-body">
        <div className="message-content">
          {isError ? (
            <div className="message-error">
              <AlertTriangle size={16} />
              <span>{t(`error.${message.error_code}`)}</span>
              {onRetry && (
                <button className="retry-button" onClick={onRetry}>
                  <RefreshCw size={12} />
                  <span>{t('chat.retry')}</span>
                </button>
              )}
            </div>
          ) : isUser ? (
            content
          ) : isWaiting ? (
            <div className="typing-indicator">
              <Loader2 size={14} className="typing-spinner" />
              <span>{t('chat.searching')}</span>
            </div>
          ) : (
            <MarkdownRenderer
              content={content}
              isStreaming={isStreaming}
            />
          )}
        </div>
        {sources.length > 0 && (
          <div className="sources-container">
            <button
              className="sources-toggle"
              onClick={() => onShowSources?.(sources, message.debug?.session_id, message.debug?.message_id)}
            >
              <FileSearch size={14} />
              <span className="sources-label">{t('chat.sources', { count: sources.length })}</span>
            </button>
          </div>
        )}
        {!isStreaming && !isUser && (message.duration_ms != null || debug) && (
          <div className="message-footer">
            {message.duration_ms != null && (
              <span className="message-duration">
                {(message.duration_ms / 1000).toFixed(1)}s
              </span>
            )}
            {debug && (
              <>
                {(debug.session_id != null) && (
                  <span className="message-ids">
                    S#{debug.session_id}{debug.message_id ? ` M#${debug.message_id}` : ''}
                  </span>
                )}
                {debug.status === 'stopped' && (
                  <span className="debug-stopped-badge">{t('debug.statusStopped')}</span>
                )}
                {debug.status === 'error' && (
                  <span className="debug-error-badge">{t('debug.statusError')}</span>
                )}
                <button
                  className="debug-toggle"
                  onClick={() => setDebugExpanded(prev => !prev)}
                  data-tooltip={t('chat.debug')}
                >
                  <Bug size={12} />
                </button>
              </>
            )}
          </div>
        )}
        {debugExpanded && debug && <DebugPanel debug={debug} onCollapse={() => setDebugExpanded(false)} />}
      </div>
    </div>
  )
}
