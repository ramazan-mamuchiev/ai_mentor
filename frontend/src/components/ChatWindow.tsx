import { useCallback, useEffect, useRef, useState } from 'react'
import { Trans, useTranslation } from 'react-i18next'
import { Cpu, ArrowDown } from 'lucide-react'
import type { SourceInfo, StreamStatus } from '../types'
import type { ChatMessage as ChatMessageType } from '../types'
import { ChatMessageComponent } from './ChatMessage'
import { ChatInput } from './ChatInput'

const SCROLL_THRESHOLD = 100

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
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const stickToBottomRef = useRef(true)
  const programmaticScrollRef = useRef(false)
  const [showScrollBtn, setShowScrollBtn] = useState(false)

  const handleScroll = useCallback(() => {
    if (programmaticScrollRef.current) return
    const el = containerRef.current
    if (!el) return
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    stickToBottomRef.current = distanceFromBottom <= SCROLL_THRESHOLD
    setShowScrollBtn(distanceFromBottom > SCROLL_THRESHOLD)
  }, [])

  useEffect(() => {
    if (!stickToBottomRef.current) return
    const el = containerRef.current
    if (!el) return
    programmaticScrollRef.current = true
    el.scrollTop = el.scrollHeight
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        programmaticScrollRef.current = false
      })
    })
  }, [messages, streamingContent])

  useEffect(() => {
    if (status !== 'streaming') {
      setShowScrollBtn(false)
    }
  }, [status])

  const scrollToBottom = useCallback(() => {
    stickToBottomRef.current = true
    setShowScrollBtn(false)
    const el = containerRef.current
    if (el) {
      programmaticScrollRef.current = true
      el.scrollTop = el.scrollHeight
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          programmaticScrollRef.current = false
        })
      })
    }
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
        <button className="scroll-to-bottom-btn" onClick={scrollToBottom} title={t('chat.scrollToBottom', 'Scroll to bottom')}>
          <ArrowDown size={18} />
        </button>
      )}

      <ChatInput onSend={handleSend} onCancel={onCancel} status={status} editValue={editValue} onUploadClick={onUploadClick} />
    </div>
  )
}
