import { useCallback, useEffect, useRef, useState } from 'react'
import { Upload as UploadIcon, X, Pause, Play, CheckCircle, AlertCircle, FileText, FolderOpen, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import * as tus from 'tus-js-client'
import type { ProductSelection } from './ProductAutocomplete'

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

type FileItemStatus = 'pending' | 'uploading' | 'paused' | 'completed' | 'error'

interface FileItem {
  id: string
  file: File
  progress: number
  speed: string
  status: FileItemStatus
  error: string
  uploadInstance: tus.Upload | null
}

const CHUNK_SIZE = 10 * 1024 * 1024
const MAX_CONCURRENT = 3

const ALLOWED_EXTENSIONS = new Set([
  '.md', '.txt', '.pdf', '.json', '.yaml', '.yml',
  '.proto', '.wsdl', '.xml',
  '.zip', '.7z', '.tar', '.tar.gz', '.tgz', '.tar.bz2', '.tar.xz', '.rar',
])

function getExtension(name: string): string {
  const lower = name.toLowerCase()
  for (const ext of ['.tar.gz', '.tar.bz2', '.tar.xz']) {
    if (lower.endsWith(ext)) return ext
  }
  const dot = lower.lastIndexOf('.')
  return dot >= 0 ? lower.slice(dot) : ''
}

function isAllowedFile(file: File): boolean {
  return ALLOWED_EXTENSIONS.has(getExtension(file.name))
}

let nextId = 0

export function FileUpload({ onComplete, onClose, productContext }: FileUploadProps) {
  const { t } = useTranslation()

  const [files, setFiles] = useState<FileItem[]>([])
  const [globalStatus, setGlobalStatus] = useState<'selecting' | 'uploading' | 'done'>('selecting')

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
  const folderInputRef = useRef<HTMLInputElement>(null)
  const startTimesRef = useRef<Record<string, number>>({})
  const activeCountRef = useRef(0)
  const filesRef = useRef(files)
  filesRef.current = files

  const addFiles = useCallback((incoming: FileList | File[]) => {
    const arr = Array.from(incoming).filter(isAllowedFile)
    if (arr.length === 0) return

    const newItems: FileItem[] = arr.map(file => ({
      id: `f-${++nextId}`,
      file,
      progress: 0,
      speed: '',
      status: 'pending',
      error: '',
      uploadInstance: null,
    }))

    setFiles(prev => [...prev, ...newItems])
  }, [])

  const removeFile = useCallback((id: string) => {
    setFiles(prev => {
      const item = prev.find(f => f.id === id)
      if (item?.uploadInstance) item.uploadInstance.abort(true)
      return prev.filter(f => f.id !== id)
    })
  }, [])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragOver(false)

    const items = e.dataTransfer.items
    if (items) {
      const filePromises: Promise<File>[] = []
      const traverse = (entry: FileSystemEntry): Promise<void> => {
        if (entry.isFile) {
          return new Promise(resolve => {
            ;(entry as FileSystemFileEntry).file(f => {
              filePromises.push(Promise.resolve(f))
              resolve()
            })
          })
        } else if (entry.isDirectory) {
          return new Promise(resolve => {
            const reader = (entry as FileSystemDirectoryEntry).createReader()
            reader.readEntries(async entries => {
              await Promise.all(entries.map(traverse))
              resolve()
            })
          })
        }
        return Promise.resolve()
      }

      const entries: FileSystemEntry[] = []
      for (let i = 0; i < items.length; i++) {
        const entry = items[i].webkitGetAsEntry()
        if (entry) entries.push(entry)
      }

      Promise.all(entries.map(traverse)).then(async () => {
        const resolvedFiles = await Promise.all(filePromises)
        addFiles(resolvedFiles)
      })
    } else {
      addFiles(e.dataTransfer.files)
    }
  }, [addFiles])

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragOver(true)
  }, [])

  const handleDragLeave = useCallback(() => {
    setIsDragOver(false)
  }, [])

  const updateFile = useCallback((id: string, patch: Partial<FileItem>) => {
    setFiles(prev => prev.map(f => f.id === id ? { ...f, ...patch } : f))
  }, [])

  const startSingleUpload = useCallback((item: FileItem) => {
    startTimesRef.current[item.id] = Date.now()
    activeCountRef.current++

    const upload = new tus.Upload(item.file, {
      endpoint: '/api/v1/uploads/',
      chunkSize: CHUNK_SIZE,
      retryDelays: [0, 1000, 3000, 5000, 10000],
      removeFingerprintOnSuccess: true,
      fingerprint: (_file, _opts) => Promise.resolve(`${item.id}-${Date.now()}`),
      onBeforeRequest: (req) => {
        const xhr = req.getUnderlyingObject() as XMLHttpRequest
        xhr.withCredentials = true
      },
      metadata: {
        filename: item.file.name,
        product_name: productName.trim(),
        firmware_version: firmwareVersion || '1.0',
        manufacturer: manufacturer,
        content_type: item.file.type || 'application/octet-stream',
      },
      onProgress: (bytesUploaded: number, bytesTotal: number) => {
        const pct = Math.round((bytesUploaded / bytesTotal) * 100)
        const elapsed = (Date.now() - (startTimesRef.current[item.id] || Date.now())) / 1000
        const speedMBps = elapsed > 0 ? (bytesUploaded / 1024 / 1024) / elapsed : 0
        updateFile(item.id, {
          progress: pct,
          speed: `${speedMBps.toFixed(1)} MB/s`,
        })
      },
      onSuccess: () => {
        activeCountRef.current--
        updateFile(item.id, { status: 'completed', progress: 100 })
        onComplete?.(0, item.file.name)
        processQueue()
      },
      onError: (error: Error) => {
        activeCountRef.current--
        updateFile(item.id, { status: 'error', error: error.message })
        processQueue()
      },
    })

    updateFile(item.id, { status: 'uploading', uploadInstance: upload })
    upload.start()
  }, [productName, firmwareVersion, manufacturer, onComplete, updateFile])

  const processQueue = useCallback(() => {
    const current = filesRef.current
    if (activeCountRef.current >= MAX_CONCURRENT) return

    const pending = current.filter(f => f.status === 'pending')
    const slots = MAX_CONCURRENT - activeCountRef.current
    pending.slice(0, slots).forEach(item => startSingleUpload(item))
  }, [startSingleUpload])

  const startUpload = useCallback((e?: React.FormEvent) => {
    e?.preventDefault()
    if (files.length === 0 || !productName.trim()) return
    setGlobalStatus('uploading')
    activeCountRef.current = 0
    processQueue()
  }, [files, productName, processQueue])

  useEffect(() => {
    if (globalStatus !== 'uploading') return
    const allDone = files.length > 0 && files.every(f => f.status === 'completed' || f.status === 'error')
    if (allDone) setGlobalStatus('done')
  }, [files, globalStatus])

  const togglePause = useCallback((id: string) => {
    const item = files.find(f => f.id === id)
    if (!item?.uploadInstance) return

    if (item.status === 'uploading') {
      item.uploadInstance.abort()
      updateFile(id, { status: 'paused' })
    } else if (item.status === 'paused') {
      item.uploadInstance.start()
      updateFile(id, { status: 'uploading' })
    }
  }, [files, updateFile])

  const cancelAll = useCallback(() => {
    files.forEach(f => {
      if (f.uploadInstance) f.uploadInstance.abort(true)
    })
    setFiles([])
    setGlobalStatus('selecting')
    activeCountRef.current = 0
  }, [files])

  const resetToSelect = useCallback(() => {
    setFiles([])
    setGlobalStatus('selecting')
    activeCountRef.current = 0
  }, [])

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

  const completedCount = files.filter(f => f.status === 'completed').length
  const errorCount = files.filter(f => f.status === 'error').length
  const totalCount = files.length
  const overallProgress = totalCount > 0
    ? Math.round(files.reduce((s, f) => s + f.progress, 0) / totalCount)
    : 0

  return (
    <div className="file-upload-overlay">
      <div className="file-upload-modal">
        <div className="file-upload-header">
          <h3>{t('upload.title')}</h3>
          {onClose && (
            <button className="file-upload-close" onClick={onClose}>
              <X size={18} />
            </button>
          )}
        </div>

        {/* Drop zone — always visible in selecting mode */}
        {globalStatus === 'selecting' && (
          <>
            <div
              className={`file-upload-dropzone ${isDragOver ? 'dragover' : ''} ${files.length > 0 ? 'compact' : ''}`}
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
            >
              {files.length === 0 && <UploadIcon size={32} />}
              {files.length === 0 && <p>{t('upload.dropzoneMulti')}</p>}
              <div className="file-upload-browse-row">
                <button
                  type="button"
                  className="file-upload-browse"
                  onClick={() => fileInputRef.current?.click()}
                >
                  {t('upload.browseFiles')}
                </button>
                <button
                  type="button"
                  className="file-upload-browse file-upload-browse-folder"
                  onClick={() => folderInputRef.current?.click()}
                >
                  <FolderOpen size={16} />
                  {t('upload.browseFolder')}
                </button>
              </div>
              {files.length === 0 && (
                <span className="file-upload-hint">
                  {t('upload.formats')}
                </span>
              )}
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept=".md,.txt,.pdf,.json,.yaml,.yml,.proto,.wsdl,.xml,.zip,.7z,.tar,.tar.gz,.tgz,.tar.bz2,.tar.xz,.rar"
                style={{ display: 'none' }}
                onChange={e => {
                  if (e.target.files) addFiles(e.target.files)
                  e.target.value = ''
                }}
              />
              <input
                ref={folderInputRef}
                type="file"
                // @ts-expect-error webkitdirectory is non-standard
                webkitdirectory=""
                directory=""
                multiple
                style={{ display: 'none' }}
                onChange={e => {
                  if (e.target.files) addFiles(e.target.files)
                  e.target.value = ''
                }}
              />
            </div>

            {/* Selected files list */}
            {files.length > 0 && (
              <form className="file-upload-form" onSubmit={startUpload}>
                <div className="file-upload-filelist">
                  <div className="file-upload-filelist-header">
                    <span>{t('upload.filesSelected', { count: files.length })}</span>
                    <span className="file-upload-total-size">
                      {formatSize(files.reduce((s, f) => s + f.file.size, 0))}
                    </span>
                  </div>
                  <div className="file-upload-filelist-items">
                    {files.map(item => (
                      <div key={item.id} className="file-upload-filelist-item">
                        <FileText size={14} />
                        <span className="file-upload-filelist-name" title={item.file.name}>{item.file.name}</span>
                        <span className="file-upload-filelist-size">{formatSize(item.file.size)}</span>
                        <button type="button" className="file-upload-remove" onClick={() => removeFile(item.id)}>
                          <Trash2 size={14} />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="file-upload-fields">
                  <label>
                    {t('upload.productOrCreate')}
                    <input
                      type="text"
                      value={productSel.productName}
                      onChange={e => setProductSel(prev => ({ ...prev, productName: e.target.value, isExisting: false, productId: undefined }))}
                      placeholder={t('upload.productPlaceholder')}
                      autoFocus={!hasProductContext}
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
                        autoFocus={hasProductContext}
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
                  disabled={!productName.trim()}
                >
                  <UploadIcon size={16} />
                  {t('upload.startAll', { count: files.length })}
                </button>
              </form>
            )}
          </>
        )}

        {/* Upload in progress */}
        {globalStatus === 'uploading' && (
          <div className="file-upload-progress">
            <div className="file-upload-overall">
              <div className="file-upload-bar-container">
                <div className="file-upload-bar" style={{ width: `${overallProgress}%` }} />
              </div>
              <div className="file-upload-stats">
                <span>{overallProgress}%</span>
                <span>{completedCount}/{totalCount} {t('upload.filesCompleted')}</span>
              </div>
            </div>

            <div className="file-upload-filelist-items file-upload-filelist-progress">
              {files.map(item => (
                <div key={item.id} className={`file-upload-progress-item file-upload-progress-item--${item.status}`}>
                  <div className="file-upload-progress-item-header">
                    {item.status === 'completed' ? <CheckCircle size={14} /> :
                      item.status === 'error' ? <AlertCircle size={14} /> :
                        <FileText size={14} />}
                    <span className="file-upload-filelist-name" title={item.file.name}>{item.file.name}</span>
                    <span className="file-upload-filelist-size">{formatSize(item.file.size)}</span>
                    {(item.status === 'uploading' || item.status === 'paused') && (
                      <button type="button" className="file-upload-mini-btn" onClick={() => togglePause(item.id)}>
                        {item.status === 'paused' ? <Play size={12} /> : <Pause size={12} />}
                      </button>
                    )}
                  </div>
                  {(item.status === 'uploading' || item.status === 'paused') && (
                    <div className="file-upload-bar-container file-upload-bar-small">
                      <div className="file-upload-bar" style={{ width: `${item.progress}%` }} />
                    </div>
                  )}
                  {item.status === 'uploading' && item.speed && (
                    <span className="file-upload-item-speed">{item.progress}% · {item.speed}</span>
                  )}
                  {item.status === 'paused' && (
                    <span className="file-upload-paused-label">{t('upload.paused')}</span>
                  )}
                  {item.status === 'error' && (
                    <span className="file-upload-item-error">{item.error}</span>
                  )}
                </div>
              ))}
            </div>

            <div className="file-upload-actions">
              <button className="file-upload-btn file-upload-btn-danger" onClick={cancelAll}>
                <X size={16} />
                {t('upload.cancelAll')}
              </button>
            </div>
          </div>
        )}

        {/* All done */}
        {globalStatus === 'done' && (
          <div className="file-upload-done">
            <div className="file-upload-done-summary">
              <CheckCircle size={24} />
              <div>
                <strong>{t('upload.allDone')}</strong>
                <p>{t('upload.allDoneSummary', { completed: completedCount, total: totalCount, errors: errorCount })}</p>
              </div>
            </div>
            {errorCount > 0 && (
              <div className="file-upload-filelist-items file-upload-filelist-progress">
                {files.filter(f => f.status === 'error').map(item => (
                  <div key={item.id} className="file-upload-progress-item file-upload-progress-item--error">
                    <div className="file-upload-progress-item-header">
                      <AlertCircle size={14} />
                      <span className="file-upload-filelist-name">{item.file.name}</span>
                    </div>
                    <span className="file-upload-item-error">{item.error}</span>
                  </div>
                ))}
              </div>
            )}
            <div className="file-upload-actions">
              <button className="file-upload-btn" onClick={resetToSelect}>{t('upload.another')}</button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
