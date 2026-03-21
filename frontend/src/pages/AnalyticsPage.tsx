import { BarChart3 } from 'lucide-react'
import { useTranslation } from 'react-i18next'

export function AnalyticsPage() {
  const { t } = useTranslation()

  return (
    <div className="stub-page">
      <BarChart3 size={48} className="stub-icon" />
      <h1 className="stub-title">{t('analytics.title')}</h1>
      <p className="stub-description">{t('analytics.description')}</p>
      <span className="stub-badge">{t('analytics.comingSoon')}</span>
    </div>
  )
}
