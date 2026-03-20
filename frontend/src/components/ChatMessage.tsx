import { useState } from 'react'
import { AlertTriangle, Bot, Bug, ChevronDown, ChevronUp, Loader2, RefreshCw, User } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { ChatMessage as ChatMessageType, DebugInfo, SourceInfo } from '../types'
import { MarkdownRenderer } from './MarkdownRenderer'
import { SourceCard } from './SourceCard'

function formatTimestamp(iso: string): string {
  try {
    const m = iso.match(/^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})\.?(\d{0,3})/)
    if (!m) return iso
    const ms = m[3] ? '.' + m[3].padEnd(3, '0') : '.000'
    return `${m[1]} ${m[2]}${ms}Z`
  } catch {
    return iso
  }
}

function fmt(n: number | undefined | null): string {
  return n != null ? n.toLocaleString() : '—'
}

function DebugPanel({ debug }: { debug: DebugInfo }) {
  const { t } = useTranslation()
  const promptTotal = (debug.query_tokens ?? 0) + (debug.context_tokens ?? 0)
    + (debug.history_tokens ?? 0) + (debug.system_prompt_tokens ?? 0)
  return (
    <div className="debug-panel">
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
        <div className="debug-section">
          <div className="debug-section-title">{t('debug.timing')}</div>
          <div className="debug-row"><span>{t('debug.total')}</span><code>{(debug.total_ms / 1000).toFixed(1)}s</code></div>
          <div className="debug-row"><span>{t('debug.rag')}</span><code>{(debug.rag_ms / 1000).toFixed(1)}s</code></div>
          <div className="debug-row"><span>{t('debug.llmTime')}</span><code>{(debug.llm_ms / 1000).toFixed(1)}s</code></div>
          <div className="debug-row"><span>{t('debug.search')}</span><code>{(debug.search_ms / 1000).toFixed(1)}s</code></div>
          {debug.first_token_ms > 0 && <div className="debug-row"><span>{t('debug.firstToken')}</span><code>{(debug.first_token_ms / 1000).toFixed(2)}s</code></div>}
        </div>
        <div className="debug-section">
          <div className="debug-section-title">{t('debug.llm')}</div>
          <div className="debug-row"><span>{t('debug.model')}</span><code>{debug.model}</code></div>
          {debug.llm_provider && <div className="debug-row"><span>{t('debug.provider')}</span><code>{debug.llm_provider}</code></div>}
          <div className="debug-row"><span>{t('debug.speed')}</span><code>{debug.tokens_per_sec} tok/s</code></div>
          <div className="debug-row"><span>{t('debug.response')}</span><code>{fmt(debug.response_length)} chars</code></div>
          <div className="debug-row"><span>{t('debug.tokens')}</span><code>{fmt(debug.token_count)}</code></div>
          <div className="debug-row debug-row-config"><span>{t('debug.temperature')}</span><code>{debug.temperature}</code></div>
          <div className="debug-row debug-row-config"><span>{t('debug.maxTokens')}</span><code>{fmt(debug.max_tokens)}</code></div>
        </div>
        <div className="debug-section">
          <div className="debug-section-title">{t('debug.ragSection')}</div>
          <div className="debug-row"><span>{t('debug.chunks')}</span><code>{debug.chunks_found}</code></div>
          <div className="debug-row"><span>{t('debug.topSim')}</span><code>{(debug.top_similarity * 100).toFixed(1)}%</code></div>
          <div className="debug-row"><span>{t('debug.minSim')}</span><code>{(debug.min_similarity * 100).toFixed(1)}%</code></div>
          <div className="debug-row"><span>{t('debug.historyMsgs')}</span><code>{debug.history_messages}</code></div>
          <div className="debug-row"><span>{t('debug.promptMsgs')}</span><code>{debug.prompt_messages}</code></div>
          <div className="debug-row"><span>{t('debug.embed')}</span><code className="debug-embed">{debug.embedding_model}</code></div>
        </div>
        <div className="debug-section">
          <div className="debug-section-title">{t('debug.identifiers')}</div>
          <div className="debug-row"><span>{t('debug.session')}</span><code>#{debug.session_id}</code></div>
          <div className="debug-row"><span>{t('debug.message')}</span><code>#{debug.message_id}</code></div>
          <div className="debug-row"><span>{t('debug.userMsg')}</span><code>#{debug.user_message_id}</code></div>
          {debug.timestamp && <div className="debug-row"><span>{t('debug.timestamp')}</span><code>{formatTimestamp(debug.timestamp)}</code></div>}
        </div>
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
        </div>
      </div>
    </div>
  )
}

interface Props {
  message: ChatMessageType
  isStreaming?: boolean
  streamingContent?: string
  streamingSources?: SourceInfo[]
  onRetry?: () => void
}

export function ChatMessageComponent({ message, isStreaming, streamingContent, streamingSources, onRetry }: Props) {
  const { t } = useTranslation()
  const content = isStreaming ? (streamingContent || '') : message.content
  const sources = isStreaming ? (streamingSources || []) : (message.sources || [])
  const isUser = message.role === 'user'
  const isWaiting = isStreaming && !content
  const isError = !!message.error_code
  const [sourcesExpanded, setSourcesExpanded] = useState(false)
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
            <MarkdownRenderer content={content} isStreaming={isStreaming} />
          )}
        </div>
        {sources.length > 0 && (
          <div className="sources-container">
            <div
              className="sources-toggle"
              onClick={() => setSourcesExpanded(prev => !prev)}
            >
              <span className="sources-label">{t('chat.sources', { count: sources.length })}</span>
              {sourcesExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </div>
            {sourcesExpanded && sources.map((s, i) => (
              <SourceCard key={i} source={s} />
            ))}
          </div>
        )}
        {!isStreaming && (message.duration_ms || debug) && (
          <div className="message-footer">
            {message.duration_ms ? (
              <span className="message-duration">
                {(message.duration_ms / 1000).toFixed(1)}s
              </span>
            ) : null}
            {debug && (
              <>
                <span className="message-ids">
                  S#{debug.session_id} M#{debug.message_id}
                </span>
                <button
                  className="debug-toggle"
                  onClick={() => setDebugExpanded(prev => !prev)}
                  title={t('chat.debug')}
                >
                  <Bug size={12} />
                </button>
              </>
            )}
          </div>
        )}
        {debugExpanded && debug && <DebugPanel debug={debug} />}
      </div>
    </div>
  )
}
