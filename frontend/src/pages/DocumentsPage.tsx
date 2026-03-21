import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  FileText,
  Upload,
  Download,
  RefreshCw,
  Trash2,
  Clock,
  Loader2,
  CheckCircle,
  AlertCircle,
} from 'lucide-react'
import { listDocuments, downloadDocument, deleteDocument } from '../api/documents'
import type { DocumentListItem, DocumentStatusValue } from '../types'

const POLL_INTERVAL = 5000

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${(bytes / Math.pow(k, i)).toFixed(i > 0 ? 1 : 0)} ${sizes[i]}`
}

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

function StatusBadge({ status }: { status: DocumentStatusValue }) {
  const { t } = useTranslation()
  const icons: Record<DocumentStatusValue, React.ReactNode> = {
    pending: <Clock size={14} />,
    processing: <Loader2 size={14} className="spin-icon" />,
    ready: <CheckCircle size={14} />,
    error: <AlertCircle size={14} />,
  }
  return (
    <span className={`docs-status docs-status--${status}`}>
      {icons[status]}
      {t(`docs.status.${status}`)}
    </span>
  )
}

interface Props {
  onUploadClick: () => void
}

export function DocumentsPage({ onUploadClick }: Props) {
  const { t } = useTranslation()
  const [documents, setDocuments] = useState<DocumentListItem[]>([])
  const [loading, setLoading] = useState(true)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchDocs = useCallback(async () => {
    try {
      const docs = await listDocuments()
      setDocuments(docs)
    } catch {
      // keep previous state
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchDocs()
  }, [fetchDocs])

  useEffect(() => {
    const hasPending = documents.some(d => d.status === 'pending' || d.status === 'processing')
    if (hasPending) {
      pollRef.current = setInterval(fetchDocs, POLL_INTERVAL)
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [documents, fetchDocs])

  const handleDownload = useCallback(async (id: number) => {
    try {
      const result = await downloadDocument(id)
      window.open(result.download_url, '_blank')
    } catch {
      // ignore
    }
  }, [])

  const handleDelete = useCallback(async (id: number) => {
    if (!confirm(t('docs.actions.confirmDelete'))) return
    try {
      await deleteDocument(id)
      setDocuments(prev => prev.filter(d => d.id !== id))
    } catch {
      // ignore
    }
  }, [t])

  if (loading) {
    return (
      <div className="docs-page">
        <div className="docs-empty">
          <Loader2 size={32} className="spin-icon docs-empty-icon" />
        </div>
      </div>
    )
  }

  if (documents.length === 0) {
    return (
      <div className="docs-page">
        <div className="docs-empty">
          <FileText size={48} className="docs-empty-icon" />
          <h2>{t('docs.empty.title')}</h2>
          <p>{t('docs.empty.description')}</p>
          <button className="docs-upload-btn" onClick={onUploadClick}>
            <Upload size={16} />
            <span>{t('docs.empty.cta')}</span>
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="docs-page">
      <div className="docs-header">
        <h1>{t('docs.title')}</h1>
        <button className="docs-upload-btn" onClick={onUploadClick}>
          <Upload size={16} />
          <span>{t('docs.upload')}</span>
        </button>
      </div>

      {/* Desktop/Tablet: Table */}
      <div className="docs-table-wrap">
        <table className="docs-table">
          <thead>
            <tr>
              <th>{t('docs.table.name')}</th>
              <th>{t('docs.table.format')}</th>
              <th>{t('docs.table.status')}</th>
              <th>{t('docs.table.size')}</th>
              <th className="col-chunks">{t('docs.table.chunks')}</th>
              <th className="col-product">{t('docs.table.product')}</th>
              <th>{t('docs.table.date')}</th>
              <th>{t('docs.table.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {documents.map(doc => (
              <tr key={doc.id}>
                <td>
                  <div className="docs-name">{doc.title}</div>
                  <div className="docs-filename">{doc.original_filename}</div>
                </td>
                <td><span className="docs-format">{doc.format}</span></td>
                <td><StatusBadge status={doc.status} /></td>
                <td className="docs-size">{formatBytes(doc.file_size_bytes)}</td>
                <td className="docs-chunks col-chunks">{doc.total_chunks || '—'}</td>
                <td className="docs-product col-product">{doc.product_name || '—'}</td>
                <td className="docs-date">{formatDate(doc.ingested_at)}</td>
                <td>
                  <div className="docs-actions">
                    {doc.status === 'ready' && (
                      <button
                        className="docs-action-btn"
                        onClick={() => handleDownload(doc.id)}
                        title={t('docs.actions.download')}
                      >
                        <Download size={16} />
                      </button>
                    )}
                    {doc.status === 'ready' && (
                      <button
                        className="docs-action-btn"
                        title={t('docs.actions.reindex')}
                      >
                        <RefreshCw size={16} />
                      </button>
                    )}
                    <button
                      className="docs-action-btn docs-action-btn--danger"
                      onClick={() => handleDelete(doc.id)}
                      title={t('docs.actions.delete')}
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile: Cards */}
      <div className="docs-cards">
        {documents.map(doc => (
          <div className="docs-card" key={doc.id}>
            <div className="docs-card-header">
              <div className="docs-card-title">{doc.title}</div>
              <StatusBadge status={doc.status} />
            </div>
            <div className="docs-card-meta">
              <span><span className="docs-format">{doc.format}</span></span>
              <span>{formatBytes(doc.file_size_bytes)}</span>
              {doc.product_name && <span>{doc.product_name}</span>}
              <span>{formatDate(doc.ingested_at)}</span>
            </div>
            <div className="docs-card-actions">
              {doc.status === 'ready' && (
                <button
                  className="docs-action-btn"
                  onClick={() => handleDownload(doc.id)}
                  title={t('docs.actions.download')}
                >
                  <Download size={16} />
                </button>
              )}
              <button
                className="docs-action-btn docs-action-btn--danger"
                onClick={() => handleDelete(doc.id)}
                title={t('docs.actions.delete')}
              >
                <Trash2 size={16} />
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
