import { Bot, User } from 'lucide-react'
import type { ChatMessage as ChatMessageType, SourceInfo } from '../types'
import { MarkdownRenderer } from './MarkdownRenderer'
import { SourceCard } from './SourceCard'

interface Props {
  message: ChatMessageType
  isStreaming?: boolean
  streamingContent?: string
  streamingSources?: SourceInfo[]
}

export function ChatMessageComponent({ message, isStreaming, streamingContent, streamingSources }: Props) {
  const content = isStreaming ? (streamingContent || '') : message.content
  const sources = isStreaming ? (streamingSources || []) : (message.sources || [])
  const isUser = message.role === 'user'

  return (
    <div className={`message ${message.role}`}>
      <div className="message-avatar">
        {isUser ? <User size={16} /> : <Bot size={16} />}
      </div>
      <div className="message-body">
        <div className={`message-content ${isStreaming ? 'streaming-cursor' : ''}`}>
          {isUser ? content : <MarkdownRenderer content={content} />}
        </div>
        {sources.length > 0 && (
          <div className="sources-container">
            {sources.map((s, i) => (
              <SourceCard key={i} source={s} />
            ))}
          </div>
        )}
        {!isStreaming && message.duration_ms && (
          <div className="message-duration">
            {(message.duration_ms / 1000).toFixed(1)}s
          </div>
        )}
      </div>
    </div>
  )
}
