import { Moon, Sun } from 'lucide-react'
import { useTranslation } from 'react-i18next'

interface Props {
  theme: 'light' | 'dark'
  onToggle: () => void
}

export function ThemeToggle({ theme, onToggle }: Props) {
  const { t } = useTranslation()
  return (
    <button className="theme-toggle" onClick={onToggle} data-tooltip={t('theme.toggle')}>
      {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
    </button>
  )
}
