import type { ReactNode } from 'react'
import { X } from 'lucide-react'
import { useTranslation } from 'react-i18next'

interface Props {
  children: ReactNode
  onCollapse?: () => void
  className?: string
}

export function DebugPanelWrapper({ children, onCollapse, className }: Props) {
  const { t } = useTranslation()
  return (
    <div className={`debug-panel-box ${className ?? ''}`}>
      {onCollapse && (
        <button className="debug-panel-close-btn" onClick={onCollapse} data-tooltip={t('docDebug.collapse')}>
          <X size={14} />
        </button>
      )}
      {children}
    </div>
  )
}
