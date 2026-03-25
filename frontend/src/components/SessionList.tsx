import { useCallback, useEffect, useRef, useState } from 'react'
import { MoreHorizontal, Pencil, Trash2, SquarePen, Box, Globe } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { ChatSession } from '../types'

interface Props {
  sessions: ChatSession[]
  activeSessionId: number | null
  onSelect: (id: number) => void
  onNew: () => void
  onDelete: (id: number) => void
}

export function SessionList({ sessions, activeSessionId, onSelect, onNew, onDelete }: Props) {
  const { t } = useTranslation()
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
      <button className="session-new-chat" onClick={onNew}>
        <SquarePen size={16} />
        {t('sidebar.newChat')}
      </button>
      {sessions.map(s => {
        const isActive = s.id === activeSessionId
        const isMenuOpen = menuOpenId === s.id
        return (
          <div
            key={s.id}
            className={`session-item${isActive ? ' active' : ''}${isMenuOpen ? ' menu-open' : ''}`}
            onClick={() => onSelect(s.id)}
          >
            <div className="session-item-content">
              <span className="session-item-title">
                {s.title || s.last_message_preview || t('session.newChat')}
              </span>
              <span className="session-product-tag">
                {s.product_filter ? (
                  <><Box size={11} />{s.product_filter}</>
                ) : (
                  <><Globe size={11} />{t('session.allProducts')}</>
                )}
              </span>
            </div>
            <div className="session-item-actions" ref={isMenuOpen ? menuRef : undefined}>
              <button
                className="session-menu-btn"
                onClick={e => {
                  e.stopPropagation()
                  setMenuOpenId(isMenuOpen ? null : s.id)
                }}
                aria-label={t('session.options')}
                data-tooltip={t('session.options')}
                data-tooltip-align="right"
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
                    {t('session.rename')}
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
                    {t('session.delete')}
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
