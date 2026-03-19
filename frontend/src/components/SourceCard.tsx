import { useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { SourceInfo } from '../types'

interface Props {
  source: SourceInfo
}

export function SourceCard({ source }: Props) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(false)

  return (
    <div className={`source-card ${expanded ? 'expanded' : ''}`}>
      <div className="source-card-header" onClick={() => setExpanded(prev => !prev)}>
        <div className="source-card-info">
          <div className="source-card-title">{source.doc_title}</div>
          <div className="source-card-path">{source.heading_path}</div>
          <div className="source-card-score">
            {source.product_name && `${source.product_name} · `}
            {t('match', { value: (source.similarity * 100).toFixed(1) })}
          </div>
        </div>
        <div className="source-card-toggle">
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </div>
      </div>
      {expanded && source.content_preview && (
        <div className="source-card-preview">{source.content_preview}</div>
      )}
    </div>
  )
}
