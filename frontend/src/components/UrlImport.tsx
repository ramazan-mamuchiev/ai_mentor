import { useCallback, useState } from 'react'
import { Globe, X, CheckCircle, AlertCircle, Loader2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { ingestUrl } from '../api/documents'

interface UrlImportProps {
  onComplete?: () => void
  onClose?: () => void
}

type ImportStatus = 'idle' | 'submitting' | 'completed' | 'error'

export function UrlImport({ onComplete, onClose }: UrlImportProps) {
  const { t } = useTranslation()
  const [url, setUrl] = useState('')
  const [productName, setProductName] = useState('')
  const [firmwareVersion, setFirmwareVersion] = useState('1.0')
  const [manufacturer, setManufacturer] = useState('')
  const [status, setStatus] = useState<ImportStatus>('idle')
  const [error, setError] = useState('')
  const [resultMessage, setResultMessage] = useState('')

  const isConfluence = /\/confluence\/spaces\/[^/]+\/pages\/\d+/.test(url)

  const handleSubmit = useCallback(async () => {
    if (!url.trim() || !productName.trim()) return

    setStatus('submitting')
    setError('')

    try {
      const result = await ingestUrl({
        url: url.trim(),
        product_name: productName.trim(),
        firmware_version: firmwareVersion || '1.0',
        manufacturer: manufacturer,
      })
      setStatus('completed')
      setResultMessage(result.message)
      onComplete?.()
    } catch (err) {
      setStatus('error')
      setError(err instanceof Error ? err.message : String(err))
    }
  }, [url, productName, firmwareVersion, manufacturer, onComplete])

  const handleReset = useCallback(() => {
    setUrl('')
    setProductName('')
    setFirmwareVersion('1.0')
    setManufacturer('')
    setStatus('idle')
    setError('')
    setResultMessage('')
  }, [])

  const isValid = url.trim().length > 0 && productName.trim().length > 0

  return (
    <div className="file-upload-overlay">
      <div className="file-upload-modal">
        <div className="file-upload-header">
          <h3>{t('urlImport.title')}</h3>
          {onClose && (
            <button className="file-upload-close" onClick={onClose} title={t('upload.close')}>
              <X size={18} />
            </button>
          )}
        </div>

        {status === 'idle' && (
          <div className="file-upload-form">
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
                  />
                </label>
              </div>
            </div>

            <button
              className="file-upload-start"
              onClick={handleSubmit}
              disabled={!isValid}
            >
              <Globe size={16} />
              {isConfluence ? t('urlImport.startCrawl') : t('urlImport.startImport')}
            </button>
          </div>
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

        {status === 'completed' && (
          <div className="file-upload-result file-upload-success">
            <CheckCircle size={24} />
            <div>
              <strong>{t('urlImport.complete')}</strong>
              <p>{resultMessage}</p>
            </div>
            <button className="file-upload-btn" onClick={handleReset}>{t('urlImport.another')}</button>
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
