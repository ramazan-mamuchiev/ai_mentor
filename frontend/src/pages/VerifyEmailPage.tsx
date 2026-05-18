import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { verifyEmail, resendVerification } from '../auth/api'
import { useTranslation } from 'react-i18next'
import { Mail, CheckCircle, AlertCircle, Moon, Sun } from 'lucide-react'
import { useTheme } from '../hooks/useTheme'

type VerifyState = 'pending' | 'verifying' | 'success' | 'error'

export function VerifyEmailPage() {
  const { user, logout, refreshUser } = useAuth()
  const navigate = useNavigate()
  const { t, i18n } = useTranslation()
  const { theme, toggle: toggleTheme } = useTheme()
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token')

  const currentLang = i18n.language?.startsWith('ru') ? 'ru' : 'en'
  const nextLang = currentLang === 'ru' ? 'en' : 'ru'

  const [state, setState] = useState<VerifyState>(token ? 'verifying' : 'pending')
  const [resent, setResent] = useState(false)
  const [resendLoading, setResendLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!token) return
    setState('verifying')
    verifyEmail(token)
      .then(async () => {
        setState('success')
        try { await refreshUser() } catch {}
        setTimeout(() => navigate('/app', { replace: true }), 2000)
      })
      .catch((err: any) => {
        setState('error')
        setError(err.message || t('verify.expired'))
      })
  }, [token, navigate, refreshUser, t])

  const handleResend = useCallback(async () => {
    setResendLoading(true)
    setResent(false)
    try {
      await resendVerification()
      setResent(true)
    } catch (err: any) {
      setError(err.message || '')
    } finally {
      setResendLoading(false)
    }
  }, [])

  const handleLogout = useCallback(async () => {
    await logout()
    navigate('/login', { replace: true })
  }, [logout, navigate])

  // If user already verified (e.g. navigated back), send to app
  useEffect(() => {
    if (user?.email_verified && state !== 'verifying') {
      navigate('/app', { replace: true })
    }
  }, [user, state, navigate])

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
      <div className="auth-card verify-card">
        <div className="auth-logo">
          <img src="/logo-on-light.svg" alt="AI Mentor" className="logo-light" />
          <img src="/logo-on-dark.svg" alt="AI Mentor" className="logo-dark" />
          <div className="auth-brand-name">AI Mentor</div>
        </div>

        {state === 'pending' && (
          <>
            <div className="verify-icon">
              <Mail size={48} />
            </div>
            <h1 className="auth-title">{t('verify.title')}</h1>
            <p className="auth-subtitle">
              {t('verify.subtitle', { email: user?.email || '' })}
            </p>
            {resent && <div className="verify-success-msg">{t('verify.resent')}</div>}
            {error && <div className="auth-error">{error}</div>}
            <button
              className="auth-submit"
              onClick={handleResend}
              disabled={resendLoading}
            >
              {resendLoading ? '...' : t('verify.resend')}
            </button>
            <button className="verify-logout-btn" onClick={handleLogout}>
              {t('verify.logout')}
            </button>
          </>
        )}

        {state === 'verifying' && (
          <>
            <div className="verify-icon">
              <div className="auth-loading-spinner" />
            </div>
            <h1 className="auth-title">{t('verify.verifying')}</h1>
          </>
        )}

        {state === 'success' && (
          <>
            <div className="verify-icon verify-icon--success">
              <CheckCircle size={48} />
            </div>
            <h1 className="auth-title">{t('verify.success')}</h1>
            <p className="auth-subtitle">{t('verify.redirecting')}</p>
          </>
        )}

        {state === 'error' && (
          <>
            <div className="verify-icon verify-icon--error">
              <AlertCircle size={48} />
            </div>
            <h1 className="auth-title">{t('verify.expired')}</h1>
            {error && <div className="auth-error">{error}</div>}
            {user && (
              <button
                className="auth-submit"
                onClick={handleResend}
                disabled={resendLoading}
              >
                {resendLoading ? '...' : t('verify.resend')}
              </button>
            )}
            <button className="verify-logout-btn" onClick={handleLogout}>
              {t('verify.logout')}
            </button>
          </>
        )}
      </div>
    </div>
  )
}
