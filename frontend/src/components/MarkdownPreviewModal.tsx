import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { X, Download, Loader2, AlertCircle, FileText, Maximize2, Minimize2 } from 'lucide-react'
import { MarkdownRenderer } from './MarkdownRenderer'
import { previewMarkdown } from '../api/documents'
import type { DocumentMarkdownPreview } from '../types'

interface Props {
  documentId: number
  documentTitle: string
  onClose: () => void
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${(bytes / Math.pow(k, i)).toFixed(i > 0 ? 1 : 0)} ${sizes[i]}`
}

const SOURCE_LABELS: Record<string, string> = {
  s3_converted: 'S3 (converted)',
  s3_original: 'S3 (original)',
  chunks_reconstructed: 'Reconstructed from chunks',
}

export function MarkdownPreviewModal({ documentId, documentTitle, onClose }: Props) {
  const { t } = useTranslation()
  const [data, setData] = useState<DocumentMarkdownPreview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [fullscreen, setFullscreen] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    previewMarkdown(documentId)
      .then(result => {
        if (!cancelled) {
          setData(result)
          setLoading(false)
        }
      })
      .catch(err => {
        if (!cancelled) {
          setError(err?.message || 'Failed to load preview')
          setLoading(false)
        }
      })
    return () => { cancelled = true }
  }, [documentId])

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [onClose])

  const handleDownload = useCallback(() => {
    if (!data) return
    const blob = new Blob([data.markdown], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${data.title || `document-${documentId}`}.md`
    a.click()
    URL.revokeObjectURL(url)
  }, [data, documentId])

  const showSpinner = loading

  return (
    <div className="confirm-overlay" onClick={onClose}>
      <div
        className={`md-preview-dialog${fullscreen ? ' md-preview-dialog--fullscreen' : ''}`}
        onClick={e => e.stopPropagation()}
        role="dialog"
        aria-labelledby="md-preview-title"
      >
        <div className="md-preview-header">
          <div className="md-preview-title-row">
            <FileText size={18} />
            <h3 id="md-preview-title" className="md-preview-title">
              {t('docs.preview.title')}: {documentTitle}
            </h3>
          </div>
          <div className="md-preview-header-actions">
            {data && (
              <>
                <span className="md-preview-meta">
                  {formatBytes(data.size_bytes)} &middot; {SOURCE_LABELS[data.source] || data.source}
                </span>
                <button className="md-preview-download-btn" onClick={handleDownload} data-tooltip={t('docs.preview.download')}>
                  <Download size={16} />
                  <span>{t('docs.preview.download')}</span>
                </button>
              </>
            )}
            <button
              className="md-preview-close-btn"
              onClick={() => setFullscreen(f => !f)}
              data-tooltip={t(fullscreen ? 'docs.preview.collapse' : 'docs.preview.expand')}
            >
              {fullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
            </button>
            <button className="md-preview-close-btn" onClick={onClose} data-tooltip={t('docDebug.collapse')}>
              <X size={14} />
            </button>
          </div>
        </div>

        <div className="md-preview-body">
          {showSpinner && (
            <div className="md-preview-placeholder">
              <Loader2 size={32} className="spin-icon" />
              <span>{t('docs.preview.loading')}</span>
            </div>
          )}
          {error && (
            <div className="md-preview-placeholder md-preview-placeholder--error">
              <AlertCircle size={32} />
              <span>{error}</span>
            </div>
          )}
          {data && !showSpinner && (
            <div className="md-preview-content">
              <MarkdownRenderer content={data.markdown} />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
