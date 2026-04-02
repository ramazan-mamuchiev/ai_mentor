import { useCallback, useEffect, useState } from 'react'
import { Globe, X, AlertCircle, Loader2, Search, Github } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { ingestUrl, ingestSite, ingestGitHub } from '../api/documents'
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
  const [githubBranch, setGithubBranch] = useState('main')
  const [confluenceMaxPages, setConfluenceMaxPages] = useState(10000)
  const [confluenceMaxDepth, setConfluenceMaxDepth] = useState(100)
  const [confluenceUsername, setConfluenceUsername] = useState('')
  const [confluencePassword, setConfluencePassword] = useState('')

  const isConfluence = /\/spaces\/[^/]+\/pages\/\d+/.test(url) || /\/spaces\/[^/]+(?:\/overview)?\/?$/.test(url.trim())
  const isGitHub = /^https?:\/\/(?:www\.)?github\.com\/[^/]+\/[^/]+/.test(url.trim())
  const isHttpUrl = /^https?:\/\/.+/.test(url.trim())
  const showSiteCrawlOption = isHttpUrl && !isConfluence && !isGitHub

  const handleSubmit = useCallback(async (e?: React.FormEvent) => {
    e?.preventDefault()
    if (!url.trim() || !productName.trim()) return

    setStatus('submitting')
    setError('')

    try {
      if (isGitHub) {
        await ingestGitHub({
          url: url.trim(),
          product_name: productName.trim(),
          firmware_version: firmwareVersion || '1.0',
          manufacturer: manufacturer,
          branch: githubBranch || 'main',
        })
      } else if (crawlSite && showSiteCrawlOption) {
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
          ...(isConfluence ? {
            max_pages: confluenceMaxPages,
            max_depth: confluenceMaxDepth,
            ...(confluenceUsername ? { confluence_username: confluenceUsername } : {}),
            ...(confluencePassword ? { confluence_password: confluencePassword } : {}),
          } : {}),
        })
      }
      onComplete?.()
      onClose?.()
    } catch (err) {
      setStatus('error')
      setError(err instanceof Error ? err.message : String(err))
    }
  }, [url, productName, firmwareVersion, manufacturer, crawlSite, showSiteCrawlOption, isGitHub, isConfluence, githubBranch, maxDepth, maxPages, downloadResources, confluenceMaxPages, confluenceMaxDepth, confluenceUsername, confluencePassword, onComplete, onClose])

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
    setGithubBranch('main')
    setMaxDepth(5)
    setMaxPages(500)
    setDownloadResources(true)
    setConfluenceMaxPages(10000)
    setConfluenceMaxDepth(100)
    setConfluenceUsername('')
    setConfluencePassword('')
  }, [])

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose?.()
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  const hasProductContext = !!productContext
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
                  {isGitHub ? <Github size={14} /> : <Globe size={14} />}
                  <span>
                    {isGitHub
                      ? t('urlImport.githubDetected')
                      : isConfluence
                        ? t('urlImport.confluenceDetected')
                        : crawlSite
                          ? t('urlImport.siteDetected')
                          : t('urlImport.webPageDetected')
                    }
                  </span>
                </div>
              )}

              {isGitHub && (
                <label>
                  {t('urlImport.githubBranch')}
                  <input
                    type="text"
                    value={githubBranch}
                    onChange={e => setGithubBranch(e.target.value)}
                    placeholder="main"
                  />
                </label>
              )}

              {isConfluence && (
                <>
                  <div className="file-upload-row">
                    <label>
                      {t('urlImport.maxDepth')}
                      <input
                        type="number"
                        value={confluenceMaxDepth}
                        onChange={e => setConfluenceMaxDepth(Math.max(1, Math.min(200, Number(e.target.value) || 1)))}
                        min={1}
                        max={200}
                      />
                    </label>
                    <label>
                      {t('urlImport.maxPages')}
                      <input
                        type="number"
                        value={confluenceMaxPages}
                        onChange={e => setConfluenceMaxPages(Math.max(1, Math.min(50000, Number(e.target.value) || 1)))}
                        min={1}
                        max={50000}
                      />
                    </label>
                  </div>
                  <div className="url-import-type-hint" style={{ opacity: 0.7, fontSize: '0.82em' }}>
                    {t('urlImport.confluenceAuthHint')}
                  </div>
                  <div className="file-upload-row">
                    <label>
                      {t('urlImport.confluenceUsername')}
                      <input
                        type="text"
                        value={confluenceUsername}
                        onChange={e => setConfluenceUsername(e.target.value)}
                        autoComplete="username"
                      />
                    </label>
                    <label>
                      {t('urlImport.confluencePassword')}
                      <input
                        type="password"
                        value={confluencePassword}
                        onChange={e => setConfluencePassword(e.target.value)}
                        autoComplete="current-password"
                      />
                    </label>
                  </div>
                </>
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
                        onChange={e => setMaxDepth(Math.max(1, Math.min(200, Number(e.target.value) || 1)))}
                        min={1}
                        max={200}
                      />
                    </label>
                    <label>
                      {t('urlImport.maxPages')}
                      <input
                        type="number"
                        value={maxPages}
                        onChange={e => setMaxPages(Math.max(1, Math.min(50000, Number(e.target.value) || 1)))}
                        min={1}
                        max={50000}
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
                  readOnly={hasProductContext}
                  className={hasProductContext ? 'input-readonly' : ''}
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
                    readOnly={hasProductContext || productSel.isExisting}
                    className={hasProductContext || productSel.isExisting ? 'input-readonly' : ''}
                  />
                </label>
                <label>
                  {t('upload.version')}
                  <input
                    type="text"
                    value={firmwareVersion}
                    onChange={e => setProductSel(prev => ({ ...prev, firmwareVersion: e.target.value }))}
                    placeholder={t('upload.versionPlaceholder')}
                    readOnly={hasProductContext || productSel.isExisting}
                    className={hasProductContext || productSel.isExisting ? 'input-readonly' : ''}
                  />
                </label>
              </div>
            </div>

            <button
              type="submit"
              className="file-upload-start"
              disabled={!isValid}
            >
              {isGitHub ? <Github size={16} /> : crawlSite ? <Search size={16} /> : <Globe size={16} />}
              {t('urlImport.startImport')}
            </button>
          </form>
        )}

        {status === 'submitting' && (
          <div className="file-upload-progress">
            <div className="file-upload-file-info">
              {isGitHub ? <Github size={20} /> : crawlSite ? <Search size={20} /> : <Globe size={20} />}
              <div>
                <strong>
                  {isGitHub
                    ? t('urlImport.crawlingGithub')
                    : isConfluence
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
