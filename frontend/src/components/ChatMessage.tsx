import { AlertTriangle, Bot, Bug, FileSearch, Loader2, RefreshCw, User } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { ChatMessage as ChatMessageType, DebugInfo, SourceInfo } from '../types'
import { MarkdownRenderer } from './MarkdownRenderer'

interface Props {
  message: ChatMessageType
  isStreaming?: boolean
  streamingContent?: string
  streamingSources?: SourceInfo[]
  onRetry?: () => void
  onShowSources?: (sources: SourceInfo[], sessionId?: number, messageId?: number) => void
  onShowDebug?: (debug: DebugInfo, sessionId?: number, messageId?: number) => void
}

export function ChatMessageComponent({ message, isStreaming, streamingContent, streamingSources, onRetry, onShowSources, onShowDebug }: Props) {
  const { t } = useTranslation()
  const content = isStreaming ? (streamingContent || '') : message.content
  const sources = isStreaming ? (streamingSources || []) : (message.sources || [])
  const isUser = message.role === 'user'
  const isWaiting = isStreaming && !content
  const isError = !!message.error_code
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
                  onClick={() => onShowDebug?.(debug, debug.session_id, debug.message_id)}
                  data-tooltip={t('chat.debug')}
                >
                  <Bug size={12} />
                </button>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
