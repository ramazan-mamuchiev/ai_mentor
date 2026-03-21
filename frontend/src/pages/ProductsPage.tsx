import { Box } from 'lucide-react'
import { useTranslation } from 'react-i18next'

export function ProductsPage() {
  const { t } = useTranslation()

  return (
    <div className="stub-page">
      <Box size={48} className="stub-icon" />
      <h1 className="stub-title">{t('products.title')}</h1>
      <p className="stub-description">{t('products.description')}</p>
      <span className="stub-badge">{t('products.comingSoon')}</span>
    </div>
  )
}
