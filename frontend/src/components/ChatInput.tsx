import { useCallback, useRef, useState } from 'react'
import { SendHorizontal, Square } from 'lucide-react'
import type { StreamStatus } from '../types'

interface Props {
  onSend: (content: string) => void
  onCancel: () => void
  status: StreamStatus
}

export function ChatInput({ onSend, onCancel, status }: Props) {
  const [value, setValue] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const handleSubmit = useCallback(() => {
    const trimmed = value.trim()
    if (!trimmed || status === 'streaming') return
    onSend(trimmed)
    setValue('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }, [value, status, onSend])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setValue(e.target.value)
    const el = e.target
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 200) + 'px'
  }

  return (
    <div className="chat-input-container">
      <div className="chat-input-wrapper">
        <textarea
          ref={textareaRef}
          className="chat-input"
          value={value}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          placeholder="Ask about device integration..."
          rows={1}
          disabled={status === 'streaming'}
        />
        {status === 'streaming' ? (
          <button className="chat-send-btn" onClick={onCancel} title="Stop generating">
            <Square size={18} />
          </button>
        ) : (
          <button
            className="chat-send-btn"
            onClick={handleSubmit}
            disabled={!value.trim()}
            title="Send message"
          >
            <SendHorizontal size={18} />
          </button>
        )}
      </div>
    </div>
  )
}
