import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { LogOut, Key, ChevronUp, Moon, Sun, Languages } from 'lucide-react'
import { useAuth } from '../auth/AuthContext'
import { useTranslation } from 'react-i18next'

function getInitials(email: string, name?: string | null): string {
  if (name) {
    return name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2)
  }
  const local = email.split('@')[0]
  return local.slice(0, 2).toUpperCase()
}

interface AccountBadgeProps {
  collapsed: boolean
  theme: 'light' | 'dark'
  onToggleTheme: () => void
}

export function AccountBadge({ collapsed, theme, onToggleTheme }: AccountBadgeProps) {
  const { user, logout } = useAuth()
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  if (!user) return null

  const initials = getInitials(user.email, user.name)
  const currentLang = i18n.language?.startsWith('ru') ? 'ru' : 'en'
  const nextLang = currentLang === 'ru' ? 'en' : 'ru'
  const langLabel = currentLang === 'ru' ? 'English' : 'Русский'

  return (
    <div className="account-badge" ref={ref}>
      <button
        className="account-badge-btn"
        onClick={() => setOpen(!open)}
        data-tooltip={collapsed ? user.email : undefined}
      >
        <span className="account-avatar">{initials}</span>
        {!collapsed && (
          <>
            <span className="account-info">
              <span className="account-email">{user.email}</span>
              <span className="account-tier">{user.tier}</span>
            </span>
            <ChevronUp size={14} className={`account-chevron ${open ? 'open' : ''}`} />
          </>
        )}
      </button>

      {open && (
        <div className="account-dropdown">
          <button onClick={() => { navigate('/app/settings'); setOpen(false) }}>
            <Key size={16} />
            {t('auth.apiKeys')}
          </button>
          <div className="account-dropdown-divider" />
          <button onClick={() => { onToggleTheme(); setOpen(false) }}>
            {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
            {theme === 'dark' ? t('theme.light') : t('theme.dark')}
          </button>
          <button onClick={() => { i18n.changeLanguage(nextLang); setOpen(false) }}>
            <Languages size={16} />
            {langLabel}
          </button>
          <div className="account-dropdown-divider" />
          <button onClick={() => { logout(); setOpen(false) }}>
            <LogOut size={16} />
            {t('auth.signOut')}
          </button>
        </div>
      )}
    </div>
  )
}
