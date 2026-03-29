import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'
import {
  FileText,
  Upload,
  Globe,
  Download,
  RefreshCw,
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
} from 'lucide-react'
import type { ColumnDef, ColumnFiltersState, FilterFn } from '@tanstack/react-table'
import { listDocuments, previewMarkdown, deleteDocument, reingestDocument, cancelDocument } from '../api/documents'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { MarkdownPreviewModal } from '../components/MarkdownPreviewModal'
import { DocsRightPanel } from '../components/DocsRightPanel'
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

function DocActions({
  doc,
  onDebug,
  onPreview,
  onDownload,
  onReingest,
  onDelete,
}: {
  doc: DocumentListItem
  onDebug: (d: DocumentListItem) => void
  onPreview: (d: DocumentListItem) => void
  onDownload: (d: DocumentListItem) => void
  onReingest: (d: DocumentListItem) => void
  onDelete: (d: DocumentListItem) => void
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const btnRef = useRef<HTMLButtonElement>(null)
  const dropRef = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<{ top: number; left: number }>({ top: 0, left: 0 })

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

  const handleToggle = useCallback(() => {
    if (!open && btnRef.current) {
      const rect = btnRef.current.getBoundingClientRect()
      const dropW = 200
      let left = rect.right - dropW
      if (left < 8) left = 8
      if (left + dropW > window.innerWidth - 8) left = window.innerWidth - dropW - 8
      setPos({ top: rect.bottom + 4, left })
    }
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
          {doc.status === 'ready' && (
            <button className="docs-actions-dropdown-item" onClick={() => { onDebug(doc); setOpen(false) }}>
              <Bug size={15} />
              {t('docs.actions.debug')}
            </button>
          )}
          {doc.status === 'ready' && (
            <button className="docs-actions-dropdown-item" onClick={() => { onDownload(doc); setOpen(false) }}>
              <Download size={15} />
              {t('docs.actions.download')}
            </button>
          )}
          {(doc.status === 'ready' || doc.status === 'error' || doc.status === 'cancelled') && (
            <button className="docs-actions-dropdown-item" onClick={() => { onReingest(doc); setOpen(false) }}>
              <RefreshCw size={15} />
              {t('docs.actions.reindex')}
            </button>
          )}
          <button className="docs-actions-dropdown-item docs-actions-dropdown-item--danger" onClick={() => { onDelete(doc); setOpen(false) }}>
            <Trash2 size={15} />
            {t('docs.actions.delete')}
          </button>
        </div>,
        document.body
      )}
    </div>
  )
}

interface Props {
  onUploadClick: () => void
  onUrlImportClick?: () => void
  refreshKey?: number
  productId?: number
  headerSlot?: React.ReactNode
}

const DEFAULT_COLUMN_ORDER = ['title', 'format', 'status', 'size', 'chunks', 'product', 'uploaded', 'indexed', 'actions']

export function DocumentsPage({ onUploadClick, onUrlImportClick, refreshKey, productId, headerSlot }: Props) {
  const { t } = useTranslation()
  const [documents, setDocuments] = useState<DocumentListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [deleteTarget, setDeleteTarget] = useState<DocumentListItem | null>(null)
  const [reingestTarget, setReingestTarget] = useState<DocumentListItem | null>(null)
  const [cancelTarget, setCancelTarget] = useState<DocumentListItem | null>(null)
  const [previewTarget, setPreviewTarget] = useState<DocumentListItem | null>(null)
  const [globalFilter, setGlobalFilter] = useState('')
  const [debugPanel, setDebugPanel] = useState<DocumentListItem | null>(null)
  const [formatFilter, setFormatFilter] = useState<Set<string>>(new Set())
  const [statusFilter, setStatusFilter] = useState<Set<string>>(new Set())
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const searchRef = useRef<HTMLInputElement>(null)

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
    const hasPending = documents.some(d => d.status === 'pending' || d.status === 'processing')
    if (hasPending) {
      pollRef.current = setInterval(fetchDocs, POLL_INTERVAL)
    }
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [documents, fetchDocs])

  const handleDownload = useCallback(async (doc: DocumentListItem) => {
    try {
      const result = await previewMarkdown(doc.id)
      const blob = new Blob([result.markdown], { type: 'text/markdown;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${result.title || `document-${doc.id}`}.md`
      a.click()
      URL.revokeObjectURL(url)
    } catch { /* ignore */ }
  }, [])

  const handleDeleteConfirm = useCallback(async () => {
    if (!deleteTarget) return
    try {
      await deleteDocument(deleteTarget.id)
      setDocuments(prev => prev.filter(d => d.id !== deleteTarget.id))
    } catch { /* ignore */ }
    finally { setDeleteTarget(null) }
  }, [deleteTarget])

  const handleReingestConfirm = useCallback(async () => {
    if (!reingestTarget) return
    try {
      await reingestDocument(reingestTarget.id)
      setDocuments(prev =>
        prev.map(d => d.id === reingestTarget.id ? { ...d, status: 'pending' as const, error_message: null, total_chunks: 0, progress_percent: 0, progress_stage: '' } : d)
      )
    } catch (err) {
      const detail = err instanceof Error ? err.message : String(err)
      alert(`${t('docs.reingest.error')}: ${detail}`)
    }
    finally { setReingestTarget(null) }
  }, [reingestTarget, t])

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
  }, [])

  const hasActiveFilters = formatFilter.size > 0 || statusFilter.size > 0

  const columnFilters = useMemo<ColumnFiltersState>(() => {
    const filters: ColumnFiltersState = []
    if (formatFilter.size > 0) filters.push({ id: 'format', value: formatFilter })
    if (statusFilter.size > 0) filters.push({ id: 'status', value: statusFilter })
    return filters
  }, [formatFilter, statusFilter])

  const columns = useMemo<ColumnDef<DocumentListItem, unknown>[]>(() => [
    {
      id: 'title',
      accessorFn: row => row.title,
      header: () => t('docs.table.name'),
      cell: ({ row }) => {
        const { title, original_filename, source_container, source_path } = row.original
        const linkUrl = source_path || source_container
        const sourceIsUrl = linkUrl && isUrl(linkUrl)
        return (
          <div className="docs-name-cell">
            <OverflowCell className="docs-name">{title}</OverflowCell>
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
          onDebug={openDebug}
          onPreview={setPreviewTarget}
          onDownload={handleDownload}
          onReingest={setReingestTarget}
          onDelete={setDeleteTarget}
        />
      ),
    },
  ], [t, handleDownload, openDebug])

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
          <button className="docs-upload-btn" onClick={onUploadClick}>
            <Upload size={16} />
            <span>{t('docs.empty.cta')}</span>
          </button>
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
          <button className="docs-upload-btn" onClick={onUploadClick}>
            <Upload size={16} />
            <span>{t('docs.upload')}</span>
          </button>
        </div>
      </div>

      {(formatCounts.length > 1 || statusCounts.length > 1) && (
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
                <div className="docs-card-title">{doc.title}</div>
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
                {doc.status === 'ready' && (
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
                  <button className="docs-action-btn" onClick={() => handleDownload(doc)}>
                    <Download size={16} />
                  </button>
                )}
                {(doc.status === 'ready' || doc.status === 'error' || doc.status === 'cancelled') && (
                  <button className="docs-action-btn" onClick={() => setReingestTarget(doc)}>
                    <RefreshCw size={16} />
                  </button>
                )}
                <button className="docs-action-btn docs-action-btn--danger" onClick={() => setDeleteTarget(doc)}>
                  <Trash2 size={16} />
                </button>
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

      {previewTarget && (
        <MarkdownPreviewModal
          documentId={previewTarget.id}
          documentTitle={previewTarget.title}
          onClose={() => setPreviewTarget(null)}
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
    </div>
  )
}
