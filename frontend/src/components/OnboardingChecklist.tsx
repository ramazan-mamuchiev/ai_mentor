import { useState, useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Check, Upload, Key, MessageSquare, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../auth/AuthContext'

const ONBOARDING_KEY = 'ai-mentor-onboarding-dismissed'

export function OnboardingChecklist() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const isOnboarding = searchParams.get('onboarding') === 'true'
    const dismissed = localStorage.getItem(ONBOARDING_KEY)
    if (isOnboarding && !dismissed) {
      setVisible(true)
      const next = new URLSearchParams(searchParams)
      next.delete('onboarding')
      setSearchParams(next, { replace: true })
    }
  }, [searchParams, setSearchParams])

  const dismiss = () => {
    setVisible(false)
    localStorage.setItem(ONBOARDING_KEY, 'true')
  }

  if (!visible || !user) return null

  const steps = [
    {
      icon: Check,
      done: true,
      label: t('onboarding.step1'),
    },
    {
      icon: Key,
      done: false,
      label: t('onboarding.step2'),
      action: () => { dismiss(); navigate('/app/settings') },
    },
    {
      icon: Upload,
      done: false,
      label: t('onboarding.step3'),
      action: () => { dismiss(); navigate('/app/products') },
    },
    {
      icon: MessageSquare,
      done: false,
      label: t('onboarding.step4'),
      action: () => dismiss(),
    },
  ]

  return (
    <div className="onboarding-overlay">
      <div className="onboarding-card">
        <div className="onboarding-header">
          <h2>{t('onboarding.title')}</h2>
          <button className="btn-icon" onClick={dismiss}><X size={20} /></button>
        </div>
        <p className="onboarding-subtitle">{t('onboarding.subtitle', { email: user.email })}</p>

        <div className="onboarding-steps">
          {steps.map((step, i) => (
            <div
              key={i}
              className={`onboarding-step ${step.done ? 'done' : ''} ${step.action ? 'clickable' : ''}`}
              onClick={step.action}
            >
              <span className="onboarding-step-icon">
                {step.done ? <Check size={18} /> : <step.icon size={18} />}
              </span>
              <span className="onboarding-step-label">{step.label}</span>
            </div>
          ))}
        </div>

        <button className="auth-submit" onClick={dismiss} style={{ marginTop: '1rem' }}>
          {t('onboarding.dismiss')}
        </button>
      </div>
    </div>
  )
}
