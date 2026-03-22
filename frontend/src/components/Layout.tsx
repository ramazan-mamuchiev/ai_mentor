import { type ReactNode, useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import {
  MessageSquare, FileText, Box, BarChart3, Settings,
  PanelLeftClose, PanelLeftOpen,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { ChatSession } from '../types'
import { LanguageToggle } from './LanguageToggle'
import { SessionList } from './SessionList'
import { ThemeToggle } from './ThemeToggle'

const WIDTH_KEY = 'ipcodex-sidebar-width'
const COLLAPSED_KEY = 'ipcodex-sidebar-collapsed'
const DEFAULT_WIDTH = 280
const MIN_WIDTH = 180
const MAX_WIDTH = 600
const COLLAPSED_WIDTH = 56

function loadWidth(): number {
  try {
    const stored = localStorage.getItem(WIDTH_KEY)
    if (stored) {
      const n = parseInt(stored, 10)
      if (!isNaN(n) && n >= MIN_WIDTH && n <= MAX_WIDTH) return n
    }
  } catch { /* ignore */ }
  return DEFAULT_WIDTH
}

function loadCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSED_KEY) === 'true'
  } catch { return false }
}

const NAV_ITEMS = [
  { path: '/app', icon: MessageSquare, labelKey: 'nav.chat' },
  { path: '/app/documents', icon: FileText, labelKey: 'nav.documents' },
  { path: '/app/products', icon: Box, labelKey: 'nav.products' },
  { path: '/app/analytics', icon: BarChart3, labelKey: 'nav.analytics' },
  { path: '/app/settings', icon: Settings, labelKey: 'nav.settings' },
] as const

interface Props {
  sessions: ChatSession[]
  activeSessionId: number | null
  theme: 'light' | 'dark'
  onSelectSession: (id: number) => void
  onNewSession: () => void
  onDeleteSession: (id: number) => void
  onToggleTheme: () => void
  children: ReactNode
}

export function Layout({
  sessions,
  activeSessionId,
  theme,
  onSelectSession,
  onNewSession,
  onDeleteSession,
  onToggleTheme,
  children,
}: Props) {
  const [sidebarWidth, setSidebarWidth] = useState(loadWidth)
  const [collapsed, setCollapsed] = useState(loadCollapsed)
  const dragging = useRef(false)
  const startX = useRef(0)
  const startWidth = useRef(0)
  const navigate = useNavigate()
  const location = useLocation()

  const isChat = location.pathname === '/app' || location.pathname === '/app/'

  const toggleCollapsed = useCallback(() => {
    setCollapsed(prev => {
      const next = !prev
      try { localStorage.setItem(COLLAPSED_KEY, String(next)) } catch { /* ignore */ }
      return next
    })
  }, [])

  const onPointerDown = useCallback((e: React.PointerEvent) => {
    if (collapsed) return
    e.preventDefault()
    dragging.current = true
    startX.current = e.clientX
    startWidth.current = sidebarWidth
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
    const target = e.target as HTMLElement
    target.setPointerCapture?.(e.pointerId)
  }, [sidebarWidth, collapsed])

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    if (!dragging.current) return
    const delta = e.clientX - startX.current
    const next = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, startWidth.current + delta))
    setSidebarWidth(next)
  }, [])

  const onPointerUp = useCallback(() => {
    if (!dragging.current) return
    dragging.current = false
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
  }, [])

  useEffect(() => {
    if (!collapsed) {
      try { localStorage.setItem(WIDTH_KEY, String(sidebarWidth)) } catch { /* ignore */ }
    }
  }, [sidebarWidth, collapsed])

  const { t } = useTranslation()

  const effectiveWidth = collapsed ? COLLAPSED_WIDTH : sidebarWidth

  return (
    <div className="app-layout">
      <aside
        className={`sidebar${collapsed ? ' sidebar--collapsed' : ''}`}
        style={{ width: effectiveWidth, minWidth: effectiveWidth }}
      >
        <div className="sidebar-header">
          {!collapsed && (
            <div className="sidebar-header-left">
              <img src="/logo-on-light.svg" alt={t('sidebar.title')} className="sidebar-icon logo-light" />
              <img src="/logo-on-dark.svg" alt={t('sidebar.title')} className="sidebar-icon logo-dark" />
              <span className="sidebar-title">{t('sidebar.title')}</span>
            </div>
          )}
          <button
            className="sidebar-toggle-btn"
            onClick={toggleCollapsed}
            aria-label={collapsed ? t('sidebar.expand') : t('sidebar.collapse')}
          >
            {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
          </button>
        </div>

        <nav className="sidebar-nav">
          {NAV_ITEMS.map(item => {
            const Icon = item.icon
            const active = item.path === '/app'
              ? isChat
              : location.pathname.startsWith(item.path)
            return (
              <button
                key={item.path}
                className={`nav-item${active ? ' nav-item--active' : ''}`}
                onClick={() => navigate(item.path)}
                title={collapsed ? t(item.labelKey) : undefined}
              >
                <Icon size={18} />
                {!collapsed && t(item.labelKey)}
              </button>
            )
          })}
        </nav>

        {!collapsed && isChat ? (
          <SessionList
            sessions={sessions}
            activeSessionId={activeSessionId}
            onSelect={onSelectSession}
            onNew={onNewSession}
            onDelete={onDeleteSession}
          />
        ) : (
          <div className="sidebar-spacer" />
        )}

        <div className="sidebar-footer">
          <LanguageToggle />
          <ThemeToggle theme={theme} onToggle={onToggleTheme} />
        </div>
      </aside>
      {!collapsed && (
        <div
          className="splitter"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
        />
      )}
      {children}
    </div>
  )
}
