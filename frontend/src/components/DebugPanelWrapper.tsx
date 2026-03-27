import type { ReactNode } from 'react'
import { X } from 'lucide-react'

interface Props {
  children: ReactNode
  onCollapse?: () => void
  className?: string
}

export function DebugPanelWrapper({ children, onCollapse, className }: Props) {
  return (
    <div className={`debug-panel-box ${className ?? ''}`}>
      {onCollapse && (
        <button className="debug-panel-close-btn" onClick={onCollapse}>
          <X size={14} />
        </button>
      )}
      {children}
    </div>
  )
}
