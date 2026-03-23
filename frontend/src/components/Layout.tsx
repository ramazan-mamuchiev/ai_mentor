import { type ReactNode, useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import {
  MessageSquare, FileText, Box, BarChart3, Settings,
  PanelLeftClose, PanelLeftOpen, X,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { ChatSession } from '../types'
import { LanguageToggle } from './LanguageToggle'
import { SessionList } from './SessionList'
import { ThemeToggle } from './ThemeToggle'

const ChatGptSidebarIcon = ({ size = 20 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
    <path d="M3 8C3 7.44772 3.44772 7 4 7H20C20.5523 7 21 7.44772 21 8C21 8.55228 20.5523 9 20 9H4C3.44772 9 3 8.55228 3 8ZM3 16C3 15.4477 3.44772 15 4 15H14C14.5523 15 15 15.4477 15 16C15 16.5523 14.5523 17 14 17H4C3.44772 17 3 16.5523 3 16Z" />
  </svg>
)

const MOBILE_BP = 768

function useIsMobile() {
  const [mobile, setMobile] = useState(
    () => typeof window !== 'undefined' && window.innerWidth < MOBILE_BP,
  )
  useEffect(() => {
    const mq = window.matchMedia(`(max-width: ${MOBILE_BP - 1}px)`)
    const handler = (e: MediaQueryListEvent) => setMobile(e.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])
  return mobile
}

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
  try { return localStorage.getItem(COLLAPSED_KEY) === 'true' } catch { return false }
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
  const [mobileOpen, setMobileOpen] = useState(false)
  const isMobile = useIsMobile()
  const dragging = useRef(false)
  const startX = useRef(0)
  const startWidth = useRef(0)
  const navigate = useNavigate()
  const location = useLocation()

  const isChat = location.pathname === '/app' || location.pathname === '/app/'

  useEffect(() => { if (!isMobile) setMobileOpen(false) }, [isMobile])
  useEffect(() => { setMobileOpen(false) }, [location.pathname])

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

  const sidebarCls = [
    'sidebar',
    collapsed && !isMobile ? 'sidebar--collapsed' : '',
    isMobile ? 'sidebar--mobile' : '',
    isMobile && mobileOpen ? 'sidebar--mobile-open' : '',
  ].filter(Boolean).join(' ')

  const sidebarStyle = isMobile
    ? { width: DEFAULT_WIDTH, minWidth: DEFAULT_WIDTH }
    : { width: effectiveWidth, minWidth: effectiveWidth }

  return (
    <div className="app-layout">
      {isMobile && mobileOpen && (
        <div className="sidebar-backdrop" onClick={() => setMobileOpen(false)} />
      )}
      <aside className={sidebarCls} style={sidebarStyle}>
        <div className="sidebar-header">
          {(!collapsed || isMobile) && (
            <div className="sidebar-header-left">
              <img src="/logo-on-light.svg" alt={t('sidebar.title')} className="sidebar-icon logo-light" />
              <img src="/logo-on-dark.svg" alt={t('sidebar.title')} className="sidebar-icon logo-dark" />
              <span className="sidebar-title">{t('sidebar.title')}</span>
            </div>
          )}
          {isMobile ? (
            <button
              className="sidebar-toggle-btn"
              onClick={() => setMobileOpen(false)}
              aria-label={t('sidebar.collapse')}
            >
              <X size={18} />
            </button>
          ) : (
            <button
              className="sidebar-toggle-btn"
              onClick={toggleCollapsed}
              aria-label={collapsed ? t('sidebar.expand') : t('sidebar.collapse')}
            >
              {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
            </button>
          )}
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
                title={collapsed && !isMobile ? t(item.labelKey) : undefined}
              >
                <Icon size={18} />
                {(!collapsed || isMobile) && t(item.labelKey)}
              </button>
            )
          })}
        </nav>

        {(!collapsed || isMobile) && isChat ? (
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
      {!isMobile && !collapsed && (
        <div
          className="splitter"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
        />
      )}
      <div className="main-content">
        {isMobile && (
          <div className="mobile-topbar">
            <button
              className="mobile-menu-btn"
              onClick={() => setMobileOpen(true)}
              aria-label="Menu"
            >
              <ChatGptSidebarIcon size={20} />
            </button>
            <div className="mobile-topbar-brand">
              <img src="/logo-on-light.svg" alt="" className="mobile-topbar-logo logo-light" />
              <img src="/logo-on-dark.svg" alt="" className="mobile-topbar-logo logo-dark" />
              <span className="mobile-topbar-title">{t('sidebar.title')}</span>
            </div>
          </div>
        )}
        {children}
      </div>
    </div>
  )
}
