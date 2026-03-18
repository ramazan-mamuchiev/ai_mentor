import { useCallback, useEffect, useRef, useState } from 'react'
import { MoreHorizontal, Pencil, Trash2 } from 'lucide-react'
import type { ChatSession } from '../types'

interface Props {
  sessions: ChatSession[]
  activeSessionId: number | null
  onSelect: (id: number) => void
  onNew: () => void
  onDelete: (id: number) => void
}

export function SessionList({ sessions, activeSessionId, onSelect, onDelete }: Props) {
  const [menuOpenId, setMenuOpenId] = useState<number | null>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  const closeMenu = useCallback(() => setMenuOpenId(null), [])

  useEffect(() => {
    if (menuOpenId === null) return
    const handleClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        closeMenu()
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [menuOpenId, closeMenu])

  useEffect(() => {
    if (menuOpenId === null) return
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeMenu()
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [menuOpenId, closeMenu])

  return (
    <div className="session-list">
      {sessions.map(s => {
        const isActive = s.id === activeSessionId
        const isMenuOpen = menuOpenId === s.id
        return (
          <div
            key={s.id}
            className={`session-item${isActive ? ' active' : ''}${isMenuOpen ? ' menu-open' : ''}`}
            onClick={() => onSelect(s.id)}
          >
            <span className="session-item-title">
              {s.title || s.last_message_preview || 'New Chat'}
            </span>
            <div className="session-item-actions" ref={isMenuOpen ? menuRef : undefined}>
              <button
                className="session-menu-btn"
                onClick={e => {
                  e.stopPropagation()
                  setMenuOpenId(isMenuOpen ? null : s.id)
                }}
                aria-label="Session options"
              >
                <MoreHorizontal size={16} />
              </button>
              {isMenuOpen && (
                <div className="session-context-menu">
                  <button
                    className="session-context-menu-item"
                    onClick={e => {
                      e.stopPropagation()
                      closeMenu()
                    }}
                  >
                    <Pencil size={14} />
                    Rename
                  </button>
                  <div className="session-context-menu-divider" />
                  <button
                    className="session-context-menu-item danger"
                    onClick={e => {
                      e.stopPropagation()
                      onDelete(s.id)
                      closeMenu()
                    }}
                  >
                    <Trash2 size={14} />
                    Delete
                  </button>
                </div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
