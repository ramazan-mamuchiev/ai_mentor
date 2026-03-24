import { useCallback, useEffect, useRef, useState } from 'react'
import { Trans, useTranslation } from 'react-i18next'
import { Cpu, ArrowDown } from 'lucide-react'
import type { SourceInfo, StreamStatus } from '../types'
import type { ChatMessage as ChatMessageType } from '../types'
import { ChatMessageComponent } from './ChatMessage'
import { ChatInput } from './ChatInput'
import { ProductBadge } from './ProductPicker'

const SCROLL_THRESHOLD = 100
const USER_INTERACTION_TTL = 200

interface Props {
  messages: ChatMessageType[]
  streamingContent: string
  streamingSources: SourceInfo[]
  status: StreamStatus
  onSend: (content: string) => void
  onCancel: () => void
  onRetry?: () => void
  editValue?: string
  onUploadClick?: () => void
  productFilter?: string | null
  versionFilter?: string | null
  autoDetected?: boolean
  productLocked?: boolean
  onEditProduct?: () => void
  onClearProduct?: () => void
}

export function ChatWindow({
  messages,
  streamingContent,
  streamingSources,
  status,
  onSend,
  onCancel,
  onRetry,
  editValue,
  onUploadClick,
  productFilter,
  versionFilter,
  autoDetected,
  productLocked,
  onEditProduct,
  onClearProduct,
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

  const { t } = useTranslation()
  const isEmpty = messages.length === 0 && !streamingContent

  return (
    <div className="main-area">
      {onEditProduct && onClearProduct && (
        <div className="chat-product-header">
          <ProductBadge
            productFilter={productFilter ?? null}
            versionFilter={versionFilter ?? null}
            autoDetected={autoDetected}
            locked={productLocked}
            onEdit={onEditProduct}
            onClear={onClearProduct}
          />
        </div>
      )}
      <div className="messages-container" ref={containerRef} onScroll={handleScroll}>
        {isEmpty ? (
          <div className="messages-empty">
            <img src="/logo-on-light.svg" alt="" className="empty-logo logo-light" />
            <img src="/logo-on-dark.svg" alt="" className="empty-logo logo-dark" />
            <span className="empty-badge"><Cpu size={14} />{t('empty.badge')}</span>
            <h1 className="empty-title">{t('empty.title')}</h1>
            <p className="empty-slogan">{t('empty.slogan')}</p>
            <div className="empty-divider">
              <span /><span className="empty-dot">·</span><span />
            </div>
            <p className="empty-subslogan">
              <Trans i18nKey="empty.subslogan">From docs to code.</Trans>{' '}
              <em>{t('empty.instantly')}</em>
            </p>
          </div>
        ) : (
          <>
            {messages.map((msg, idx) => (
              <ChatMessageComponent
                key={msg.id}
                message={msg}
                onRetry={msg.error_code && idx === messages.length - 1 ? onRetry : undefined}
              />
            ))}
            {status === 'streaming' && (
              <ChatMessageComponent
                message={{
                  id: -1,
                  session_id: 0,
                  role: 'assistant',
                  content: '',
                  created_at: new Date().toISOString(),
                }}
                isStreaming
                streamingContent={streamingContent}
                streamingSources={streamingSources}
              />
            )}
            <div ref={bottomRef} />
          </>
        )}
      </div>

      {showScrollBtn && status === 'streaming' && (
        <button className="scroll-to-bottom-btn" onClick={scrollToBottom} data-tooltip={t('chat.scrollToBottom', 'Scroll to bottom')}>
          <ArrowDown size={18} />
        </button>
      )}

      <ChatInput onSend={handleSend} onCancel={onCancel} status={status} editValue={editValue} onUploadClick={onUploadClick} />
    </div>
  )
}
