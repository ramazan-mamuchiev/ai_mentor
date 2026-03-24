import { useCallback, useEffect, useState } from 'react'
import { Globe, X, AlertCircle, Loader2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { ingestUrl } from '../api/documents'
import type { ProductContext } from './FileUpload'

interface UrlImportProps {
  onComplete?: () => void
  onClose?: () => void
  productContext?: ProductContext
}

type ImportStatus = 'idle' | 'submitting' | 'error'

export function UrlImport({ onComplete, onClose, productContext }: UrlImportProps) {
  const { t } = useTranslation()
  const [url, setUrl] = useState('')
  const [productName, setProductName] = useState(productContext?.name ?? '')
  const [firmwareVersion, setFirmwareVersion] = useState('1.0')
  const [manufacturer, setManufacturer] = useState(productContext?.manufacturer ?? '')
  const hasProductContext = !!productContext?.name
  const [status, setStatus] = useState<ImportStatus>('idle')
  const [error, setError] = useState('')

  const isConfluence = /\/confluence\/spaces\/[^/]+\/pages\/\d+/.test(url)

  const handleSubmit = useCallback(async (e?: React.FormEvent) => {
    e?.preventDefault()
    if (!url.trim() || !productName.trim()) return

    setStatus('submitting')
    setError('')

    try {
      await ingestUrl({
        url: url.trim(),
        product_name: productName.trim(),
        firmware_version: firmwareVersion || '1.0',
        manufacturer: manufacturer,
      })
      onComplete?.()
      onClose?.()
    } catch (err) {
      setStatus('error')
      setError(err instanceof Error ? err.message : String(err))
    }
  }, [url, productName, firmwareVersion, manufacturer, onComplete, onClose])

  const handleReset = useCallback(() => {
    setUrl('')
    setProductName('')
    setFirmwareVersion('1.0')
    setManufacturer('')
    setStatus('idle')
    setError('')
  }, [])

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose?.()
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  const isValid = url.trim().length > 0 && productName.trim().length > 0

  return (
    <div className="file-upload-overlay">
      <div className="file-upload-modal">
        <div className="file-upload-header">
          <h3>{t('urlImport.title')}</h3>
          {onClose && (
            <button className="file-upload-close" onClick={onClose} data-tooltip={t('upload.close')}>
              <X size={18} />
            </button>
          )}
        </div>

        {status === 'idle' && (
          <form className="file-upload-form" onSubmit={handleSubmit}>
            <div className="file-upload-fields">
              <label>
                {t('urlImport.url')}
                <input
                  type="url"
                  value={url}
                  onChange={e => setUrl(e.target.value)}
                  placeholder={t('urlImport.urlPlaceholder')}
                  autoFocus
                />
              </label>

              {url.trim() && (
                <div className="url-import-type-hint">
                  <Globe size={14} />
                  <span>
                    {isConfluence
                      ? t('urlImport.confluenceDetected')
                      : t('urlImport.webPageDetected')
                    }
                  </span>
                </div>
              )}

              <label>
                {t('upload.productName')}
                <input
                  type="text"
                  value={productName}
                  onChange={e => setProductName(e.target.value)}
                  placeholder={t('upload.productPlaceholder')}
                  readOnly={hasProductContext}
                  className={hasProductContext ? 'input-readonly' : ''}
                />
              </label>

              <div className="file-upload-row">
                <label>
                  {t('upload.version')}
                  <input
                    type="text"
                    value={firmwareVersion}
                    onChange={e => setFirmwareVersion(e.target.value)}
                    placeholder={t('upload.versionPlaceholder')}
                  />
                </label>
                <label>
                  {t('upload.manufacturer')}
                  <input
                    type="text"
                    value={manufacturer}
                    onChange={e => setManufacturer(e.target.value)}
                    placeholder={t('upload.manufacturerPlaceholder')}
                    readOnly={hasProductContext && !!productContext?.manufacturer}
                    className={hasProductContext && !!productContext?.manufacturer ? 'input-readonly' : ''}
                  />
                </label>
              </div>
            </div>

            <button
              type="submit"
              className="file-upload-start"
              disabled={!isValid}
            >
              <Globe size={16} />
              {t('urlImport.startImport')}
            </button>
          </form>
        )}

        {status === 'submitting' && (
          <div className="file-upload-progress">
            <div className="file-upload-file-info">
              <Globe size={20} />
              <div>
                <strong>{isConfluence ? t('urlImport.crawling') : t('urlImport.fetching')}</strong>
                <span className="docs-cell-overflow" style={{ maxWidth: 300 }}>{url}</span>
              </div>
            </div>
            <div className="file-upload-bar-container">
              <div className="file-upload-bar" style={{ width: '100%', animation: 'pulse 1.5s ease-in-out infinite' }} />
            </div>
            <div className="file-upload-stats">
              <Loader2 size={14} className="spin-icon" />
              <span>{t('urlImport.processing')}</span>
            </div>
          </div>
        )}

        {status === 'error' && (
          <div className="file-upload-result file-upload-error">
            <AlertCircle size={24} />
            <div>
              <strong>{t('urlImport.failed')}</strong>
              <p>{error}</p>
            </div>
            <div className="file-upload-actions">
              <button className="file-upload-btn" onClick={handleSubmit}>{t('upload.retry')}</button>
              <button className="file-upload-btn" onClick={handleReset}>{t('upload.cancel')}</button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
