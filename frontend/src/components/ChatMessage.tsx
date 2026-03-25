import { useCallback, useEffect, useRef, useState } from 'react'
import { AlertTriangle, Bot, Bug, Check, Copy, FileSearch, Loader2, Pencil, RefreshCw, Share2 } from 'lucide-react'
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
  onEditMessage?: (content: string) => void
  onShareMessage?: (messageId: number) => void
}

export function ChatMessageComponent({ message, isStreaming, streamingContent, streamingSources, onRetry, onShowSources, onShowDebug, onEditMessage, onShareMessage }: Props) {
  const { t } = useTranslation()
  const content = isStreaming ? (streamingContent || '') : message.content
  const sources = isStreaming ? (streamingSources || []) : (message.sources || [])
  const isUser = message.role === 'user'
  const isWaiting = isStreaming && !content
  const isError = !!message.error_code
  const debug = message.debug

  const [isEditing, setIsEditing] = useState(false)
  const [editText, setEditText] = useState('')
  const [copied, setCopied] = useState(false)
  const editTextareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (isEditing && editTextareaRef.current) {
      const el = editTextareaRef.current
      el.focus()
      el.setSelectionRange(el.value.length, el.value.length)
      el.style.height = 'auto'
      el.style.height = Math.min(el.scrollHeight, 200) + 'px'
    }
  }, [isEditing])

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(content)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // fallback for older browsers
      const textarea = document.createElement('textarea')
      textarea.value = content
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }, [content])

  const handleEditStart = useCallback(() => {
    setEditText(content)
    setIsEditing(true)
  }, [content])

  const handleEditCancel = useCallback(() => {
    setIsEditing(false)
    setEditText('')
  }, [])

  const handleEditSend = useCallback(() => {
    const trimmed = editText.trim()
    if (trimmed && onEditMessage) {
      onEditMessage(trimmed)
    }
    setIsEditing(false)
    setEditText('')
  }, [editText, onEditMessage])

  const handleEditKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleEditSend()
    } else if (e.key === 'Escape') {
      handleEditCancel()
    }
  }, [handleEditSend, handleEditCancel])

  const handleEditInput = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setEditText(e.target.value)
    const el = e.target
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 200) + 'px'
  }, [])

  return (
    <div className={`message ${message.role}`}>
      {!isUser && (
        <div className="message-avatar">
          <Bot size={16} />
        </div>
      )}
      <div className="message-body">
        {isEditing ? (
          <div className="message-edit-mode">
            <div className="message-edit-wrapper">
              <textarea
                ref={editTextareaRef}
                className="message-edit-textarea"
                value={editText}
                onChange={handleEditInput}
                onKeyDown={handleEditKeyDown}
                placeholder={t('input.placeholder')}
                rows={1}
              />
              <div className="message-edit-actions">
                <button
                  className="message-edit-cancel"
                  onClick={handleEditCancel}
                  type="button"
                >
                  {t('chat.editCancel')}
                </button>
                <button
                  className="message-edit-send"
                  onClick={handleEditSend}
                  disabled={!editText.trim()}
                  type="button"
                >
                  {t('chat.editSend')}
                </button>
              </div>
            </div>
          </div>
        ) : (
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
        )}
        {isUser && !isEditing && (
          <div className="message-actions">
            <button
              className={`message-action-btn${copied ? ' message-action-btn--copied' : ''}`}
              onClick={handleCopy}
              data-tooltip={copied ? t('chat.copied') : t('chat.copy')}
              aria-label={t('chat.copy')}
              type="button"
            >
              {copied ? <Check size={12} /> : <Copy size={12} />}
            </button>
            {onEditMessage && (
              <button
                className="message-action-btn"
                onClick={handleEditStart}
                data-tooltip={t('chat.edit')}
                aria-label={t('chat.edit')}
                type="button"
              >
                <Pencil size={12} />
              </button>
            )}
          </div>
        )}
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
        {!isStreaming && !isUser && (
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
            <button
              className={`message-action-btn${copied ? ' message-action-btn--copied' : ''}`}
              onClick={handleCopy}
              data-tooltip={copied ? t('chat.copied') : t('chat.copy')}
              aria-label={t('chat.copy')}
              type="button"
            >
              {copied ? <Check size={12} /> : <Copy size={12} />}
            </button>
            {onShareMessage && message.id > 0 && (
              <button
                className="message-action-btn share-action-btn"
                onClick={() => onShareMessage(message.id)}
                data-tooltip={t('share.shareAnswer')}
                aria-label={t('share.shareAnswer')}
                type="button"
              >
                <Share2 size={12} />
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
