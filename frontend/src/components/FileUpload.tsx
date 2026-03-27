import { useCallback, useEffect, useRef, useState } from 'react'
import { Upload as UploadIcon, X, Pause, Play, CheckCircle, AlertCircle, FileText } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import * as tus from 'tus-js-client'
import { ProductAutocomplete, type ProductSelection } from './ProductAutocomplete'

export interface ProductContext {
  name: string
  manufacturer?: string
  version?: string
}

interface FileUploadProps {
  onComplete?: (documentId: number, filename: string) => void
  onClose?: () => void
  productContext?: ProductContext
}

interface UploadState {
  file: File | null
  progress: number
  speed: string
  status: 'idle' | 'uploading' | 'paused' | 'completed' | 'error'
  error: string
  documentId: number | null
  uploadInstance: tus.Upload | null
}

const CHUNK_SIZE = 10 * 1024 * 1024 // 10 MB

export function FileUpload({ onComplete, onClose, productContext }: FileUploadProps) {
  const { t } = useTranslation()
  const [state, setState] = useState<UploadState>({
    file: null,
    progress: 0,
    speed: '',
    status: 'idle',
    error: '',
    documentId: null,
    uploadInstance: null,
  })
  const hasProductContext = !!productContext?.name
  const [productSel, setProductSel] = useState<ProductSelection>({
    productName: productContext?.name ?? '',
    manufacturer: productContext?.manufacturer ?? '',
    firmwareVersion: productContext?.version ?? '1.0',
    isExisting: false,
  })
  const productName = productSel.productName
  const firmwareVersion = productSel.firmwareVersion
  const manufacturer = productSel.manufacturer
  const [isDragOver, setIsDragOver] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const startTimeRef = useRef<number>(0)

  const handleFileSelect = useCallback((file: File) => {
    setState(prev => ({
      ...prev,
      file,
      progress: 0,
      speed: '',
      status: 'idle',
      error: '',
      documentId: null,
      uploadInstance: null,
    }))
  }, [])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragOver(false)
    const file = e.dataTransfer.files[0]
    if (file) handleFileSelect(file)
  }, [handleFileSelect])

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragOver(true)
  }, [])

  const handleDragLeave = useCallback(() => {
    setIsDragOver(false)
  }, [])

  const startUpload = useCallback((e?: React.FormEvent) => {
    e?.preventDefault()
    if (!state.file || !productName.trim()) return

    startTimeRef.current = Date.now()

    const upload = new tus.Upload(state.file, {
      endpoint: '/api/v1/uploads/',
      chunkSize: CHUNK_SIZE,
      retryDelays: [0, 1000, 3000, 5000, 10000],
      onBeforeRequest: (req) => {
        const xhr = req.getUnderlyingObject() as XMLHttpRequest
        xhr.withCredentials = true
      },
      metadata: {
        filename: state.file.name,
        product_name: productName.trim(),
        firmware_version: firmwareVersion || '1.0',
        manufacturer: manufacturer,
        content_type: state.file.type || 'application/octet-stream',
      },
      onProgress: (bytesUploaded: number, bytesTotal: number) => {
        const pct = Math.round((bytesUploaded / bytesTotal) * 100)
        const elapsed = (Date.now() - startTimeRef.current) / 1000
        const speedMBps = elapsed > 0 ? (bytesUploaded / 1024 / 1024) / elapsed : 0
        setState(prev => ({
          ...prev,
          progress: pct,
          speed: `${speedMBps.toFixed(1)} MB/s`,
        }))
      },
      onSuccess: () => {
        const url = upload.url || ''
        const uploadId = url.split('/').filter(Boolean).pop() || ''

        setState(prev => ({
          ...prev,
          status: 'completed',
          progress: 100,
        }))

        // Poll for document completion via the upload response headers
        // The document ID is returned in X-Document-Id header of the final PATCH
        // For now, we show upload complete and let user check documents list
        if (onComplete && uploadId) {
          // We don't have direct access to response headers from tus-js-client
          // The document will appear in the documents list
          onComplete(0, state.file?.name || '')
        }
      },
      onError: (error: Error) => {
        setState(prev => ({
          ...prev,
          status: 'error',
          error: error.message || t('upload.failed'),
        }))
      },
    })

    setState(prev => ({ ...prev, status: 'uploading', uploadInstance: upload, error: '' }))
    upload.start()
  }, [state.file, productName, firmwareVersion, manufacturer, onComplete])

  const togglePause = useCallback(() => {
    if (!state.uploadInstance) return

    if (state.status === 'uploading') {
      state.uploadInstance.abort()
      setState(prev => ({ ...prev, status: 'paused' }))
    } else if (state.status === 'paused') {
      state.uploadInstance.start()
      setState(prev => ({ ...prev, status: 'uploading' }))
    }
  }, [state.uploadInstance, state.status])

  const cancelUpload = useCallback(() => {
    if (state.uploadInstance) {
      state.uploadInstance.abort(true)
    }
    setState({
      file: null,
      progress: 0,
      speed: '',
      status: 'idle',
      error: '',
      documentId: null,
      uploadInstance: null,
    })
  }, [state.uploadInstance])

  const formatSize = (bytes: number) => {
    if (bytes >= 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`
    if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
    return `${(bytes / 1024).toFixed(1)} KB`
  }

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose?.()
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  const isUploading = state.status === 'uploading' || state.status === 'paused'

  return (
    <div className="file-upload-overlay">
      <div className="file-upload-modal">
        <div className="file-upload-header">
          <h3>{t('upload.title')}</h3>
          {onClose && (
            <button className="file-upload-close" onClick={onClose} data-tooltip={t('upload.close')} data-tooltip-align="right">
              <X size={18} />
            </button>
          )}
        </div>

        {/* Drop zone */}
        {!state.file && (
          <div
            className={`file-upload-dropzone ${isDragOver ? 'dragover' : ''}`}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
          >
            <UploadIcon size={32} />
            <p>{t('upload.dropzone')}</p>
            <button
              type="button"
              className="file-upload-browse"
              onClick={() => fileInputRef.current?.click()}
            >
              {t('upload.browse')}
            </button>
            <span className="file-upload-hint">
              {t('upload.formats')}
            </span>
            <input
              ref={fileInputRef}
              type="file"
              accept=".md,.txt,.pdf,.json,.yaml,.yml,.proto,.wsdl,.xml,.zip,.7z,.tar,.tar.gz,.tgz,.tar.bz2,.tar.xz,.rar"
              style={{ display: 'none' }}
              onChange={e => {
                const file = e.target.files?.[0]
                if (file) handleFileSelect(file)
              }}
            />
          </div>
        )}

        {/* File selected — show form */}
        {state.file && state.status === 'idle' && (
          <form className="file-upload-form" onSubmit={startUpload}>
            <div className="file-upload-file-info">
              <FileText size={20} />
              <div>
                <strong>{state.file.name}</strong>
                <span>{formatSize(state.file.size)}</span>
              </div>
              <button type="button" className="file-upload-remove" onClick={() => setState(prev => ({ ...prev, file: null }))} data-tooltip={t('upload.removeFile')} data-tooltip-align="right">
                <X size={16} />
              </button>
            </div>

            <div className="file-upload-fields">
              {hasProductContext ? (
                <label>
                  {t('upload.productName')}
                  <input
                    type="text"
                    value={productName}
                    readOnly
                    className="input-readonly"
                  />
                </label>
              ) : (
                <label>
                  {t('upload.productOrCreate')}
                  <ProductAutocomplete
                    value={productSel}
                    onChange={setProductSel}
                    autoFocus={!hasProductContext}
                  />
                </label>
              )}
              <div className="file-upload-row">
                <label>
                  {t('upload.version')}
                  <input
                    type="text"
                    value={firmwareVersion}
                    onChange={e => setProductSel(prev => ({ ...prev, firmwareVersion: e.target.value }))}
                    placeholder={t('upload.versionPlaceholder')}
                    readOnly={hasProductContext || productSel.isExisting}
                    className={hasProductContext || productSel.isExisting ? 'input-readonly' : ''}
                    autoFocus={hasProductContext}
                  />
                </label>
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
              </div>
            </div>

            <button
              type="submit"
              className="file-upload-start"
              disabled={!productName.trim()}
            >
              <UploadIcon size={16} />
              {t('upload.start')}
            </button>
          </form>
        )}

        {/* Upload in progress */}
        {isUploading && state.file && (
          <div className="file-upload-progress">
            <div className="file-upload-file-info">
              <FileText size={20} />
              <div>
                <strong>{state.file.name}</strong>
                <span>{formatSize(state.file.size)}</span>
              </div>
            </div>

            <div className="file-upload-bar-container">
              <div className="file-upload-bar" style={{ width: `${state.progress}%` }} />
            </div>
            <div className="file-upload-stats">
              <span>{state.progress}%</span>
              <span>{state.speed}</span>
              {state.status === 'paused' && <span className="file-upload-paused-label">{t('upload.paused')}</span>}
            </div>

            <div className="file-upload-actions">
              <button className="file-upload-btn" onClick={togglePause} data-tooltip={state.status === 'paused' ? t('upload.resume') : t('upload.pause')}>
                {state.status === 'paused' ? <Play size={16} /> : <Pause size={16} />}
                {state.status === 'paused' ? t('upload.resume') : t('upload.pause')}
              </button>
              <button className="file-upload-btn file-upload-btn-danger" onClick={cancelUpload}>
                <X size={16} />
                {t('upload.cancel')}
              </button>
            </div>
          </div>
        )}

        {/* Completed */}
        {state.status === 'completed' && (
          <div className="file-upload-result file-upload-success">
            <CheckCircle size={24} />
            <div>
              <strong>{t('upload.complete')}</strong>
              <p>{t('upload.queued', { filename: state.file?.name })}</p>
            </div>
            <button className="file-upload-btn" onClick={cancelUpload}>{t('upload.another')}</button>
          </div>
        )}

        {/* Error */}
        {state.status === 'error' && (
          <div className="file-upload-result file-upload-error">
            <AlertCircle size={24} />
            <div>
              <strong>{t('upload.failed')}</strong>
              <p>{state.error}</p>
            </div>
            <div className="file-upload-actions">
              <button className="file-upload-btn" onClick={startUpload}>{t('upload.retry')}</button>
              <button className="file-upload-btn" onClick={cancelUpload}>{t('upload.cancel')}</button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
