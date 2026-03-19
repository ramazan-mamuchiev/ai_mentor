import { useState } from 'react'
import { AlertTriangle, Bot, Bug, ChevronDown, ChevronUp, Loader2, RefreshCw, User } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { ChatMessage as ChatMessageType, DebugInfo, SourceInfo } from '../types'
import { MarkdownRenderer } from './MarkdownRenderer'
import { SourceCard } from './SourceCard'

function DebugPanel({ debug }: { debug: DebugInfo }) {
  const { t } = useTranslation()
  return (
    <div className="debug-panel">
      <div className="debug-grid">
        <div className="debug-section">
          <div className="debug-section-title">{t('debug.identifiers')}</div>
          <div className="debug-row"><span>{t('debug.session')}</span><code>#{debug.session_id}</code></div>
          <div className="debug-row"><span>{t('debug.message')}</span><code>#{debug.message_id}</code></div>
          <div className="debug-row"><span>{t('debug.userMsg')}</span><code>#{debug.user_message_id}</code></div>
        </div>
        <div className="debug-section">
          <div className="debug-section-title">{t('debug.llm')}</div>
          <div className="debug-row"><span>{t('debug.model')}</span><code>{debug.model}</code></div>
          <div className="debug-row"><span>{t('debug.tokens')}</span><code>{debug.token_count}</code></div>
          <div className="debug-row"><span>{t('debug.speed')}</span><code>{debug.tokens_per_sec} tok/s</code></div>
          <div className="debug-row"><span>{t('debug.response')}</span><code>{debug.response_length} chars</code></div>
        </div>
        <div className="debug-section">
          <div className="debug-section-title">{t('debug.timing')}</div>
          <div className="debug-row"><span>{t('debug.total')}</span><code>{(debug.total_ms / 1000).toFixed(1)}s</code></div>
          <div className="debug-row"><span>{t('debug.rag')}</span><code>{(debug.rag_ms / 1000).toFixed(1)}s</code></div>
          <div className="debug-row"><span>{t('debug.llmTime')}</span><code>{(debug.llm_ms / 1000).toFixed(1)}s</code></div>
          <div className="debug-row"><span>{t('debug.search')}</span><code>{(debug.search_ms / 1000).toFixed(1)}s</code></div>
        </div>
        <div className="debug-section">
          <div className="debug-section-title">{t('debug.ragSection')}</div>
          <div className="debug-row"><span>{t('debug.chunks')}</span><code>{debug.chunks_found}</code></div>
          <div className="debug-row"><span>{t('debug.topSim')}</span><code>{(debug.top_similarity * 100).toFixed(1)}%</code></div>
          <div className="debug-row"><span>{t('debug.minSim')}</span><code>{(debug.min_similarity * 100).toFixed(1)}%</code></div>
          <div className="debug-row"><span>{t('debug.ctxTokens')}</span><code>{debug.context_tokens}</code></div>
          <div className="debug-row"><span>{t('debug.embed')}</span><code className="debug-embed">{debug.embedding_model}</code></div>
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
        <div className={`message-content ${isStreaming && content ? 'streaming-cursor' : ''}`}>
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
            <MarkdownRenderer content={content} />
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
