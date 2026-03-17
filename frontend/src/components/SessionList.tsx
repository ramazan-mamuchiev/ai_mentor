import { MessageSquare, Plus, Trash2 } from 'lucide-react'
import type { ChatSession } from '../types'

interface Props {
  sessions: ChatSession[]
  activeSessionId: number | null
  onSelect: (id: number) => void
  onNew: () => void
  onDelete: (id: number) => void
}

export function SessionList({ sessions, activeSessionId, onSelect, onNew, onDelete }: Props) {
  return (
    <>
      <button className="new-chat-btn" onClick={onNew}>
        <Plus size={16} />
        New Chat
      </button>
      <div className="session-list">
        {sessions.map(s => (
          <div
            key={s.id}
            className={`session-item ${s.id === activeSessionId ? 'active' : ''}`}
            onClick={() => onSelect(s.id)}
          >
            <MessageSquare size={14} />
            <span className="session-item-title">
              {s.title || s.last_message_preview || 'New Chat'}
            </span>
            <button
              className="session-delete-btn"
              onClick={e => {
                e.stopPropagation()
                onDelete(s.id)
              }}
            >
              <Trash2 size={14} />
            </button>
          </div>
        ))}
      </div>
    </>
  )
}
