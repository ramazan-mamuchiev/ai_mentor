import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { X, Loader2, AlertCircle, Key, Maximize2, Minimize2, Search } from 'lucide-react'
import { getProductSearchKeys } from '../api/products'
import { getDocumentSearchKeys } from '../api/documents'
import type { ProductSearchKeysResponse, DocumentSearchKeysResponse } from '../types'

interface ProductProps {
  mode: 'product'
  entityId: number
  entityTitle: string
  onClose: () => void
}

interface DocumentProps {
  mode: 'document'
  entityId: number
  entityTitle: string
  onClose: () => void
}

type Props = ProductProps | DocumentProps

export function SearchKeysModal({ mode, entityId, entityTitle, onClose }: Props) {
  const { t } = useTranslation()
  const [productData, setProductData] = useState<ProductSearchKeysResponse | null>(null)
  const [documentData, setDocumentData] = useState<DocumentSearchKeysResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [fullscreen, setFullscreen] = useState(false)
  const [filter, setFilter] = useState('')

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    const promise = mode === 'product'
      ? getProductSearchKeys(entityId)
      : getDocumentSearchKeys(entityId)

    promise
      .then(result => {
        if (cancelled) return
        if (mode === 'product') setProductData(result as ProductSearchKeysResponse)
        else setDocumentData(result as DocumentSearchKeysResponse)
        setLoading(false)
      })
      .catch(err => {
        if (cancelled) return
        setError(err?.message || 'Failed to load keys')
        setLoading(false)
      })

    return () => { cancelled = true }
  }, [mode, entityId])

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [onClose])

  const lowerFilter = filter.toLowerCase()

  const renderProductKeys = () => {
    if (!productData) return null
    const filteredLlm = productData.llm_keys.filter(k => k.toLowerCase().includes(lowerFilter))
    const filteredChunks = productData.chunk_keys_by_document
      .map(group => ({
        ...group,
        keys: group.keys.filter(k => k.toLowerCase().includes(lowerFilter)),
      }))
      .filter(group => group.keys.length > 0)

    const visibleCount = filteredLlm.length + filteredChunks.reduce((s, g) => s + g.keys.length, 0)

    return (
      <>
        <div className="sk-summary">
          {t('searchKeys.totalKeys')}: <strong>{productData.total_keys}</strong>
          {filter && <> &middot; {t('searchKeys.showing')}: <strong>{visibleCount}</strong></>}
        </div>

        {filteredLlm.length > 0 && (
          <div className="sk-section">
            <h4 className="sk-section-title">
              LLM keys <span className="sk-count">({filteredLlm.length})</span>
            </h4>
            <div className="sk-tags">
              {filteredLlm.map((key, i) => (
                <span key={i} className="sk-tag sk-tag--llm">{key}</span>
              ))}
            </div>
          </div>
        )}

        {filteredChunks.map(group => (
          <div key={group.document_id} className="sk-section">
            <h4 className="sk-section-title">
              {group.title} <span className="sk-count">({group.keys.length})</span>
            </h4>
            <div className="sk-tags">
              {group.keys.map((key, i) => (
                <span key={i} className="sk-tag sk-tag--chunk">{key}</span>
              ))}
            </div>
          </div>
        ))}

        {visibleCount === 0 && (
          <div className="sk-empty">{t('searchKeys.noKeysMatch')}</div>
        )}
      </>
    )
  }

  const renderDocumentKeys = () => {
    if (!documentData) return null
    const filtered = documentData.keys.filter(k => k.key.toLowerCase().includes(lowerFilter))

    return (
      <>
        <div className="sk-summary">
          {t('searchKeys.totalKeys')}: <strong>{documentData.total_keys}</strong>
          {filter && <> &middot; {t('searchKeys.showing')}: <strong>{filtered.length}</strong></>}
        </div>

        {filtered.length > 0 && (
          <div className="sk-section">
            <div className="sk-tags">
              {filtered.map((item, i) => (
                <span key={i} className={`sk-tag sk-tag--${item.source}`}>{item.key}</span>
              ))}
            </div>
          </div>
        )}

        {filtered.length === 0 && (
          <div className="sk-empty">{t('searchKeys.noKeysMatch')}</div>
        )}
      </>
    )
  }

  return (
    <div className="confirm-overlay" onClick={onClose}>
      <div
        className={`md-preview-dialog${fullscreen ? ' md-preview-dialog--fullscreen' : ''}`}
        onClick={e => e.stopPropagation()}
        role="dialog"
        aria-labelledby="sk-modal-title"
      >
        <div className="md-preview-header">
          <div className="md-preview-title-row">
            <Key size={18} />
            <h3 id="sk-modal-title" className="md-preview-title">
              {t('searchKeys.title')}: {entityTitle}
            </h3>
          </div>
          <div className="md-preview-header-actions">
            <button
              className="md-preview-close-btn"
              onClick={() => setFullscreen(f => !f)}
            >
              {fullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
            </button>
            <button className="md-preview-close-btn" onClick={onClose}>
              <X size={14} />
            </button>
          </div>
        </div>

        <div className="md-preview-body">
          {!loading && !error && (
            <div className="sk-filter-bar">
              <Search size={16} />
              <input
                type="text"
                className="sk-filter-input"
                placeholder={t('searchKeys.filterPlaceholder')}
                value={filter}
                onChange={e => setFilter(e.target.value)}
                autoFocus
              />
            </div>
          )}

          {loading && (
            <div className="md-preview-placeholder">
              <Loader2 size={32} className="spin-icon" />
              <span>{t('searchKeys.loading')}</span>
            </div>
          )}
          {error && (
            <div className="md-preview-placeholder md-preview-placeholder--error">
              <AlertCircle size={32} />
              <span>{error}</span>
            </div>
          )}
          {!loading && !error && (
            <div className="sk-content">
              {mode === 'product' ? renderProductKeys() : renderDocumentKeys()}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
