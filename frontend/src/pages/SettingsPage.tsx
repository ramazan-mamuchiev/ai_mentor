import { Settings } from 'lucide-react'
import { useTranslation } from 'react-i18next'

export function SettingsPage() {
  const { t } = useTranslation()

  return (
    <div className="stub-page">
      <Settings size={48} className="stub-icon" />
      <h1 className="stub-title">{t('settings.title')}</h1>
      <p className="stub-description">{t('settings.description')}</p>
      <span className="stub-badge">{t('settings.comingSoon')}</span>
    </div>
  )
}
