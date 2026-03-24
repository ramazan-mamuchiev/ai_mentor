import { useTranslation } from 'react-i18next'

export function LanguageToggle() {
  const { i18n, t } = useTranslation()
  const current = i18n.language?.startsWith('ru') ? 'ru' : 'en'
  const next = current === 'ru' ? 'en' : 'ru'

  return (
    <button
      className="lang-toggle"
      onClick={() => i18n.changeLanguage(next)}
      data-tooltip={t('lang.toggle')}
    >
      {current.toUpperCase()}
    </button>
  )
}
