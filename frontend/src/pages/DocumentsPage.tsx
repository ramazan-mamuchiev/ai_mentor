import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'
import {
  FileText,
  Upload,
  Globe,
  RefreshCw,
  CloudDownload,
  Trash2,
  Clock,
  Loader2,
  CheckCircle,
  AlertCircle,
  Search,
  X,
  Bug,
  Ban,
  ExternalLink,
  Eye,
  MoreHorizontal,
  Key,
  Activity,
  FileSearch,
  ChevronRight,
  Play,
  Pencil,
} from 'lucide-react'
import type { ColumnDef, ColumnFiltersState, FilterFn } from '@tanstack/react-table'
import { listDocuments, deleteDocument, reingestDocument, cancelDocument, analyzeDocumentLifecycle, deleteDocumentLifecycle, updateDocument } from '../api/documents'
import { usePermission } from '../auth/usePermission'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { MarkdownPreviewModal } from '../components/MarkdownPreviewModal'
import { DocsRightPanel } from '../components/DocsRightPanel'
import { SearchKeysModal } from '../components/SearchKeysModal'
import { LifecycleModal } from '../components/LifecycleModal'
import { DataTable } from '../components/DataTable'
import { useDataTable } from '../hooks/useDataTable'
import type { DocumentListItem, DocumentStatusValue } from '../types'

const POLL_INTERVAL = 2000
const STORAGE_KEY = 'lexiro-docs-table'

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${(bytes / Math.pow(k, i)).toFixed(i > 0 ? 1 : 0)} ${sizes[i]}`
}

function formatDateCompact(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}

function formatDateTimeFull(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleString(undefined, {
    day: 'numeric', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}

function isUrl(value: string): boolean {
  return /^https?:\/\//.test(value)
}

function getDomainLabel(url: string): string {
  try {
    return new URL(url).hostname
  } catch {
    return url
  }
}

function StatusBadge({
  status,
  errorMessage,
  progressPercent = 0,
  progressStage = '',
  onCancel,
}: {
  status: DocumentStatusValue
  errorMessage?: string | null
  progressPercent?: number
  progressStage?: string
  onCancel?: () => void
}) {
  const { t } = useTranslation()
  const icons: Record<DocumentStatusValue, React.ReactNode> = {
    pending: <Clock size={14} />,
    processing: <Loader2 size={14} className="spin-icon" />,
    ready: <CheckCircle size={14} />,
    error: <AlertCircle size={14} />,
    cancelled: <Ban size={14} />,
  }

  const stageLabel = progressStage ? t(`docs.stage.${progressStage}`, progressStage) : ''
  const pct = status === 'processing' ? Math.max(0, Math.min(100, progressPercent)) : 0
  const canCancel = onCancel && (status === 'pending' || status === 'processing')

  return (
    <div className="docs-status-wrap">
      <div className="docs-status-row">
        <span
          className={`docs-status docs-status--${status}`}
          title={status === 'error' && errorMessage ? errorMessage : undefined}
        >
          {icons[status]}
          {t(`docs.status.${status}`)}
        </span>
        {canCancel && (
          <button
            className="docs-status-cancel"
            onClick={e => { e.stopPropagation(); onCancel() }}
          >
            <X size={14} />
          </button>
        )}
      </div>
      {status === 'processing' && (
        <>
          <div className="docs-progress-bar">
            <div
              className="docs-progress-fill docs-progress-fill--processing"
              style={pct > 0 ? { width: `${pct}%`, animation: 'none' } : undefined}
            />
          </div>
          {(pct > 0 || stageLabel) && (
            <div className="docs-progress-info">
              {pct > 0 && <span className="docs-progress-pct">{pct}%</span>}
              {stageLabel && <span className="docs-progress-stage">{stageLabel}</span>}
            </div>
          )}
        </>
      )}
      {status === 'pending' && (
        <div className="docs-progress-bar">
          <div className="docs-progress-fill docs-progress-fill--pending" />
        </div>
      )}
      {status === 'error' && errorMessage && (
        <div className="docs-error-hint" title={errorMessage}>
          {errorMessage.length > 60 ? errorMessage.slice(0, 60) + '…' : errorMessage}
        </div>
      )}
    </div>
  )
}

function LifecycleStatusIcon({ status }: { status?: string }) {
  const { t } = useTranslation()
  if (!status) return null
  if (status === 'pending' || status === 'processing')
    return (
      <span className="docs-lc-icon docs-lc-icon--pending" title={t('docs.lifecycle.statusPending')}>
        <Loader2 size={13} className="spin-icon" />
      </span>
    )
  if (status === 'ready')
    return (
      <span className="docs-lc-icon docs-lc-icon--ready" title={t('docs.lifecycle.statusReady')}>
        <Activity size={13} />
      </span>
    )
  if (status === 'error')
    return (
      <span className="docs-lc-icon docs-lc-icon--error" title={t('docs.lifecycle.statusError')}>
        <AlertCircle size={13} />
      </span>
    )
  return null
}

function OverflowCell({ children, className }: { children: React.ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const [truncated, setTruncated] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    setTruncated(el.scrollWidth > el.clientWidth || el.scrollHeight > el.clientHeight)
  })

  return (
    <div
      ref={ref}
      className={`docs-cell-overflow${className ? ` ${className}` : ''}`}
      title={truncated && typeof children === 'string' ? children : undefined}
    >
      {children}
    </div>
  )
}

const _PLACEHOLDER_FORMATS = new Set(['site', 'confluence', 'github', 'url'])

function isLinkedDoc(doc: DocumentListItem): boolean {
  return _PLACEHOLDER_FORMATS.has(doc.format)
    || (!!doc.source_path && doc.source_path.startsWith('http'))
}

const docGlobalFilter: FilterFn<DocumentListItem> = (row, _columnId, filterValue) => {
  const q = String(filterValue).toLowerCase()
  if (!q) return true
  const d = row.original
  return (
    d.title.toLowerCase().includes(q) ||
    d.original_filename.toLowerCase().includes(q) ||
    (d.source_container || '').toLowerCase().includes(q) ||
    (d.source_path || '').toLowerCase().includes(q)
  )
}

function LifecycleSubmenu({
  doc, onAnalyzeLifecycle, onViewLifecycle, onDeleteLifecycle, onClose,
}: {
  doc: DocumentListItem
  onAnalyzeLifecycle?: (d: DocumentListItem) => void
  onViewLifecycle?: (d: DocumentListItem) => void
  onDeleteLifecycle?: (d: DocumentListItem) => void
  onClose: () => void
}) {
  const { t } = useTranslation()
  const wrapperRef = useRef<HTMLDivElement>(null)
  const subRef = useRef<HTMLDivElement>(null)
  const [subOpen, setSubOpen] = useState(false)
  const [flipLeft, setFlipLeft] = useState(false)

  useEffect(() => {
    if (!subOpen || !wrapperRef.current || !subRef.current) return
    const wrapperRect = wrapperRef.current.getBoundingClientRect()
    const subW = subRef.current.offsetWidth || 200
    const spaceRight = window.innerWidth - wrapperRect.right
    setFlipLeft(spaceRight < subW + 8)
  }, [subOpen])

  return (
    <div
      ref={wrapperRef}
      className="docs-actions-submenu-wrapper"
      onMouseEnter={() => setSubOpen(true)}
      onMouseLeave={() => setSubOpen(false)}
    >
      <button className="docs-actions-dropdown-item docs-actions-submenu-trigger">
        <Activity size={15} />
        API Lifecycle
        <ChevronRight size={13} className="docs-actions-submenu-arrow" />
      </button>
      {subOpen && (
        <div
          ref={subRef}
          className={`docs-actions-submenu${flipLeft ? ' docs-actions-submenu--left' : ''}`}
        >
          {onAnalyzeLifecycle && (
            <button className="docs-actions-dropdown-item" onClick={() => { onAnalyzeLifecycle(doc); onClose() }}>
              <Play size={14} />
              {t('docs.actions.analyzeLifecycle')}
            </button>
          )}
          {onViewLifecycle && (
            <button className="docs-actions-dropdown-item" onClick={() => { onViewLifecycle(doc); onClose() }}>
              <FileSearch size={14} />
              {t('docs.actions.viewLifecycle')}
            </button>
          )}
          {doc.lifecycle_status === 'ready' && onDeleteLifecycle && (
            <button className="docs-actions-dropdown-item docs-actions-dropdown-item--danger" onClick={() => { onDeleteLifecycle(doc); onClose() }}>
              <Trash2 size={14} />
              {t('docs.actions.deleteLifecycle')}
            </button>
          )}
        </div>
      )}
    </div>
  )
}

function RenameDialog({
  currentTitle,
  originalFilename,
  onConfirm,
  onCancel,
}: {
  currentTitle: string
  originalFilename: string
  onConfirm: (value: string) => void
  onCancel: () => void
}) {
  const { t } = useTranslation()
  const inputRef = useRef<HTMLInputElement>(null)
  const [canSave, setCanSave] = useState(false)

  useEffect(() => {
    const timer = setTimeout(() => {
      inputRef.current?.focus()
      inputRef.current?.select()
    }, 50)
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel()
    }
    window.addEventListener('keydown', handleKey)
    return () => { clearTimeout(timer); window.removeEventListener('keydown', handleKey) }
  }, [onCancel])

  const validate = () => {
    const v = inputRef.current?.value.trim() ?? ''
    setCanSave(v.length > 0 && v !== currentTitle)
  }

  const handleSubmit = () => {
    if (!canSave) return
    onConfirm(inputRef.current?.value ?? currentTitle)
  }

  return createPortal(
    <div className="confirm-overlay" onClick={onCancel}>
      <div
        className="confirm-dialog"
        onClick={e => e.stopPropagation()}
        role="dialog"
        aria-labelledby="rename-title"
      >
        <button className="confirm-close" onClick={onCancel} aria-label="Close">
          <X size={16} />
        </button>

        <div className="confirm-icon confirm-icon--default">
          <Pencil size={24} />
        </div>

        <h3 id="rename-title" className="confirm-title">{t('docs.rename.title')}</h3>

        <input
          ref={inputRef}
          className="rename-dialog-input"
          defaultValue={currentTitle}
          onChange={validate}
          onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); handleSubmit() } }}
        />
        {originalFilename && originalFilename !== currentTitle && (
          <div className="rename-dialog-hint">{originalFilename}</div>
        )}

        <div className="confirm-actions">
          <button className="confirm-btn confirm-btn--cancel" onClick={onCancel}>
            {t('docs.rename.cancel')}
          </button>
          <button className="confirm-btn confirm-btn--default" onClick={handleSubmit} disabled={!canSave}>
            {t('docs.rename.confirm')}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  )
}

function DocActions({
  doc,
  onDebug,
  onPreview,
  onReingest,
  onSync,
  onDelete,
  onRename,
  onSearchKeys,
  onAnalyzeLifecycle,
  onViewLifecycle,
  onDeleteLifecycle,
}: {
  doc: DocumentListItem
  onDebug?: (d: DocumentListItem) => void
  onPreview: (d: DocumentListItem) => void
  onReingest?: (d: DocumentListItem) => void
  onSync?: (d: DocumentListItem) => void
  onDelete?: (d: DocumentListItem) => void
  onRename?: (d: DocumentListItem) => void
  onSearchKeys?: (d: DocumentListItem) => void
  onAnalyzeLifecycle?: (d: DocumentListItem) => void
  onViewLifecycle?: (d: DocumentListItem) => void
  onDeleteLifecycle?: (d: DocumentListItem) => void
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const btnRef = useRef<HTMLButtonElement>(null)
  const dropRef = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<{ top: number; left: number }>({ top: -9999, left: -9999 })

  useEffect(() => {
    if (!open) return
    const onMouseDown = (e: MouseEvent) => {
      if (dropRef.current && !dropRef.current.contains(e.target as Node) &&
          btnRef.current && !btnRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    const onScroll = () => setOpen(false)
    document.addEventListener('mousedown', onMouseDown)
    document.addEventListener('keydown', onKey)
    document.addEventListener('scroll', onScroll, true)
    return () => {
      document.removeEventListener('mousedown', onMouseDown)
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('scroll', onScroll, true)
    }
  }, [open])

  useEffect(() => {
    if (!open || !dropRef.current || !btnRef.current) return
    const rect = btnRef.current.getBoundingClientRect()
    const dropRect = dropRef.current.getBoundingClientRect()
    const dropW = dropRect.width || 200
    const dropH = dropRect.height
    let left = rect.right - dropW
    if (left < 8) left = 8
    if (left + dropW > window.innerWidth - 8) left = window.innerWidth - dropW - 8
    const top = (rect.bottom + 4 + dropH > window.innerHeight)
      ? rect.top - dropH - 4
      : rect.bottom + 4
    setPos({ top, left })
  }, [open])

  const isLinked = isLinkedDoc(doc)
  const isPlaceholder = _PLACEHOLDER_FORMATS.has(doc.format)
  const canAct = doc.status === 'ready' || doc.status === 'error' || doc.status === 'cancelled'

  const handleToggle = useCallback(() => {
    if (!open) setPos({ top: -9999, left: -9999 })
    setOpen(v => !v)
  }, [open])

  return (
    <div className="docs-actions">
      {doc.status === 'ready' && (
        <button
          className="docs-action-btn"
          onClick={() => onPreview(doc)}
          aria-label={t('docs.actions.previewMd')}
        >
          <Eye size={16} />
        </button>
      )}
      <button
        ref={btnRef}
        className="docs-action-btn"
        onClick={handleToggle}
      >
        <MoreHorizontal size={16} />
      </button>
      {open && createPortal(
        <div ref={dropRef} className="docs-actions-dropdown" style={{ top: pos.top, left: pos.left }}>
          {onRename && (
            <button className="docs-actions-dropdown-item" onClick={() => { onRename(doc); setOpen(false) }}>
              <Pencil size={15} />
              {t('docs.actions.rename')}
            </button>
          )}
          {doc.status === 'ready' && onDebug && (
            <button className="docs-actions-dropdown-item" onClick={() => { onDebug(doc); setOpen(false) }}>
              <Bug size={15} />
              {t('docs.actions.debug')}
            </button>
          )}
          {canAct && !isPlaceholder && onReingest && (
            <button className="docs-actions-dropdown-item" onClick={() => { onReingest(doc); setOpen(false) }}>
              <RefreshCw size={15} />
              {t('docs.actions.reindex')}
            </button>
          )}
          {canAct && isLinked && onSync && (
            <button className="docs-actions-dropdown-item" onClick={() => { onSync(doc); setOpen(false) }}>
              <CloudDownload size={15} />
              {t('docs.actions.sync')}
            </button>
          )}
          {doc.status === 'ready' && onSearchKeys && (
            <button className="docs-actions-dropdown-item" onClick={() => { onSearchKeys(doc); setOpen(false) }}>
              <Key size={15} />
              {t('docs.actions.searchKeys')}
            </button>
          )}
          {doc.status === 'ready' && (onAnalyzeLifecycle || onViewLifecycle) && (
            <LifecycleSubmenu
              doc={doc}
              onAnalyzeLifecycle={onAnalyzeLifecycle}
              onViewLifecycle={onViewLifecycle}
              onDeleteLifecycle={onDeleteLifecycle}
              onClose={() => setOpen(false)}
            />
          )}
          {onDelete && (
            <button className="docs-actions-dropdown-item docs-actions-dropdown-item--danger" onClick={() => { onDelete(doc); setOpen(false) }}>
              <Trash2 size={15} />
              {t('docs.actions.delete')}
            </button>
          )}
        </div>,
        document.body
      )}
    </div>
  )
}

interface Props {
  onUploadClick?: () => void
  onUrlImportClick?: () => void
  refreshKey?: number
  productId?: number
  headerSlot?: React.ReactNode
}

const DEFAULT_COLUMN_ORDER = ['title', 'format', 'status', 'size', 'chunks', 'product', 'uploaded', 'indexed', 'actions']

export function DocumentsPage({ onUploadClick, onUrlImportClick, refreshKey, productId, headerSlot }: Props) {
  const { t } = useTranslation()
  const canDebug = usePermission('debug')
  const canLifecycle = usePermission('lifecycle.run')
  const canDelete = usePermission('documents.delete')
  const canReindex = usePermission('documents.reindex')
  const canSync = usePermission('documents.sync')
  const [documents, setDocuments] = useState<DocumentListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [deleteTarget, setDeleteTarget] = useState<DocumentListItem | null>(null)
  const [reingestTarget, setReingestTarget] = useState<DocumentListItem | null>(null)
  const [syncTarget, setSyncTarget] = useState<DocumentListItem | null>(null)
  const [cancelTarget, setCancelTarget] = useState<DocumentListItem | null>(null)
  const [deleteLcTarget, setDeleteLcTarget] = useState<DocumentListItem | null>(null)
  const [previewTarget, setPreviewTarget] = useState<DocumentListItem | null>(null)
  const [globalFilter, setGlobalFilter] = useState('')
  const [debugPanel, setDebugPanel] = useState<DocumentListItem | null>(null)
  const [searchKeysTarget, setSearchKeysTarget] = useState<DocumentListItem | null>(null)
  const [lifecycleTarget, setLifecycleTarget] = useState<DocumentListItem | null>(null)
  const [renameTarget, setRenameTarget] = useState<{ id: number; title: string; originalFilename: string } | null>(null)
  const [toast, setToast] = useState<{ message: string; variant: 'success' | 'error' | 'info' } | null>(null)
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [formatFilter, setFormatFilter] = useState<Set<string>>(new Set())
  const [statusFilter, setStatusFilter] = useState<Set<string>>(new Set())
  const [lifecycleFilter, setLifecycleFilter] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const searchRef = useRef<HTMLInputElement>(null)

  const showToast = useCallback((message: string, variant: 'success' | 'error' | 'info') => {
    if (toastTimer.current) clearTimeout(toastTimer.current)
    setToast({ message, variant })
    toastTimer.current = setTimeout(() => setToast(null), 4000)
  }, [])

  const fetchDocs = useCallback(async () => {
    try {
      const docs = await listDocuments(productId)
      setDocuments(docs)
    } catch {
      // keep previous state
    } finally {
      setLoading(false)
    }
  }, [productId])

  useEffect(() => { fetchDocs() }, [fetchDocs, refreshKey])

  useEffect(() => {
    const hasPending = documents.some(d =>
      d.status === 'pending' || d.status === 'processing' ||
      d.lifecycle_status === 'pending' || d.lifecycle_status === 'processing'
    )
    if (hasPending) {
      pollRef.current = setInterval(fetchDocs, POLL_INTERVAL)
    }
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [documents, fetchDocs])

  const handleDeleteConfirm = useCallback(async () => {
    if (!deleteTarget) return
    try {
      await deleteDocument(deleteTarget.id)
      setDocuments(prev => prev.filter(d => d.id !== deleteTarget.id))
    } catch { /* ignore */ }
    finally { setDeleteTarget(null) }
  }, [deleteTarget])

  const _setDocPending = useCallback((docId: number) => {
    setDocuments(prev =>
      prev.map(d => d.id === docId ? { ...d, status: 'pending' as const, error_message: null, total_chunks: 0, progress_percent: 0, progress_stage: '' } : d)
    )
  }, [])

  const handleReingestConfirm = useCallback(async () => {
    if (!reingestTarget) return
    const id = reingestTarget.id
    setReingestTarget(null)
    _setDocPending(id)
    try {
      await reingestDocument(id, true)
    } catch (err) {
      const detail = err instanceof Error ? err.message : String(err)
      if (detail.includes('409') || detail.includes('already being processed')) {
        alert(t('docs.conflict'))
      } else {
        alert(`${t('docs.reingest.error')}: ${detail}`)
      }
    }
  }, [reingestTarget, t, _setDocPending])

  const handleSyncConfirm = useCallback(async () => {
    if (!syncTarget) return
    const id = syncTarget.id
    setSyncTarget(null)
    _setDocPending(id)
    try {
      await reingestDocument(id, false)
    } catch (err) {
      const detail = err instanceof Error ? err.message : String(err)
      if (detail.includes('409') || detail.includes('already being processed')) {
        alert(t('docs.conflict'))
      } else {
        alert(`${t('docs.sync.error')}: ${detail}`)
      }
    }
  }, [syncTarget, t, _setDocPending])

  const handleCancelConfirm = useCallback(async () => {
    if (!cancelTarget) return
    try {
      await cancelDocument(cancelTarget.id)
      setDocuments(prev =>
        prev.map(d => d.id === cancelTarget.id ? { ...d, status: 'cancelled' as const, progress_percent: 0, progress_stage: '', error_message: null } : d)
      )
    } catch { /* ignore */ }
    finally { setCancelTarget(null) }
  }, [cancelTarget])

  const openDebug = useCallback((doc: DocumentListItem) => {
    setDebugPanel(doc)
  }, [])

  const handleAnalyzeLifecycle = useCallback(async (doc: DocumentListItem) => {
    try {
      await analyzeDocumentLifecycle(doc.id)
      setDocuments(prev => prev.map(d => d.id === doc.id ? { ...d, lifecycle_status: 'pending' } : d))
      showToast(t('docs.lifecycle.started', { title: doc.title }), 'success')
    } catch {
      showToast(t('docs.lifecycle.error'), 'error')
    }
  }, [showToast, t])

  const handleDeleteLifecycle = useCallback((doc: DocumentListItem) => {
    setDeleteLcTarget(doc)
  }, [])

  const handleDeleteLcConfirm = useCallback(async () => {
    if (!deleteLcTarget) return
    try {
      await deleteDocumentLifecycle(deleteLcTarget.id)
      setDocuments(prev => prev.map(d => d.id === deleteLcTarget.id ? { ...d, lifecycle_status: '' } : d))
      showToast(t('docs.lifecycle.deleted', { title: deleteLcTarget.title }), 'success')
    } catch {
      showToast(t('docs.lifecycle.deleteError'), 'error')
    } finally {
      setDeleteLcTarget(null)
    }
  }, [deleteLcTarget, showToast, t])

  const handleRenameStart = useCallback((doc: DocumentListItem) => {
    setRenameTarget({ id: doc.id, title: doc.title, originalFilename: doc.original_filename })
  }, [])

  const handleRenameConfirm = useCallback(async (newTitle: string) => {
    if (!renameTarget) return
    const trimmed = newTitle.trim()
    if (!trimmed || trimmed === renameTarget.title) {
      setRenameTarget(null)
      return
    }
    try {
      await updateDocument(renameTarget.id, { title: trimmed })
      setDocuments(prev =>
        prev.map(d => d.id === renameTarget.id ? { ...d, title: trimmed } : d)
      )
    } catch {
      showToast(t('docs.rename.error'), 'error')
    } finally {
      setRenameTarget(null)
    }
  }, [renameTarget, showToast, t])

  const closeDebug = useCallback(() => {
    setDebugPanel(null)
  }, [])

  const formatCounts = useMemo(() => {
    const map = new Map<string, number>()
    for (const d of documents) {
      map.set(d.format, (map.get(d.format) ?? 0) + 1)
    }
    return [...map.entries()].sort((a, b) => b[1] - a[1])
  }, [documents])

  const statusCounts = useMemo(() => {
    const map = new Map<string, number>()
    for (const d of documents) {
      map.set(d.status, (map.get(d.status) ?? 0) + 1)
    }
    return [...map.entries()].sort((a, b) => b[1] - a[1])
  }, [documents])

  const lifecycleReadyCount = useMemo(() =>
    documents.filter(d => d.lifecycle_status === 'ready').length
  , [documents])

  const toggleFilter = useCallback((setter: React.Dispatch<React.SetStateAction<Set<string>>>, value: string) => {
    setter(prev => {
      const next = new Set(prev)
      if (next.has(value)) next.delete(value)
      else next.add(value)
      return next
    })
  }, [])

  const clearFilters = useCallback(() => {
    setFormatFilter(new Set())
    setStatusFilter(new Set())
    setLifecycleFilter(false)
  }, [])

  const hasActiveFilters = formatFilter.size > 0 || statusFilter.size > 0 || lifecycleFilter

  const columnFilters = useMemo<ColumnFiltersState>(() => {
    const filters: ColumnFiltersState = []
    if (formatFilter.size > 0) filters.push({ id: 'format', value: formatFilter })
    if (statusFilter.size > 0) filters.push({ id: 'status', value: statusFilter })
    if (lifecycleFilter) filters.push({ id: 'title', value: 'lifecycle_ready' })
    return filters
  }, [formatFilter, statusFilter, lifecycleFilter])

  const columns = useMemo<ColumnDef<DocumentListItem, unknown>[]>(() => [
    {
      id: 'title',
      accessorFn: row => row.title,
      header: () => t('docs.table.name'),
      filterFn: (row, _columnId, filterValue) => {
        if (filterValue === 'lifecycle_ready') return row.original.lifecycle_status === 'ready'
        return true
      },
      cell: ({ row }) => {
        const { title, original_filename, source_container, source_path, lifecycle_status } = row.original
        const linkUrl = source_path || source_container
        const sourceIsUrl = linkUrl && isUrl(linkUrl)
        const lcReady = lifecycle_status === 'ready'
        const lcRunning = lifecycle_status === 'pending' || lifecycle_status === 'processing'
        return (
          <div className="docs-name-cell">
            <div className="docs-name-row">
              <OverflowCell className="docs-name">{title}</OverflowCell>
              {lcReady && (
                <button
                  className="docs-lc-badge docs-lc-badge--ready"
                  onClick={e => { e.stopPropagation(); setLifecycleTarget(row.original) }}
                  title={t('docs.actions.viewLifecycle')}
                >
                  <Activity size={10} />
                  API Lifecycle
                </button>
              )}
              {lcRunning && (
                <span className="docs-lc-badge docs-lc-badge--running">
                  <Loader2 size={10} className="spin-icon" />
                  {t('lifecycleModal.running')}
                </span>
              )}
              {lifecycle_status === 'error' && (
                <button
                  className="docs-lc-badge docs-lc-badge--error"
                  onClick={e => { e.stopPropagation(); setLifecycleTarget(row.original) }}
                  title={t('docs.lifecycle.statusError')}
                >
                  <AlertCircle size={10} />
                  Lifecycle
                </button>
              )}
            </div>
            {sourceIsUrl ? (
              <a
                href={linkUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="docs-source-link"
                title={linkUrl}
              >
                {getDomainLabel(linkUrl)}
                <ExternalLink size={10} className="docs-source-link-icon" />
              </a>
            ) : (
              <>
                {original_filename && original_filename !== title && original_filename !== `${title}.md` && (
                  <OverflowCell className="docs-filename">{original_filename}</OverflowCell>
                )}
                {source_container && (
                  <OverflowCell className="docs-source-container">
                    {t('docs.source.from', { source: source_container })}
                  </OverflowCell>
                )}
              </>
            )}
          </div>
        )
      },
      enableGrouping: true,
    },
    {
      id: 'format',
      accessorKey: 'format',
      header: () => t('docs.table.format'),
      cell: ({ getValue, row }) => {
        const lang = row.original.detected_language
        return (
          <span className="docs-format">
            {String(getValue())}
            {lang && <span className="docs-lang-badge" title={lang}>{lang}</span>}
          </span>
        )
      },
      enableGrouping: true,
      filterFn: (row, _columnId, filterValue: Set<string>) =>
        filterValue.size === 0 || filterValue.has(row.original.format),
    },
    {
      id: 'status',
      accessorKey: 'status',
      header: () => t('docs.table.status'),
      cell: ({ row }) => (
        <StatusBadge
          status={row.original.status}
          errorMessage={row.original.error_message}
          progressPercent={row.original.progress_percent}
          progressStage={row.original.progress_stage}
          onCancel={() => setCancelTarget(row.original)}
        />
      ),
      enableGrouping: true,
      filterFn: (row, _columnId, filterValue: Set<string>) =>
        filterValue.size === 0 || filterValue.has(row.original.status),
    },
    {
      id: 'size',
      accessorKey: 'file_size_bytes',
      header: () => t('docs.table.size'),
      cell: ({ getValue }) => <span className="docs-size">{formatBytes(Number(getValue()))}</span>,
      enableGrouping: false,
      sortingFn: 'basic',
    },
    {
      id: 'chunks',
      accessorKey: 'total_chunks',
      header: () => t('docs.table.chunks'),
      cell: ({ getValue }) => <span className="docs-chunks">{Number(getValue()) || '—'}</span>,
      enableGrouping: false,
    },
    {
      id: 'product',
      accessorKey: 'product_name',
      header: () => t('docs.table.product'),
      cell: ({ getValue }) => <OverflowCell className="docs-product">{String(getValue() || '—')}</OverflowCell>,
      enableGrouping: true,
    },
    {
      id: 'uploaded',
      accessorFn: row => row.uploaded_at,
      header: () => t('docs.table.uploaded'),
      cell: ({ getValue }) => {
        const v = getValue() as string | null
        return <span className="docs-date">{formatDateCompact(v)}</span>
      },
      enableGrouping: false,
      sortingFn: 'datetime',
    },
    {
      id: 'indexed',
      accessorFn: row => row.indexed_at,
      header: () => t('docs.table.indexed'),
      cell: ({ getValue }) => {
        const v = getValue() as string | null
        return <span className="docs-date">{formatDateCompact(v)}</span>
      },
      enableGrouping: false,
      sortingFn: 'datetime',
    },
    {
      id: 'actions',
      header: () => t('docs.table.actions'),
      enableSorting: false,
      enableGrouping: false,
      cell: ({ row }) => (
        <DocActions
          doc={row.original}
          onDebug={canDebug ? openDebug : undefined}
          onPreview={setPreviewTarget}
          onReingest={canReindex ? setReingestTarget : undefined}
          onSync={canSync ? setSyncTarget : undefined}
          onDelete={canDelete ? setDeleteTarget : undefined}
          onRename={handleRenameStart}
          onSearchKeys={setSearchKeysTarget}
          onAnalyzeLifecycle={canLifecycle ? handleAnalyzeLifecycle : undefined}
          onViewLifecycle={setLifecycleTarget}
          onDeleteLifecycle={canLifecycle ? handleDeleteLifecycle : undefined}
        />
      ),
    },
  ], [t, openDebug, canDebug, canLifecycle, canDelete, canReindex, canSync, handleAnalyzeLifecycle, handleDeleteLifecycle, handleRenameStart])

  const {
    table,
    columnOrder,
    grouping,
    handleColumnOrderChange,
    removeGrouping,
    toggleGrouping,
    resetSettings,
  } = useDataTable({
    data: documents,
    columns,
    storageKey: STORAGE_KEY,
    defaultColumnOrder: DEFAULT_COLUMN_ORDER,
    defaultSorting: [{ id: 'title', desc: false }],
    getRowId: row => String(row.id),
    columnFilters,
    globalFilter,
    onGlobalFilterChange: setGlobalFilter,
    globalFilterFn: docGlobalFilter,
  })

  const handleResetAll = useCallback(() => {
    resetSettings()
    setGlobalFilter('')
    setFormatFilter(new Set())
    setStatusFilter(new Set())
  }, [resetSettings])

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
          {onUploadClick && (
            <button className="docs-upload-btn" onClick={onUploadClick}>
              <Upload size={16} />
              <span>{t('docs.empty.cta')}</span>
            </button>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className={`docs-page${debugPanel ? ' docs-page--with-panel' : ''}`}>
      <div className="docs-page-main">
      {headerSlot}
      <div className="docs-header">
        <h1 className="docs-page-title">
          <FileText size={20} />
          {t('docs.title')}
        </h1>
        <div className="docs-header-actions">
          <div className="docs-search">
            <Search size={16} />
            <input
              ref={searchRef}
              type="text"
              value={globalFilter}
              onChange={e => setGlobalFilter(e.target.value)}
              placeholder={t('docs.search.placeholder')}
              className="docs-search-input"
            />
            {globalFilter && (
              <button className="docs-search-clear" onClick={() => { setGlobalFilter(''); searchRef.current?.focus() }}>
                <X size={14} />
              </button>
            )}
          </div>
          {onUrlImportClick && (
            <button className="docs-upload-btn docs-upload-btn--secondary" onClick={onUrlImportClick}>
              <Globe size={16} />
              <span>{t('urlImport.button')}</span>
            </button>
          )}
          {onUploadClick && (
            <button className="docs-upload-btn" onClick={onUploadClick}>
              <Upload size={16} />
              <span>{t('docs.upload')}</span>
            </button>
          )}
        </div>
      </div>

      {(formatCounts.length > 1 || statusCounts.length > 1 || lifecycleReadyCount > 0) && (
        <div className="docs-filter-bar">
          {formatCounts.length > 1 && (
            <div className="docs-filter-group">
              <span className="docs-filter-label">{t('docs.filter.format')}:</span>
              <div className="docs-filter-chips">
                {formatCounts.map(([fmt, count]) => (
                  <button
                    key={fmt}
                    className={`docs-filter-chip${formatFilter.has(fmt) ? ' docs-filter-chip--active' : ''}`}
                    onClick={() => toggleFilter(setFormatFilter, fmt)}
                  >
                    {fmt.toUpperCase()}
                    <span className="docs-filter-chip-count">{count}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
          {statusCounts.length > 1 && (
            <div className="docs-filter-group">
              <span className="docs-filter-label">{t('docs.filter.status')}:</span>
              <div className="docs-filter-chips">
                {statusCounts.map(([st, count]) => (
                  <button
                    key={st}
                    className={`docs-filter-chip docs-filter-chip--status-${st}${statusFilter.has(st) ? ' docs-filter-chip--active' : ''}`}
                    onClick={() => toggleFilter(setStatusFilter, st)}
                  >
                    {t(`docs.status.${st}`)}
                    <span className="docs-filter-chip-count">{count}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
          {lifecycleReadyCount > 0 && (
            <div className="docs-filter-group">
              <div className="docs-filter-chips">
                <button
                  className={`docs-filter-chip docs-filter-chip--lifecycle${lifecycleFilter ? ' docs-filter-chip--active' : ''}`}
                  onClick={() => setLifecycleFilter(prev => !prev)}
                >
                  <Activity size={12} />
                  API Lifecycle
                  <span className="docs-filter-chip-count">{lifecycleReadyCount}</span>
                </button>
              </div>
            </div>
          )}
          {hasActiveFilters && (
            <button className="docs-filter-clear" onClick={clearFilters}>
              <X size={14} />
              {t('docs.filter.clear')}
            </button>
          )}
        </div>
      )}

      <DataTable
        table={table}
        columnOrder={columnOrder}
        grouping={grouping}
        onColumnOrderChange={handleColumnOrderChange}
        removeGrouping={removeGrouping}
        toggleGrouping={toggleGrouping}
        resetSettings={handleResetAll}
      />

      {/* Mobile: Cards */}
      <div className="docs-cards">
        {documents
          .filter(doc => {
            if (formatFilter.size > 0 && !formatFilter.has(doc.format)) return false
            if (statusFilter.size > 0 && !statusFilter.has(doc.status)) return false
            if (lifecycleFilter && doc.lifecycle_status !== 'ready') return false
            if (!globalFilter) return true
            const q = globalFilter.toLowerCase()
            return (
              doc.title.toLowerCase().includes(q) ||
              doc.original_filename.toLowerCase().includes(q) ||
              (doc.source_container || '').toLowerCase().includes(q) ||
              (doc.source_path || '').toLowerCase().includes(q)
            )
          })
          .map(doc => {
            const cardLinkUrl = doc.source_path || doc.source_container
            return (
            <div className="docs-card" key={doc.id}>
              <div className="docs-card-header">
                <div className="docs-card-title-row">
                  <span className="docs-card-title">{doc.title}</span>
                  {doc.lifecycle_status === 'ready' && (
                    <button
                      className="docs-lc-badge docs-lc-badge--ready"
                      onClick={() => setLifecycleTarget(doc)}
                      title={t('docs.actions.viewLifecycle')}
                    >
                      <Activity size={10} />
                      API Lifecycle
                    </button>
                  )}
                  {(doc.lifecycle_status === 'pending' || doc.lifecycle_status === 'processing') && (
                    <span className="docs-lc-badge docs-lc-badge--running">
                      <Loader2 size={10} className="spin-icon" />
                      {t('lifecycleModal.running')}
                    </span>
                  )}
                  {doc.lifecycle_status === 'error' && (
                    <button
                      className="docs-lc-badge docs-lc-badge--error"
                      onClick={() => setLifecycleTarget(doc)}
                      title={t('docs.lifecycle.statusError')}
                    >
                      <AlertCircle size={10} />
                      Lifecycle
                    </button>
                  )}
                </div>
                <StatusBadge status={doc.status} errorMessage={doc.error_message} progressPercent={doc.progress_percent} progressStage={doc.progress_stage} onCancel={() => setCancelTarget(doc)} />
              </div>
              {cardLinkUrl && isUrl(cardLinkUrl) && (
                <a
                  href={cardLinkUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="docs-source-link"
                >
                  {getDomainLabel(cardLinkUrl)}
                  <ExternalLink size={10} className="docs-source-link-icon" />
                </a>
              )}
              <div className="docs-card-meta">
                <span>
                  <span className="docs-format">{doc.format}</span>
                  {doc.detected_language && <span className="docs-lang-badge" title={doc.detected_language}>{doc.detected_language}</span>}
                </span>
                <span>{formatBytes(doc.file_size_bytes)}</span>
                {doc.total_chunks > 0 && <span>{t('docs.table.chunks')}: {doc.total_chunks}</span>}
                {doc.product_name && <span>{doc.product_name}</span>}
                <span>{formatDateCompact(doc.uploaded_at)}</span>
              </div>
              <div className="docs-card-actions">
                <button className="docs-action-btn" onClick={() => handleRenameStart(doc)} title={t('docs.actions.rename')}>
                  <Pencil size={16} />
                </button>
                {doc.status === 'ready' && canDebug && (
                  <button
                    className="docs-action-btn"
                    onClick={() => openDebug(doc)}
                  >
                    <Bug size={16} />
                  </button>
                )}
                {doc.status === 'ready' && (
                  <button className="docs-action-btn" onClick={() => setPreviewTarget(doc)}>
                    <Eye size={16} />
                  </button>
                )}
                {doc.status === 'ready' && (
                  <button className="docs-action-btn" onClick={() => setSearchKeysTarget(doc)} title={t('docs.actions.searchKeys')}>
                    <Key size={16} />
                  </button>
                )}
                {doc.status === 'ready' && canLifecycle && (
                  <button className="docs-action-btn" onClick={() => handleAnalyzeLifecycle(doc)} title={t('docs.actions.analyzeLifecycle')}>
                    <Activity size={16} />
                  </button>
                )}
                {doc.status === 'ready' && (
                  <button className="docs-action-btn" onClick={() => setLifecycleTarget(doc)} title={t('docs.actions.viewLifecycle')}>
                    <FileSearch size={16} />
                  </button>
                )}
                {canReindex && (doc.status === 'ready' || doc.status === 'error' || doc.status === 'cancelled') && !_PLACEHOLDER_FORMATS.has(doc.format) && (
                  <button className="docs-action-btn" onClick={() => setReingestTarget(doc)}>
                    <RefreshCw size={16} />
                  </button>
                )}
                {canSync && (doc.status === 'ready' || doc.status === 'error' || doc.status === 'cancelled') && isLinkedDoc(doc) && (
                  <button className="docs-action-btn" onClick={() => setSyncTarget(doc)}>
                    <CloudDownload size={16} />
                  </button>
                )}
                {canDelete && (
                  <button className="docs-action-btn docs-action-btn--danger" onClick={() => setDeleteTarget(doc)}>
                    <Trash2 size={16} />
                  </button>
                )}
              </div>
            </div>
          )})}
      </div>

      {deleteTarget && (
        <ConfirmDialog
          title={t('docs.delete.title')}
          message={t('docs.delete.message')}
          details={`${deleteTarget.title} (${deleteTarget.original_filename}, ${formatBytes(deleteTarget.file_size_bytes)})`}
          confirmLabel={t('docs.delete.confirm')}
          cancelLabel={t('docs.delete.cancel')}
          variant="danger"
          onConfirm={handleDeleteConfirm}
          onCancel={() => setDeleteTarget(null)}
        />
      )}

      {reingestTarget && (
        <ConfirmDialog
          title={t('docs.reingest.title')}
          message={t('docs.reingest.message')}
          details={`${reingestTarget.title} (${reingestTarget.original_filename}, ${formatBytes(reingestTarget.file_size_bytes)})`}
          confirmLabel={t('docs.reingest.confirm')}
          cancelLabel={t('docs.reingest.cancel')}
          variant="default"
          onConfirm={handleReingestConfirm}
          onCancel={() => setReingestTarget(null)}
        />
      )}

      {syncTarget && (
        <ConfirmDialog
          title={t('docs.sync.title')}
          message={t('docs.sync.message')}
          details={`${syncTarget.title} (${syncTarget.original_filename}, ${formatBytes(syncTarget.file_size_bytes)})`}
          confirmLabel={t('docs.sync.confirm')}
          cancelLabel={t('docs.sync.cancel')}
          variant="default"
          onConfirm={handleSyncConfirm}
          onCancel={() => setSyncTarget(null)}
        />
      )}

      {cancelTarget && (
        <ConfirmDialog
          title={t('docs.cancel.title')}
          message={t('docs.cancel.message')}
          details={`${cancelTarget.title} (${cancelTarget.original_filename}, ${formatBytes(cancelTarget.file_size_bytes)})`}
          confirmLabel={t('docs.cancel.confirm')}
          cancelLabel={t('docs.cancel.dismiss')}
          variant="danger"
          onConfirm={handleCancelConfirm}
          onCancel={() => setCancelTarget(null)}
        />
      )}

      {deleteLcTarget && (
        <ConfirmDialog
          title={t('docs.lifecycle.deleteTitle')}
          message={t('docs.lifecycle.deleteMessage')}
          details={deleteLcTarget.title}
          confirmLabel={t('docs.lifecycle.deleteConfirm')}
          cancelLabel={t('docs.delete.cancel')}
          variant="danger"
          onConfirm={handleDeleteLcConfirm}
          onCancel={() => setDeleteLcTarget(null)}
        />
      )}

      {renameTarget && (
        <RenameDialog
          currentTitle={renameTarget.title}
          originalFilename={renameTarget.originalFilename}
          onConfirm={handleRenameConfirm}
          onCancel={() => setRenameTarget(null)}
        />
      )}

      {previewTarget && (
        <MarkdownPreviewModal
          documentId={previewTarget.id}
          documentTitle={previewTarget.title}
          onClose={() => setPreviewTarget(null)}
        />
      )}

      {searchKeysTarget && (
        <SearchKeysModal
          mode="document"
          entityId={searchKeysTarget.id}
          entityTitle={searchKeysTarget.title}
          onClose={() => setSearchKeysTarget(null)}
        />
      )}

      {lifecycleTarget && (
        <LifecycleModal
          documentId={lifecycleTarget.id}
          documentTitle={lifecycleTarget.title}
          canRun={canLifecycle}
          onClose={() => setLifecycleTarget(null)}
          onDeleted={() => {
            setDocuments(prev => prev.map(d => d.id === lifecycleTarget.id ? { ...d, lifecycle_status: '' } : d))
          }}
        />
      )}
      </div>

      {debugPanel && (
        <DocsRightPanel
          mode="document"
          documentId={debugPanel.id}
          documentTitle={debugPanel.title}
          onClose={closeDebug}
        />
      )}

      {toast && (
        <div className={`docs-toast docs-toast--${toast.variant}`}>
          <span>{toast.message}</span>
          <button className="docs-toast-close" onClick={() => setToast(null)}>
            <X size={14} />
          </button>
        </div>
      )}
    </div>
  )
}
