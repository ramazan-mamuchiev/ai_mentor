import { useState } from 'react'
import { ChevronDown, ChevronUp, Eye } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { SourceInfo } from '../types'

interface Props {
  source: SourceInfo
  onPreview?: (documentId: number, title: string) => void
}

export function SourceCard({ source, onPreview }: Props) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(false)

  const canPreview = !!source.document_id && !!onPreview

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
        <div className="source-card-actions">
          {canPreview && (
            <button
              className="source-card-preview-btn"
              onClick={e => { e.stopPropagation(); onPreview!(source.document_id!, source.doc_title) }}
              data-tooltip={t('chat.sources.preview')}
            >
              <Eye size={14} />
            </button>
          )}
          <div className="source-card-toggle">
            {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </div>
        </div>
      </div>
      {expanded && source.content_preview && (
        <div className="source-card-preview">{source.content_preview}</div>
      )}
    </div>
  )
}
