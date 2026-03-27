import { useCallback, useEffect, useRef, useState } from 'react'
import { AlertTriangle, Bug, Check, Copy, FileSearch, Globe, Loader2, Pencil, RefreshCw, Share2, ThumbsDown, ThumbsUp } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { ChatMessage as ChatMessageType, DebugInfo, SourceInfo } from '../types'
import { MarkdownRenderer } from './MarkdownRenderer'
import { submitFeedback } from '../api/chat'

interface Props {
  message: ChatMessageType
  isStreaming?: boolean
  streamingContent?: string
  streamingSources?: SourceInfo[]
  streamingStage?: string
  onRetry?: () => void
  onShowSources?: (sources: SourceInfo[], sessionId?: string, messageId?: number) => void
  onShowDebug?: (debug: DebugInfo, sessionId?: string, messageId?: number) => void
  onEditMessage?: (content: string) => void
  onShareMessage?: (messageId: number) => void
  onFeedbackChange?: (messageId: number, feedback: 'up' | 'down') => void
}

const STAGE_I18N: Record<string, string> = {
  rewriting: 'chat.stageRewriting',
  classifying: 'chat.stageClassifying',
  decomposing: 'chat.stageDecomposing',
  searching: 'chat.stageSearching',
  web_searching: 'chat.stageWebSearching',
  generating: 'chat.stageGenerating',
}

export function ChatMessageComponent({ message, isStreaming, streamingContent, streamingSources, streamingStage, onRetry, onShowSources, onShowDebug, onEditMessage, onShareMessage, onFeedbackChange }: Props) {
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
  const [currentFeedback, setCurrentFeedback] = useState<'up' | 'down' | null>(message.feedback ?? null)
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

  const handleFeedback = useCallback(async (value: 'up' | 'down') => {
    if (message.id <= 0) return
    const newValue = currentFeedback === value ? null : value
    setCurrentFeedback(newValue)
    if (newValue) {
      try {
        await submitFeedback(message.session_id, message.id, newValue)
        onFeedbackChange?.(message.id, newValue)
      } catch {
        setCurrentFeedback(currentFeedback)
      }
    }
  }, [message.id, message.session_id, currentFeedback, onFeedbackChange])

  return (
    <div className={`message ${message.role}`}>
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
                <span>{t(streamingStage && STAGE_I18N[streamingStage] ? STAGE_I18N[streamingStage] : 'chat.searching')}</span>
              </div>
            ) : (
              <>
                {debug?.web_search_used && (
                  <div className="message-source-banner message-source-banner--web">
                    <Globe size={14} />
                    <span>{t('chat.webSearchBanner')}</span>
                  </div>
                )}
                <MarkdownRenderer
                  content={content}
                  isStreaming={isStreaming}
                />
              </>
            )}
          </div>
        )}
        {isUser && !isEditing && (
          <div className="message-actions">
            <button
              className={`message-action-btn${copied ? ' message-action-btn--copied' : ''}`}
              onClick={handleCopy}
              aria-label={t('chat.copy')}
              type="button"
            >
              {copied ? <Check size={14} /> : <Copy size={14} />}
            </button>
            {onEditMessage && (
              <button
                className="message-action-btn"
                onClick={handleEditStart}
                aria-label={t('chat.edit')}
                type="button"
              >
                <Pencil size={14} />
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
              <FileSearch size={16} />
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
                    S: {String(debug.session_id).slice(0, 8)}{debug.message_id != null ? ` · M: ${debug.message_id}` : ''}
                  </span>
                )}
                {debug.status === 'stopped' && (
                  <span className="debug-stopped-badge">{t('debug.statusStopped')}</span>
                )}
                {debug.status === 'error' && (
                  <span className="debug-error-badge">{t('debug.statusError')}</span>
                )}
              </>
            )}
            <div className="message-footer-actions">
              {debug && (
                <button
                  className="message-action-btn debug-toggle"
                  onClick={() => onShowDebug?.(debug, debug.session_id, debug.message_id)}
                >
                  <Bug size={14} />
                </button>
              )}
              <button
                className={`message-action-btn feedback-btn${currentFeedback === 'up' ? ' feedback-btn--active' : ''}`}
                onClick={() => handleFeedback('up')}
                aria-label={t('chat.thumbsUp')}
                type="button"
              >
                <ThumbsUp size={14} />
              </button>
              <button
                className={`message-action-btn feedback-btn${currentFeedback === 'down' ? ' feedback-btn--active' : ''}`}
                onClick={() => handleFeedback('down')}
                aria-label={t('chat.thumbsDown')}
                type="button"
              >
                <ThumbsDown size={14} />
              </button>
              <button
                className={`message-action-btn${copied ? ' message-action-btn--copied' : ''}`}
                onClick={handleCopy}
                aria-label={t('chat.copy')}
                type="button"
              >
                {copied ? <Check size={14} /> : <Copy size={14} />}
              </button>
              {onShareMessage && message.id > 0 && (
                <button
                  className="message-action-btn share-action-btn"
                  onClick={() => onShareMessage(message.id)}
                  aria-label={t('share.shareAnswer')}
                  type="button"
                >
                  <Share2 size={14} />
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
