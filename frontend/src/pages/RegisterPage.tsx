import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { useTranslation } from 'react-i18next'
import { Eye, EyeOff, Moon, Sun } from 'lucide-react'
import { useTheme } from '../hooks/useTheme'

export function RegisterPage() {
  const { register } = useAuth()
  const navigate = useNavigate()
  const { t, i18n } = useTranslation()
  const { theme, toggle: toggleTheme } = useTheme()
  const currentLang = i18n.language?.startsWith('ru') ? 'ru' : 'en'
  const nextLang = currentLang === 'ru' ? 'en' : 'ru'

  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await register(email, password, name || undefined)
      navigate('/app?onboarding=true')
    } catch (err: any) {
      setError(err.message || t('auth.registerError'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-header-actions">
        <button className="lang-toggle" onClick={() => i18n.changeLanguage(nextLang)} aria-label={t('lang.toggle')}>
          {currentLang.toUpperCase()}
        </button>
        <button className="theme-toggle" onClick={toggleTheme} aria-label={t('theme.toggle')}>
          {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
        </button>
      </div>
      <div className="auth-card">
        <div className="auth-logo">
          <img src="/logo-on-light.svg" alt="Lexiro" className="logo-light" />
          <img src="/logo-on-dark.svg" alt="Lexiro" className="logo-dark" />
          <div className="auth-brand-name">Lexiro</div>
        </div>
        <h1 className="auth-title">{t('auth.createAccount')}</h1>
        <p className="auth-subtitle">{t('auth.registerSubtitle')}</p>

        <form onSubmit={handleSubmit} className="auth-form">
          {error && <div className="auth-error">{error}</div>}
          <div className="auth-field">
            <label className="auth-label" htmlFor="register-name">{t('auth.nameLabel')}</label>
            <input
              id="register-name"
              type="text"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder={t('auth.namePlaceholder')}
              className="auth-input"
              autoComplete="name"
              maxLength={128}
            />
          </div>
          <div className="auth-field">
            <label className="auth-label" htmlFor="register-email">{t('auth.emailLabel')}</label>
            <input
              id="register-email"
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="you@axxonsoft.dev"
              required
              className="auth-input"
              autoComplete="email"
            />
            <span className="auth-hint">{t('auth.emailDomainHint')}</span>
          </div>
          <div className="auth-field">
            <label className="auth-label" htmlFor="register-password">{t('auth.passwordLabel')}</label>
            <div className="auth-input-wrapper">
              <input
                id="register-password"
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder={t('auth.passwordPlaceholder')}
                required
                minLength={8}
                className="auth-input"
                autoComplete="new-password"
              />
              <button
                type="button"
                className="auth-password-toggle"
                onClick={() => setShowPassword(v => !v)}
                tabIndex={-1}
                aria-label={showPassword ? t('auth.hidePassword') : t('auth.showPassword')}
              >
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </div>
          <button type="submit" className="auth-submit" disabled={loading}>
            {loading ? t('auth.creating') : t('auth.createAccount')}
          </button>
        </form>

        <p className="auth-footer">
          {t('auth.haveAccount')} <Link to="/login">{t('auth.signIn')}</Link>
        </p>
      </div>
    </div>
  )
}
