import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { LogIn, Moon, Sun, Globe } from 'lucide-react'
import { useTheme } from '../hooks/useTheme'

export function PublicKBLayout({ children }: { children: ReactNode }) {
  const navigate = useNavigate()
  const { t, i18n } = useTranslation()
  const { theme, toggle: toggleTheme } = useTheme()
  const lang = i18n.language?.startsWith('ru') ? 'ru' : 'en'

  const toggleLang = () => {
    i18n.changeLanguage(lang === 'ru' ? 'en' : 'ru')
  }

  return (
    <div className="public-kb-layout">
      <header className="public-kb-header">
        <div className="public-kb-header-left" onClick={() => navigate('/')} role="button" style={{ cursor: 'pointer' }}>
          <img src="/logo-on-light.svg" alt="AI Mentor" className="public-kb-logo logo-light" />
          <img src="/logo-on-dark.svg" alt="AI Mentor" className="public-kb-logo logo-dark" />
          <span className="public-kb-brand">AI Mentor</span>
        </div>
        <div className="public-kb-header-actions">
          <button className="public-kb-btn" onClick={toggleLang} title={lang === 'ru' ? 'English' : 'Русский'}>
            <Globe size={16} />
            <span>{lang === 'ru' ? 'EN' : 'RU'}</span>
          </button>
          <button className="public-kb-btn" onClick={toggleTheme} title={theme === 'dark' ? 'Light' : 'Dark'}>
            {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
          </button>
          <button className="public-kb-btn public-kb-btn--primary" onClick={() => navigate('/login')}>
            <LogIn size={16} />
            <span>{t('kb.signIn')}</span>
          </button>
        </div>
      </header>
      <main className="public-kb-main">
        {children}
      </main>
    </div>
  )
}
