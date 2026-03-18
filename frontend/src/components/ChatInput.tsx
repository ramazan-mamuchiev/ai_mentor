import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowUp, Plus, Square } from 'lucide-react'
import type { StreamStatus } from '../types'

interface Props {
  onSend: (content: string) => void
  onCancel: () => void
  status: StreamStatus
  editValue?: string
}

export function ChatInput({ onSend, onCancel, status, editValue }: Props) {
  const [value, setValue] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (editValue) {
      setValue(editValue)
      requestAnimationFrame(() => {
        const el = textareaRef.current
        if (el) {
          el.style.height = 'auto'
          el.style.height = Math.min(el.scrollHeight, 200) + 'px'
          el.focus()
          el.setSelectionRange(el.value.length, el.value.length)
        }
      })
    }
  }, [editValue])

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

  const hasText = value.trim().length > 0
  const isStreaming = status === 'streaming'

  return (
    <div className="chat-input-container">
      <div className="chat-input-wrapper">
        <button className="chat-attach-btn" title="Attach file">
          <Plus size={18} />
        </button>
        <textarea
          ref={textareaRef}
          className="chat-input"
          value={value}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          placeholder="Ask about product integration..."
          rows={1}
        />
        {isStreaming ? (
          <button className="chat-send-btn active" onClick={onCancel} title="Stop generating">
            <Square size={16} />
          </button>
        ) : (
          <button
            className={`chat-send-btn${hasText ? ' active' : ''}`}
            onClick={handleSubmit}
            disabled={!hasText}
            title="Send message"
          >
            <ArrowUp size={18} />
          </button>
        )}
      </div>
    </div>
  )
}
