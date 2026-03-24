import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowUp, Plus, Square } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { StreamStatus } from '../types'

interface Props {
  onSend: (content: string) => void
  onCancel: () => void
  status: StreamStatus
  editValue?: string
  onUploadClick?: () => void
}

export function ChatInput({ onSend, onCancel, status, editValue, onUploadClick }: Props) {
  const { t } = useTranslation()
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
        <button className="chat-attach-btn" data-tooltip={t('input.upload')} onClick={onUploadClick}>
          <Plus size={18} />
        </button>
        <textarea
          ref={textareaRef}
          className="chat-input"
          value={value}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          placeholder={t('input.placeholder')}
          rows={1}
        />
        {isStreaming ? (
          <button className="chat-send-btn active" onClick={onCancel} data-tooltip={t('input.stop')}>
            <Square size={16} />
          </button>
        ) : (
          <button
            className={`chat-send-btn${hasText ? ' active' : ''}`}
            onClick={handleSubmit}
            disabled={!hasText}
            data-tooltip={t('input.send')}
          >
            <ArrowUp size={18} />
          </button>
        )}
      </div>
    </div>
  )
}
