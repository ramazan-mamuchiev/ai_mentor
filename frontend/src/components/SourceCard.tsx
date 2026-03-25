import { Eye } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { SourceInfo } from '../types'

function stripMarkdown(text: string): string {
  return text
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/[*_~`#\\]/g, '')
    .replace(/\s{2,}/g, ' ')
    .trim()
}

interface Props {
  source: SourceInfo
  index: number
  onPreview?: (documentId: number, title: string) => void
}

export function SourceCard({ source, index, onPreview }: Props) {
  const { t } = useTranslation()
  const canPreview = !!source.document_id && !!onPreview

  return (
    <div className="source-card">
      <div className="source-card-header">
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
              onClick={() => onPreview!(source.document_id!, source.doc_title)}
              data-tooltip={t('chat.sources.preview')}
            >
              <Eye size={14} />
            </button>
          )}
          <span className="source-card-index">{index}</span>
        </div>
      </div>
      {source.content_preview && (
        <div className="source-card-snippet">{stripMarkdown(source.content_preview)}</div>
      )}
    </div>
  )
}
