import { useCallback, useEffect, useRef } from 'react'
import { Bot } from 'lucide-react'
import type { SourceInfo, StreamStatus } from '../types'
import type { ChatMessage as ChatMessageType } from '../types'
import { ChatMessageComponent } from './ChatMessage'
import { ChatInput } from './ChatInput'

interface Props {
  messages: ChatMessageType[]
  streamingContent: string
  streamingSources: SourceInfo[]
  status: StreamStatus
  sessionTitle: string | null
  onSend: (content: string) => void
  onCancel: () => void
}

export function ChatWindow({
  messages,
  streamingContent,
  streamingSources,
  status,
  sessionTitle,
  onSend,
  onCancel,
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingContent])

  const handleSend = useCallback(
    (content: string) => onSend(content),
    [onSend],
  )

  const isEmpty = messages.length === 0 && !streamingContent

  return (
    <div className="main-area">
      <div className="chat-header">
        <span className="chat-header-title">{sessionTitle || 'New Chat'}</span>
      </div>

      <div className="messages-container">
        {isEmpty ? (
          <div className="messages-empty">
            <Bot size={48} strokeWidth={1.5} />
            <div className="messages-empty-title">IPCodex AI</div>
            <div className="messages-empty-subtitle">
              Ask me anything about device integration, API documentation,
              protocols, and configuration. I'll search through your uploaded
              documentation to find the answer.
            </div>
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

      <ChatInput onSend={handleSend} onCancel={onCancel} status={status} />
    </div>
  )
}
