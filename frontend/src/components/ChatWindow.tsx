import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Cpu, ArrowDown, Share2 } from 'lucide-react'
import type { SourceInfo, StreamStatus, DebugInfo, SuggestionChip } from '../types'
import type { ChatMessage as ChatMessageType } from '../types'
import { getSuggestions } from '../api/products'
import { useRotatingSlogan } from '../hooks/useRotatingSlogan'
import { ChatMessageComponent } from './ChatMessage'
import { ChatInput } from './ChatInput'
import { ProductBadge } from './ProductPicker'
import { RightPanel } from './RightPanel'
import { ShareModal } from './ShareModal'

const SCROLL_THRESHOLD = 100
const USER_INTERACTION_TTL = 200

interface Props {
  messages: ChatMessageType[]
  streamingContent: string
  streamingSources: SourceInfo[]
  streamingStage?: string
  status: StreamStatus
  onSend: (content: string) => void
  onCancel: () => void
  onRetry?: () => void
  editValue?: string
  productFilter?: string | null
  versionFilter?: string | null
  autoDetected?: boolean
  productLocked?: boolean
  onEditProduct?: () => void
  onClearProduct?: () => void
  onLockProduct?: () => void
  onUnlockProduct?: () => void
  sessionId?: string | null
}

export function ChatWindow({
  messages,
  streamingContent,
  streamingSources,
  streamingStage,
  status,
  onSend,
  onCancel,
  onRetry,
  editValue,
  productFilter,
  versionFilter,
  autoDetected,
  productLocked,
  onEditProduct,
  onClearProduct,
  onLockProduct,
  onUnlockProduct,
  sessionId,
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const stickToBottomRef = useRef(true)
  const userInteractingRef = useRef(false)
  const interactionTimerRef = useRef(0)
  const [showScrollBtn, setShowScrollBtn] = useState(false)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const markInteraction = () => {
      userInteractingRef.current = true
      window.clearTimeout(interactionTimerRef.current)
      interactionTimerRef.current = window.setTimeout(() => {
        userInteractingRef.current = false
      }, USER_INTERACTION_TTL)
    }

    el.addEventListener('wheel', markInteraction, { passive: true })
    el.addEventListener('touchmove', markInteraction, { passive: true })
    el.addEventListener('pointerdown', markInteraction)

    return () => {
      el.removeEventListener('wheel', markInteraction)
      el.removeEventListener('touchmove', markInteraction)
      el.removeEventListener('pointerdown', markInteraction)
      window.clearTimeout(interactionTimerRef.current)
    }
  }, [])

  const handleScroll = useCallback(() => {
    const el = containerRef.current
    if (!el) return
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    const nearBottom = distanceFromBottom <= SCROLL_THRESHOLD

    if (userInteractingRef.current) {
      stickToBottomRef.current = nearBottom
    }

    setShowScrollBtn(!nearBottom)
  }, [])

  useEffect(() => {
    if (!stickToBottomRef.current) return
    const el = containerRef.current
    if (!el) return
    el.scrollTop = el.scrollHeight
  }, [messages, streamingContent])

  const scrollToBottom = useCallback(() => {
    stickToBottomRef.current = true
    setShowScrollBtn(false)
    const el = containerRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [])

  const handleSend = useCallback(
    (content: string) => {
      stickToBottomRef.current = true
      setShowScrollBtn(false)
      onSend(content)
    },
    [onSend],
  )

  const [rightPanel, setRightPanel] = useState<{
    mode: 'sources' | 'debug'
    sources?: SourceInfo[]
    debug?: DebugInfo
    sessionId?: string
    messageId?: number
  } | null>(null)

  const handleShowSources = useCallback((sources: SourceInfo[], sessionId?: string, messageId?: number) => {
    setRightPanel({ mode: 'sources', sources, sessionId, messageId })
  }, [])

  const handleShowDebug = useCallback((debug: DebugInfo, sessionId?: string, messageId?: number) => {
    setRightPanel({ mode: 'debug', debug, sessionId, messageId })
  }, [])

  const handleEditMessage = useCallback((content: string) => {
    handleSend(content)
  }, [handleSend])

  const [shareModal, setShareModal] = useState<{ type: 'session' | 'message'; id: number | string } | null>(null)

  const handleShareMessage = useCallback((messageId: number) => {
    setShareModal({ type: 'message', id: messageId })
  }, [])

  const handleShareSession = useCallback(() => {
    if (sessionId) setShareModal({ type: 'session', id: sessionId })
  }, [sessionId])

  const { t, i18n } = useTranslation()
  const { line1, line2, accent, visible: sloganVisible } = useRotatingSlogan()
  const isEmpty = messages.length === 0 && !streamingContent

  const [dynamicChips, setDynamicChips] = useState<SuggestionChip[] | null>(null)

  useEffect(() => {
    if (!isEmpty) return
    let cancelled = false
    getSuggestions()
      .then(chips => { if (!cancelled && chips.length) setDynamicChips(chips) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [isEmpty])

  return (
    <div className="main-area">
      <div className="main-area-chat">
        {onEditProduct && onClearProduct && (
          <div className="chat-product-header">
            <ProductBadge
              productFilter={productFilter ?? null}
              versionFilter={versionFilter ?? null}
              autoDetected={autoDetected}
              locked={productLocked}
              onEdit={onEditProduct}
              onClear={onClearProduct}
              onLock={onLockProduct}
              onUnlock={onUnlockProduct}
            />
            {sessionId && messages.length > 0 && (
              <button
                className="share-chat-btn"
                onClick={handleShareSession}
                aria-label={t('share.shareChat')}
                type="button"
              >
                <Share2 size={14} />
              </button>
            )}
          </div>
        )}
        <div className="messages-container" ref={containerRef} onScroll={handleScroll}>
          {isEmpty ? (
            <div className="messages-empty">
              <img src="/logo-on-light.svg" alt="" className="empty-logo logo-light" />
              <img src="/logo-on-dark.svg" alt="" className="empty-logo logo-dark" />
              <span className="empty-badge"><Cpu size={14} />{t('empty.badge')}</span>
              <h1 className="empty-title">{t('empty.title')}</h1>
              <p className={`empty-slogan${sloganVisible ? '' : ' fading'}`}>{line1}</p>
              <p className={`empty-subslogan${sloganVisible ? '' : ' fading'}`}>
                {line2}{' '}
                <em>{accent}</em>
              </p>
              <div className="empty-suggestions">
                {dynamicChips
                  ? dynamicChips.map((chip, idx) => {
                      const text = i18n.language === 'ru' ? chip.text_ru : chip.text_en
                      return (
                        <button key={idx} className="empty-suggestion-chip" onClick={() => onSend(text)}>
                          {text}
                        </button>
                      )
                    })
                  : (['empty.suggestion1', 'empty.suggestion2', 'empty.suggestion3', 'empty.suggestion4'] as const).map(key => (
                      <button key={key} className="empty-suggestion-chip" onClick={() => onSend(t(key))}>
                        {t(key)}
                      </button>
                    ))
                }
              </div>
            </div>
          ) : (
            <>
              {messages.map((msg, idx) => (
                <ChatMessageComponent
                  key={msg.id}
                  message={msg}
                  onRetry={msg.error_code && idx === messages.length - 1 ? onRetry : undefined}
                  onShowSources={handleShowSources}
                  onShowDebug={handleShowDebug}
                  onEditMessage={msg.role === 'user' ? handleEditMessage : undefined}
                  onShareMessage={handleShareMessage}
                />
              ))}
              {status === 'streaming' && (
                <ChatMessageComponent
                  message={{
                    id: -1,
                    session_id: '',
                    role: 'assistant',
                    content: '',
                    created_at: new Date().toISOString(),
                  }}
                  isStreaming
                  streamingContent={streamingContent}
                  streamingSources={streamingSources}
                  streamingStage={streamingStage}
                  onShowSources={handleShowSources}
                  onShowDebug={handleShowDebug}
                />
              )}
              <div ref={bottomRef} />
            </>
          )}
        </div>

        {showScrollBtn && status === 'streaming' && (
          <button className="scroll-to-bottom-btn" onClick={scrollToBottom}>
            <ArrowDown size={18} />
          </button>
        )}

        <ChatInput onSend={handleSend} onCancel={onCancel} status={status} editValue={editValue} />
      </div>

      {rightPanel && (
        <RightPanel
          content={
            rightPanel.mode === 'sources'
              ? { mode: 'sources', sources: rightPanel.sources! }
              : { mode: 'debug', debug: rightPanel.debug! }
          }
          sessionId={rightPanel.sessionId}
          messageId={rightPanel.messageId}
          onClose={() => setRightPanel(null)}
        />
      )}

      {shareModal && (
        <ShareModal
          type={shareModal.type}
          id={shareModal.id}
          onClose={() => setShareModal(null)}
        />
      )}
    </div>
  )
}
