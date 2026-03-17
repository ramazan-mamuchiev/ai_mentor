import type { ReactNode } from 'react'
import type { ChatSession } from '../types'
import { SessionList } from './SessionList'
import { ThemeToggle } from './ThemeToggle'

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
  return (
    <div className="app-layout">
      <aside className="sidebar">
        <div className="sidebar-header">
          <span className="sidebar-title">IPCodex</span>
        </div>
        <SessionList
          sessions={sessions}
          activeSessionId={activeSessionId}
          onSelect={onSelectSession}
          onNew={onNewSession}
          onDelete={onDeleteSession}
        />
        <div className="sidebar-footer">
          <ThemeToggle theme={theme} onToggle={onToggleTheme} />
        </div>
      </aside>
      {children}
    </div>
  )
}
