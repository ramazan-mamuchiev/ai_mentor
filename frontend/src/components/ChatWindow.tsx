import { useCallback, useEffect, useRef } from 'react'
import type { SourceInfo, StreamStatus } from '../types'
import type { ChatMessage as ChatMessageType } from '../types'
import { ChatMessageComponent } from './ChatMessage'
import { ChatInput } from './ChatInput'

const SCROLL_THRESHOLD = 80

interface Props {
  messages: ChatMessageType[]
  streamingContent: string
  streamingSources: SourceInfo[]
  status: StreamStatus
  sessionTitle: string | null
  onSend: (content: string) => void
  onCancel: () => void
  editValue?: string
}

export function ChatWindow({
  messages,
  streamingContent,
  streamingSources,
  status,
  sessionTitle,
  onSend,
  onCancel,
  editValue,
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const stickToBottomRef = useRef(true)

  const handleScroll = useCallback(() => {
    const el = containerRef.current
    if (!el) return
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    stickToBottomRef.current = distanceFromBottom <= SCROLL_THRESHOLD
  }, [])

  useEffect(() => {
    if (stickToBottomRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages, streamingContent])

  const handleSend = useCallback(
    (content: string) => {
      stickToBottomRef.current = true
      onSend(content)
    },
    [onSend],
  )

  const isEmpty = messages.length === 0 && !streamingContent

  return (
    <div className="main-area">
      <div className="chat-header">
        <span className="chat-header-title">{sessionTitle || 'IPCodex'}</span>
      </div>

      <div className="messages-container" ref={containerRef} onScroll={handleScroll}>
        {isEmpty ? (
          <div className="messages-empty">
            <div className="messages-empty-title">What can I help with?</div>
          </div>
        ) : (
          <>
            {messages.map(msg => (
              <ChatMessageComponent key={msg.id} message={msg} />
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

      <ChatInput onSend={handleSend} onCancel={onCancel} status={status} editValue={editValue} />
    </div>
  )
}
