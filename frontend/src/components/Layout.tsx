import { type ReactNode, useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import {
  MessageSquare, Box, BarChart3, Settings, X, Shield,
  LayoutDashboard, Users, FileText, ScrollText, KeyRound, MessageSquareCode,
  ArrowLeft,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { ChatSession } from '../types'
import { useAuth } from '../auth/AuthContext'
import { AccountBadge } from './AccountBadge'
import { SessionList } from './SessionList'
import { SidebarMenuIcon, SidebarCollapseIcon, SidebarExpandIcon } from './icons'

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

const WIDTH_KEY = 'lexiro-sidebar-width'
const COLLAPSED_KEY = 'lexiro-sidebar-collapsed'
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
  { path: '/app/products', icon: Box, labelKey: 'nav.products' },
  { path: '/app/analytics', icon: BarChart3, labelKey: 'nav.analytics' },
  { path: '/app/settings', icon: Settings, labelKey: 'nav.settings' },
] as const

const ADMIN_NAV_ITEM = { path: '/app/admin', icon: Shield, labelKey: 'nav.admin' } as const

const ADMIN_SUB_NAV: readonly { path: string; icon: typeof LayoutDashboard; labelKey: string; exact?: boolean }[] = [
  { path: '/app/admin', icon: LayoutDashboard, labelKey: 'admin.nav.dashboard', exact: true },
  { path: '/app/admin/tenants', icon: Users, labelKey: 'admin.nav.tenants' },
  { path: '/app/admin/documents', icon: FileText, labelKey: 'admin.nav.documents' },
  { path: '/app/admin/chats', icon: MessageSquare, labelKey: 'admin.nav.chatAudit' },
  { path: '/app/admin/roles', icon: KeyRound, labelKey: 'admin.nav.roles' },
  { path: '/app/admin/prompts', icon: MessageSquareCode, labelKey: 'admin.nav.prompts' },
  { path: '/app/admin/logs', icon: ScrollText, labelKey: 'admin.nav.logs' },
  { path: '/app/admin/stats', icon: BarChart3, labelKey: 'admin.nav.stats' },
]

interface Props {
  sessions: ChatSession[]
  activeSessionId: string | null
  theme: 'light' | 'dark'
  onSelectSession: (id: string) => void
  onNewSession: () => void
  onDeleteSession: (id: string) => void
  onToggleTheme: () => void
  onLogoClick?: () => void
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
  onLogoClick,
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

  const { user } = useAuth()
  const isChat = location.pathname === '/app' || location.pathname === '/app/'
  const isAdmin = location.pathname.startsWith('/app/admin')

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
            <div className="sidebar-header-left" onClick={() => { onLogoClick?.(); navigate('/app') }} role="button" style={{ cursor: 'pointer' }}>
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
              {collapsed ? <SidebarExpandIcon size={18} /> : <SidebarCollapseIcon size={18} />}
            </button>
          )}
        </div>

        {isAdmin ? (
          <nav className="sidebar-nav sidebar-nav--admin">
            <button
              className="admin-back-btn"
              onClick={() => navigate('/app')}
            >
              <ArrowLeft size={16} />
              {(!collapsed || isMobile) && t('admin.nav.backToApp')}
            </button>
            <div className="nav-divider" />
            {ADMIN_SUB_NAV.map(item => {
              const Icon = item.icon
              const active = item.exact
                ? location.pathname === item.path || location.pathname === item.path + '/'
                : location.pathname.startsWith(item.path)
              return (
                <button
                  key={item.path}
                  className={`nav-item nav-item--sub${active ? ' nav-item--active' : ''}`}
                  onClick={() => navigate(item.path)}
                >
                  <Icon size={16} />
                  {(!collapsed || isMobile) && t(item.labelKey)}
                </button>
              )
            })}
          </nav>
        ) : (
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
                  onClick={() => { navigate(item.path); if (isMobile) setMobileOpen(false) }}
                >
                  <Icon size={18} />
                  {(!collapsed || isMobile) && t(item.labelKey)}
                </button>
              )
            })}
            {(user?.permissions as any)?.features?.admin && (() => {
              const Icon = ADMIN_NAV_ITEM.icon
              return (
                <button
                  className={`nav-item${isAdmin ? ' nav-item--active' : ''}`}
                  onClick={() => navigate(ADMIN_NAV_ITEM.path)}
                >
                  <Icon size={18} />
                  {(!collapsed || isMobile) && t(ADMIN_NAV_ITEM.labelKey)}
                </button>
              )
            })()}
          </nav>
        )}

        {(!collapsed || isMobile) && isChat && !isAdmin ? (
          <SessionList
            sessions={sessions}
            activeSessionId={activeSessionId}
            onSelect={(id) => { onSelectSession(id); if (isMobile) setMobileOpen(false) }}
            onNew={() => { onNewSession(); if (isMobile) setMobileOpen(false) }}
            onDelete={onDeleteSession}
          />
        ) : !isAdmin ? (
          <div className="sidebar-spacer" />
        ) : null}

        <div className="sidebar-footer">
          <AccountBadge collapsed={collapsed && !isMobile} theme={theme} onToggleTheme={onToggleTheme} />
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
              <SidebarMenuIcon size={20} />
            </button>
            <div className="mobile-topbar-brand" onClick={() => { onLogoClick?.(); navigate('/app') }} role="button" style={{ cursor: 'pointer' }}>
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
