import { useState } from 'react'
import { Bot, Bug, ChevronDown, ChevronUp, Loader2, User } from 'lucide-react'
import type { ChatMessage as ChatMessageType, DebugInfo, SourceInfo } from '../types'
import { MarkdownRenderer } from './MarkdownRenderer'
import { SourceCard } from './SourceCard'

function DebugPanel({ debug }: { debug: DebugInfo }) {
  return (
    <div className="debug-panel">
      <div className="debug-grid">
        <div className="debug-section">
          <div className="debug-section-title">Identifiers</div>
          <div className="debug-row"><span>Session</span><code>#{debug.session_id}</code></div>
          <div className="debug-row"><span>Message</span><code>#{debug.message_id}</code></div>
          <div className="debug-row"><span>User Msg</span><code>#{debug.user_message_id}</code></div>
        </div>
        <div className="debug-section">
          <div className="debug-section-title">LLM</div>
          <div className="debug-row"><span>Model</span><code>{debug.model}</code></div>
          <div className="debug-row"><span>Tokens</span><code>{debug.token_count}</code></div>
          <div className="debug-row"><span>Speed</span><code>{debug.tokens_per_sec} tok/s</code></div>
          <div className="debug-row"><span>Response</span><code>{debug.response_length} chars</code></div>
        </div>
        <div className="debug-section">
          <div className="debug-section-title">Timing</div>
          <div className="debug-row"><span>Total</span><code>{(debug.total_ms / 1000).toFixed(1)}s</code></div>
          <div className="debug-row"><span>RAG</span><code>{(debug.rag_ms / 1000).toFixed(1)}s</code></div>
          <div className="debug-row"><span>LLM</span><code>{(debug.llm_ms / 1000).toFixed(1)}s</code></div>
          <div className="debug-row"><span>Search</span><code>{(debug.search_ms / 1000).toFixed(1)}s</code></div>
        </div>
        <div className="debug-section">
          <div className="debug-section-title">RAG</div>
          <div className="debug-row"><span>Chunks</span><code>{debug.chunks_found}</code></div>
          <div className="debug-row"><span>Top sim</span><code>{(debug.top_similarity * 100).toFixed(1)}%</code></div>
          <div className="debug-row"><span>Min sim</span><code>{(debug.min_similarity * 100).toFixed(1)}%</code></div>
          <div className="debug-row"><span>Ctx tokens</span><code>{debug.context_tokens}</code></div>
          <div className="debug-row"><span>Embed</span><code className="debug-embed">{debug.embedding_model}</code></div>
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
}

export function ChatMessageComponent({ message, isStreaming, streamingContent, streamingSources }: Props) {
  const content = isStreaming ? (streamingContent || '') : message.content
  const sources = isStreaming ? (streamingSources || []) : (message.sources || [])
  const isUser = message.role === 'user'
  const isWaiting = isStreaming && !content
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
          {isUser ? (
            content
          ) : isWaiting ? (
            <div className="typing-indicator">
              <Loader2 size={14} className="typing-spinner" />
              <span>Searching documentation & generating response...</span>
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
              <span className="sources-label">Sources ({sources.length})</span>
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
                  title="Debug info"
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
