import { useCallback, useEffect, useState } from 'react'
import { Globe, X, AlertCircle, Loader2, Search } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { ingestUrl, ingestSite } from '../api/documents'
import type { ProductContext } from './FileUpload'
import type { ProductSelection } from './ProductAutocomplete'

interface UrlImportProps {
  onComplete?: () => void
  onClose?: () => void
  productContext?: ProductContext
}

type ImportStatus = 'idle' | 'submitting' | 'error'

export function UrlImport({ onComplete, onClose, productContext }: UrlImportProps) {
  const { t } = useTranslation()
  const [url, setUrl] = useState('')
  const [productSel, setProductSel] = useState<ProductSelection>({
    productName: productContext?.name ?? '',
    manufacturer: productContext?.manufacturer ?? '',
    firmwareVersion: productContext?.version ?? '1.0',
    isExisting: false,
  })
  const productName = productSel.productName
  const firmwareVersion = productSel.firmwareVersion
  const manufacturer = productSel.manufacturer
  const [status, setStatus] = useState<ImportStatus>('idle')
  const [error, setError] = useState('')
  const [crawlSite, setCrawlSite] = useState(false)
  const [maxDepth, setMaxDepth] = useState(5)
  const [maxPages, setMaxPages] = useState(500)
  const [downloadResources, setDownloadResources] = useState(true)

  const isConfluence = /\/confluence\/spaces\/[^/]+\/pages\/\d+/.test(url)
  const isHttpUrl = /^https?:\/\/.+/.test(url.trim())
  const showSiteCrawlOption = isHttpUrl && !isConfluence

  const handleSubmit = useCallback(async (e?: React.FormEvent) => {
    e?.preventDefault()
    if (!url.trim() || !productName.trim()) return

    setStatus('submitting')
    setError('')

    try {
      if (crawlSite && showSiteCrawlOption) {
        await ingestSite({
          url: url.trim(),
          product_name: productName.trim(),
          firmware_version: firmwareVersion || '1.0',
          manufacturer: manufacturer,
          max_depth: maxDepth,
          max_pages: maxPages,
          download_resources: downloadResources,
        })
      } else {
        await ingestUrl({
          url: url.trim(),
          product_name: productName.trim(),
          firmware_version: firmwareVersion || '1.0',
          manufacturer: manufacturer,
        })
      }
      onComplete?.()
      onClose?.()
    } catch (err) {
      setStatus('error')
      setError(err instanceof Error ? err.message : String(err))
    }
  }, [url, productName, firmwareVersion, manufacturer, crawlSite, showSiteCrawlOption, maxDepth, maxPages, downloadResources, onComplete, onClose])

  const handleReset = useCallback(() => {
    setUrl('')
    setProductSel({
      productName: '',
      manufacturer: '',
      firmwareVersion: '1.0',
      isExisting: false,
    })
    setStatus('idle')
    setError('')
    setCrawlSite(false)
    setMaxDepth(5)
    setMaxPages(500)
    setDownloadResources(true)
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
            <button className="file-upload-close" onClick={onClose}>
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
                      : crawlSite
                        ? t('urlImport.siteDetected')
                        : t('urlImport.webPageDetected')
                    }
                  </span>
                </div>
              )}

              {showSiteCrawlOption && (
                <label className="url-import-toggle">
                  <input
                    type="checkbox"
                    checked={crawlSite}
                    onChange={e => setCrawlSite(e.target.checked)}
                  />
                  <Search size={14} />
                  <span>{t('urlImport.siteCrawlToggle')}</span>
                </label>
              )}

              {crawlSite && showSiteCrawlOption && (
                <>
                  <div className="file-upload-row">
                    <label>
                      {t('urlImport.maxDepth')}
                      <input
                        type="number"
                        value={maxDepth}
                        onChange={e => setMaxDepth(Math.max(1, Math.min(10, Number(e.target.value) || 1)))}
                        min={1}
                        max={10}
                      />
                    </label>
                    <label>
                      {t('urlImport.maxPages')}
                      <input
                        type="number"
                        value={maxPages}
                        onChange={e => setMaxPages(Math.max(1, Math.min(5000, Number(e.target.value) || 1)))}
                        min={1}
                        max={5000}
                      />
                    </label>
                  </div>
                  <label className="url-import-toggle">
                    <input
                      type="checkbox"
                      checked={downloadResources}
                      onChange={e => setDownloadResources(e.target.checked)}
                    />
                    <span>{t('urlImport.downloadResources')}</span>
                  </label>
                </>
              )}

              <label>
                {t('upload.productOrCreate')}
                <input
                  type="text"
                  value={productName}
                  onChange={e => setProductSel(prev => ({ ...prev, productName: e.target.value, isExisting: false, productId: undefined }))}
                  placeholder={t('upload.productPlaceholder')}
                />
              </label>

              <div className="file-upload-row">
                <label>
                  {t('upload.manufacturer')}
                  <input
                    type="text"
                    value={manufacturer}
                    onChange={e => setProductSel(prev => ({ ...prev, manufacturer: e.target.value }))}
                    placeholder={t('upload.manufacturerPlaceholder')}
                    readOnly={productSel.isExisting}
                    className={productSel.isExisting ? 'input-readonly' : ''}
                  />
                </label>
                <label>
                  {t('upload.version')}
                  <input
                    type="text"
                    value={firmwareVersion}
                    onChange={e => setProductSel(prev => ({ ...prev, firmwareVersion: e.target.value }))}
                    placeholder={t('upload.versionPlaceholder')}
                    readOnly={productSel.isExisting}
                    className={productSel.isExisting ? 'input-readonly' : ''}
                  />
                </label>
              </div>
            </div>

            <button
              type="submit"
              className="file-upload-start"
              disabled={!isValid}
            >
              {crawlSite ? <Search size={16} /> : <Globe size={16} />}
              {t('urlImport.startImport')}
            </button>
          </form>
        )}

        {status === 'submitting' && (
          <div className="file-upload-progress">
            <div className="file-upload-file-info">
              {crawlSite ? <Search size={20} /> : <Globe size={20} />}
              <div>
                <strong>
                  {isConfluence
                    ? t('urlImport.crawling')
                    : crawlSite
                      ? t('urlImport.crawlingSite')
                      : t('urlImport.fetching')
                  }
                </strong>
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
