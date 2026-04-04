import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import {
  Box,
  Upload,
  Globe,
  Loader2,
  CheckCircle,
  Search,
  X,
  Bug,
  RefreshCw,
  CloudDownload,
  Pencil,
  Trash2,
  MoreHorizontal,
  Activity,
  ChevronRight,
  Play,
  FileSearch,
} from 'lucide-react'
import type { ColumnDef, ColumnFiltersState } from '@tanstack/react-table'
import { listProducts, deleteProduct, reingestProduct, syncProduct, cancelProductIngestion, analyzeProductLifecycle, deleteProductLifecycle } from '../api/products'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { DocsRightPanel } from '../components/DocsRightPanel'
import { ProductEditDialog } from '../components/ProductEditDialog'
import { ProductLifecycleModal } from '../components/ProductLifecycleModal'
import { DataTable } from '../components/DataTable'
import { useDataTable } from '../hooks/useDataTable'
import type { ProductListItem, DocumentStatusValue } from '../types'
import { usePermission } from '../auth/usePermission'
import { usePageTour } from '../hooks/usePageTour'
import { getProductsSteps } from '../tour/steps/productsSteps'

const POLL_INTERVAL = 2000
const STORAGE_KEY = 'lexiro-products-table'

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

function getProductStatus(p: ProductListItem): DocumentStatusValue {
  if (p.processing_documents > 0) return 'processing'
  if (p.pending_documents > 0) return 'pending'
  if (p.ready_documents > 0) return 'ready'
  if (p.error_documents > 0) return 'error'
  if (p.cancelled_documents > 0) return 'cancelled'
  return 'ready'
}

function ProductStatusBadge({ product, onCancel }: { product: ProductListItem; onCancel?: () => void }) {
  const { t } = useTranslation()
  const status = getProductStatus(product)
  const total = product.total_documents

  if (product.sync_status && product.sync_status !== 'idle') {
    const labelKey = product.sync_status === 'deleting'
      ? 'products.status.deleting'
      : product.sync_status === 'syncing'
        ? 'products.status.syncing'
        : 'products.status.reindexing'
    const variant = product.sync_status === 'deleting' ? 'deleting' : 'processing'
    return (
      <span className={`docs-status docs-status--${variant}`}>
        <Loader2 size={14} className="spin-icon" />
        {t(labelKey)}
      </span>
    )
  }

  const finished = total > 0 && product.processing_documents === 0 && product.pending_documents === 0
  const allReady = finished && product.ready_documents === total
  const mostlyReady = finished && product.ready_documents > 0 && !allReady

  if (allReady) {
    return (
      <span className="docs-status docs-status--ready">
        <CheckCircle size={14} />
        {t('docs.status.ready')}
      </span>
    )
  }

  if (mostlyReady) {
    return (
      <span className="docs-status docs-status--ready">
        <CheckCircle size={14} />
        {t('docs.status.ready')}
        {product.error_documents > 0 && (
          <span className="product-segmented-error-hint" style={{ marginLeft: 6 }}>
            ({product.error_documents} {t('docs.status.error').toLowerCase()})
          </span>
        )}
      </span>
    )
  }

  if (total === 0) {
    return <span className="docs-date">—</span>
  }

  const segments = ([
    { key: 'ready' as DocumentStatusValue, count: product.ready_documents },
    { key: 'processing' as DocumentStatusValue, count: product.processing_documents },
    { key: 'pending' as DocumentStatusValue, count: product.pending_documents },
    { key: 'error' as DocumentStatusValue, count: product.error_documents },
    { key: 'cancelled' as DocumentStatusValue, count: product.cancelled_documents },
  ]).filter(s => s.count > 0)

  const pct = (status === 'processing' || status === 'pending')
    ? Math.max(0, Math.min(100, product.progress_percent))
    : Math.round((product.ready_documents / total) * 100)

  const canCancel = onCancel && (status === 'processing' || status === 'pending')

  return (
    <div className="product-segmented-wrap">
      <div className="product-segmented-bar">
        {segments.map(s => (
          <div
            key={s.key}
            className={`product-segmented-segment product-segmented-segment--${s.key}`}
            style={{ width: `${(s.count / total) * 100}%` }}
          />
        ))}
      </div>
      <div className="product-segmented-text">
        {(status === 'processing' || status === 'pending') && (
          <span className="product-segmented-pct">{pct}%</span>
        )}
        <span className="product-segmented-fraction">
          {product.ready_documents} / {total}
        </span>
        {product.error_documents > 0 && (
          <span className="product-segmented-error-hint">
            ({product.error_documents} {t('docs.status.error').toLowerCase()})
          </span>
        )}
        {canCancel && (
          <button
            className="docs-status-cancel"
            onClick={e => { e.stopPropagation(); onCancel() }}
          >
            <X size={14} />
          </button>
        )}
      </div>
    </div>
  )
}

function ProductLifecycleSubmenu({
  product: p,
  onAnalyze,
  onView,
  onDeleteLc,
  onClose,
}: {
  product: ProductListItem
  onAnalyze?: (p: ProductListItem) => void
  onView?: (p: ProductListItem) => void
  onDeleteLc?: (p: ProductListItem) => void
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

  const hasResults = p.has_merged_lifecycle || p.lifecycle_ready_documents > 0

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
          {onAnalyze && (
            <button className="docs-actions-dropdown-item" onClick={() => { onAnalyze(p); onClose() }}>
              <Play size={14} />
              {t('docs.actions.analyzeLifecycle')}
            </button>
          )}
          {onView && hasResults && (
            <button className="docs-actions-dropdown-item" onClick={() => { onView(p); onClose() }}>
              <FileSearch size={14} />
              {t('docs.actions.viewLifecycle')}
            </button>
          )}
          {hasResults && onDeleteLc && (
            <button className="docs-actions-dropdown-item docs-actions-dropdown-item--danger" onClick={() => { onDeleteLc(p); onClose() }}>
              <Trash2 size={14} />
              {t('docs.actions.deleteLifecycle')}
            </button>
          )}
        </div>
      )}
    </div>
  )
}

function ProductActions({
  product: p,
  onEdit,
  onDelete,
  onReingest,
  onSync,
  onDebug,
  onAnalyzeLifecycle,
  onViewLifecycle,
  onDeleteLifecycle,
}: {
  product: ProductListItem
  onEdit?: (p: ProductListItem) => void
  onDelete?: (p: ProductListItem) => void
  onReingest?: (p: ProductListItem) => void
  onSync?: (p: ProductListItem) => void
  onDebug?: (p: ProductListItem) => void
  onAnalyzeLifecycle?: (p: ProductListItem) => void
  onViewLifecycle?: (p: ProductListItem) => void
  onDeleteLifecycle?: (p: ProductListItem) => void
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

  const handleToggle = useCallback(() => {
    if (!open) setPos({ top: -9999, left: -9999 })
    setOpen(v => !v)
  }, [open])

  return (
    <div className="docs-actions">
      {onEdit && (
        <button
          className="docs-action-btn"
          onClick={() => onEdit(p)}
          aria-label={t('products.actions.edit')}
        >
          <Pencil size={16} />
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
          {onDebug && (
            <button className="docs-actions-dropdown-item" onClick={() => { onDebug(p); setOpen(false) }}>
              <Bug size={15} />
              {t('products.actions.debug')}
            </button>
          )}
          {onReingest && (
            <button className="docs-actions-dropdown-item" onClick={() => { onReingest(p); setOpen(false) }}>
              <RefreshCw size={15} />
              {t('products.actions.reindex')}
            </button>
          )}
          {onSync && (
            <button className="docs-actions-dropdown-item" onClick={() => { onSync(p); setOpen(false) }}>
              <CloudDownload size={15} />
              {t('products.actions.sync')}
            </button>
          )}
          {(onAnalyzeLifecycle || onViewLifecycle || onDeleteLifecycle) && (
            <ProductLifecycleSubmenu
              product={p}
              onAnalyze={onAnalyzeLifecycle}
              onView={onViewLifecycle}
              onDeleteLc={onDeleteLifecycle}
              onClose={() => setOpen(false)}
            />
          )}
          {onDelete && (
            <button className="docs-actions-dropdown-item docs-actions-dropdown-item--danger" onClick={() => { onDelete(p); setOpen(false) }}>
              <Trash2 size={15} />
              {t('products.actions.delete')}
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
}

const DEFAULT_COLUMN_ORDER = ['name', 'category', 'documents', 'format', 'status', 'size', 'chunks', 'uploaded', 'indexed', 'actions']

export function ProductsPage({ onUploadClick, onUrlImportClick, refreshKey }: Props) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const productsTourSteps = useMemo(() => getProductsSteps(t), [t])
  usePageTour('products', productsTourSteps)
  const canDebug = usePermission('debug')
  const canEdit = usePermission('products.edit')
  const canDelete = usePermission('products.delete')
  const canReindex = usePermission('documents.reindex')
  const canSync = usePermission('documents.sync')
  const canLifecycle = usePermission('lifecycle.run')
  const [products, setProducts] = useState<ProductListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [globalFilter, setGlobalFilter] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<ProductListItem | null>(null)
  const [editTarget, setEditTarget] = useState<ProductListItem | null>(null)
  const [reingestTarget, setReingestTarget] = useState<ProductListItem | null>(null)
  const [syncTarget, setSyncTarget] = useState<ProductListItem | null>(null)
  const [cancelTarget, setCancelTarget] = useState<ProductListItem | null>(null)
  const [debugPanel, setDebugPanel] = useState<ProductListItem | null>(null)
  const [lifecycleTarget, setLifecycleTarget] = useState<ProductListItem | null>(null)
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

  const fetchProducts = useCallback(async () => {
    try {
      const data = await listProducts()
      setProducts(data)
    } catch { /* keep previous */ }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { fetchProducts() }, [fetchProducts])

  useEffect(() => {
    if (refreshKey) fetchProducts()
  }, [refreshKey, fetchProducts])

  useEffect(() => {
    const hasPending = products.some(p => p.pending_documents > 0 || p.processing_documents > 0 || (p.sync_status && p.sync_status !== 'idle'))
    if (hasPending) {
      pollRef.current = setInterval(fetchProducts, POLL_INTERVAL)
    }
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [products, fetchProducts])

  const handleDeleteConfirm = useCallback(async () => {
    if (!deleteTarget) return
    try {
      await deleteProduct(deleteTarget.id)
      setProducts(prev => prev.map(p =>
        p.id === deleteTarget.id ? { ...p, sync_status: 'deleting' } : p
      ))
    } catch { /* ignore */ }
    finally { setDeleteTarget(null) }
  }, [deleteTarget])

  const handleReingestConfirm = useCallback(async () => {
    if (!reingestTarget) return
    const id = reingestTarget.id
    setReingestTarget(null)
    try {
      await reingestProduct(id)
    } catch { /* ignore */ }
    finally { fetchProducts() }
  }, [reingestTarget, fetchProducts])

  const handleSyncConfirm = useCallback(async () => {
    if (!syncTarget) return
    const id = syncTarget.id
    setSyncTarget(null)
    try {
      await syncProduct(id)
    } catch { /* ignore */ }
    finally { fetchProducts() }
  }, [syncTarget, fetchProducts])

  const handleCancelConfirm = useCallback(async () => {
    if (!cancelTarget) return
    try {
      await cancelProductIngestion(cancelTarget.id)
      fetchProducts()
    } catch { /* ignore */ }
    finally { setCancelTarget(null) }
  }, [cancelTarget, fetchProducts])

  const openDebug = useCallback((product: ProductListItem) => {
    setDebugPanel(product)
  }, [])

  const closeDebug = useCallback(() => {
    setDebugPanel(null)
  }, [])

  const handleAnalyzeLifecycle = useCallback(async (p: ProductListItem) => {
    try {
      await analyzeProductLifecycle(p.id)
      showToast(t('products.lifecycle.started', { name: p.name }), 'success')
      fetchProducts()
    } catch {
      showToast(t('products.lifecycle.error'), 'error')
    }
  }, [showToast, t, fetchProducts])

  const handleDeleteLifecycle = useCallback(async (p: ProductListItem) => {
    try {
      await deleteProductLifecycle(p.id)
      setProducts(prev => prev.map(pr => pr.id === p.id ? { ...pr, lifecycle_ready_documents: 0, has_merged_lifecycle: false } : pr))
      showToast(t('products.lifecycle.deleted', { name: p.name }), 'success')
    } catch {
      showToast(t('products.lifecycle.deleteError'), 'error')
    }
  }, [showToast, t])

  const lifecycleReadyCount = useMemo(() =>
    products.filter(p => p.has_merged_lifecycle || p.lifecycle_ready_documents > 0).length
  , [products])

  const formatCounts = useMemo(() => {
    const map = new Map<string, number>()
    for (const p of products) {
      for (const f of p.formats) {
        map.set(f.format, (map.get(f.format) ?? 0) + 1)
      }
    }
    return [...map.entries()].sort((a, b) => b[1] - a[1])
  }, [products])

  const statusCounts = useMemo(() => {
    const map = new Map<string, number>()
    for (const p of products) {
      map.set(getProductStatus(p), (map.get(getProductStatus(p)) ?? 0) + 1)
    }
    return [...map.entries()].sort((a, b) => b[1] - a[1])
  }, [products])

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
    if (lifecycleFilter) filters.push({ id: 'name', value: 'lifecycle_ready' })
    return filters
  }, [formatFilter, statusFilter, lifecycleFilter])

  const columns = useMemo<ColumnDef<ProductListItem, unknown>[]>(() => [
    {
      id: 'name',
      accessorFn: row => row.display_name || row.name,
      header: () => t('products.table.name'),
      filterFn: (row, _columnId, filterValue) => {
        if (filterValue === 'lifecycle_ready') {
          return row.original.has_merged_lifecycle || row.original.lifecycle_ready_documents > 0
        }
        return true
      },
      cell: ({ row }) => {
        const p = row.original
        const isDeleting = p.sync_status === 'deleting'
        const lcFull = p.has_merged_lifecycle
        const lcPartial = !lcFull && p.lifecycle_ready_documents > 0
        return (
          <div
            className="docs-name-cell"
            style={{ cursor: isDeleting ? 'default' : 'pointer', opacity: isDeleting ? 0.5 : 1 }}
            onClick={isDeleting ? undefined : () => navigate(`/app/products/${p.slug}`)}
          >
            <div className="docs-name-row">
              <span className="docs-name">{p.display_name || p.name}</span>
              {lcFull && (
                <button
                  className="docs-lc-badge docs-lc-badge--ready"
                  onClick={e => { e.stopPropagation(); setLifecycleTarget(p) }}
                  title={t('products.lifecycle.badgeFull')}
                >
                  <Activity size={10} />
                  API Lifecycle
                </button>
              )}
              {lcPartial && (
                <button
                  className="docs-lc-badge docs-lc-badge--partial"
                  onClick={e => { e.stopPropagation(); setLifecycleTarget(p) }}
                  title={t('products.lifecycle.badgePartial', { count: p.lifecycle_ready_documents })}
                >
                  <Activity size={10} />
                  API Lifecycle ({p.lifecycle_ready_documents})
                </button>
              )}
            </div>
            {p.manufacturer && (
              <span className="docs-filename">{p.manufacturer}</span>
            )}
          </div>
        )
      },
      enableGrouping: true,
    },
    {
      id: 'category',
      accessorFn: row => row.category || '',
      header: () => t('products.table.category'),
      cell: ({ row }) => {
        const cat = row.original.category
        if (!cat) return <span className="docs-date">—</span>
        return <span className="docs-format-badge">{t(`category.${cat}`)}</span>
      },
      enableGrouping: true,
    },
    {
      id: 'documents',
      accessorKey: 'total_documents',
      header: () => t('products.table.documents'),
      cell: ({ getValue }) => <span className="docs-chunks">{Number(getValue()) || '—'}</span>,
      enableGrouping: false,
    },
    {
      id: 'format',
      accessorFn: row => row.formats.map(f => f.format).join(', '),
      header: () => t('products.table.format'),
      cell: ({ row }) => (
        <div className="docs-format-badges">
          {row.original.formats.map(f => (
            <span key={f.format} className="docs-format-badge">
              {f.format.toUpperCase()} {f.count > 1 && <span className="docs-format-count">{f.count}</span>}
            </span>
          ))}
        </div>
      ),
      enableGrouping: true,
      filterFn: (row, _columnId, filterValue: Set<string>) =>
        filterValue.size === 0 || row.original.formats.some(f => filterValue.has(f.format)),
    },
    {
      id: 'status',
      accessorFn: row => getProductStatus(row),
      header: () => t('products.table.status'),
      cell: ({ row }) => <ProductStatusBadge product={row.original} onCancel={() => setCancelTarget(row.original)} />,
      enableGrouping: true,
      filterFn: (row, _columnId, filterValue: Set<string>) =>
        filterValue.size === 0 || filterValue.has(getProductStatus(row.original)),
    },
    {
      id: 'size',
      accessorKey: 'total_file_size_bytes',
      header: () => t('products.table.size'),
      cell: ({ getValue }) => <span className="docs-size">{formatBytes(Number(getValue()))}</span>,
      enableGrouping: false,
      sortingFn: 'basic',
    },
    {
      id: 'chunks',
      accessorKey: 'total_chunks',
      header: () => t('products.table.chunks'),
      cell: ({ getValue }) => <span className="docs-chunks">{Number(getValue()) || '—'}</span>,
      enableGrouping: false,
    },
    {
      id: 'uploaded',
      accessorFn: row => row.uploaded_at,
      header: () => t('products.table.uploaded'),
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
      header: () => t('products.table.indexed'),
      cell: ({ getValue }) => {
        const v = getValue() as string | null
        return <span className="docs-date">{formatDateCompact(v)}</span>
      },
      enableGrouping: false,
      sortingFn: 'datetime',
    },
    ...((canEdit || canDebug || canDelete || canReindex || canSync || canLifecycle) ? [{
      id: 'actions',
      header: () => t('products.table.actions'),
      enableSorting: false,
      enableGrouping: false,
      cell: ({ row }: { row: { original: ProductListItem } }) => {
        const p = row.original
        const isDeleting = p.sync_status === 'deleting'
        if (isDeleting) return null
        return (
          <ProductActions
            product={p}
            onEdit={canEdit ? setEditTarget : undefined}
            onDelete={canDelete ? setDeleteTarget : undefined}
            onReingest={canReindex ? setReingestTarget : undefined}
            onSync={canSync ? setSyncTarget : undefined}
            onDebug={canDebug ? openDebug : undefined}
            onAnalyzeLifecycle={canLifecycle ? handleAnalyzeLifecycle : undefined}
            onViewLifecycle={setLifecycleTarget}
            onDeleteLifecycle={canLifecycle ? handleDeleteLifecycle : undefined}
          />
        )
      },
    }] : []),
  ], [t, navigate, openDebug, canDebug, canEdit, canDelete, canReindex, canSync, canLifecycle, handleAnalyzeLifecycle, handleDeleteLifecycle])

  const {
    table,
    columnOrder,
    grouping,
    handleColumnOrderChange,
    removeGrouping,
    toggleGrouping,
    resetSettings,
  } = useDataTable({
    data: products,
    columns,
    storageKey: STORAGE_KEY,
    defaultColumnOrder: DEFAULT_COLUMN_ORDER,
    defaultSorting: [{ id: 'name', desc: false }],
    getRowId: row => row.firmware_version_id ? `${row.id}-${row.firmware_version_id}` : String(row.id),
    columnFilters,
    globalFilter,
    onGlobalFilterChange: setGlobalFilter,
  })

  const handleResetAll = useCallback(() => {
    resetSettings()
    setGlobalFilter('')
    setFormatFilter(new Set())
    setStatusFilter(new Set())
    setLifecycleFilter(false)
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

  if (products.length === 0) {
    return (
      <div className="docs-page">
        <div className="docs-empty">
          <Box size={48} className="docs-empty-icon" />
          <h2>{t('products.empty.title')}</h2>
          <p>{t('products.empty.description')}</p>
          <div className="docs-empty-actions">
            {onUploadClick && (
              <button className="docs-upload-btn" onClick={onUploadClick}>
                <Upload size={16} />
                <span>{t('products.empty.cta')}</span>
              </button>
            )}
            {onUrlImportClick && (
              <button className="docs-upload-btn docs-upload-btn--secondary" onClick={onUrlImportClick}>
                <Globe size={16} />
                <span>{t('urlImport.button')}</span>
              </button>
            )}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className={`docs-page${debugPanel ? ' docs-page--with-panel' : ''}`}>
      <div className="docs-page-main">
      <div className="docs-header">
        <h1 className="docs-page-title">
          <Box size={20} />
          {t('products.title')}
        </h1>
        <div className="docs-header-actions">
          <div className="docs-search">
            <Search size={16} />
            <input
              ref={searchRef}
              type="text"
              value={globalFilter}
              onChange={e => setGlobalFilter(e.target.value)}
              placeholder={t('products.search.placeholder')}
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
        {products
          .filter(p => {
            if (formatFilter.size > 0 && !p.formats.some(f => formatFilter.has(f.format))) return false
            if (statusFilter.size > 0 && !statusFilter.has(getProductStatus(p))) return false
            if (lifecycleFilter && !p.has_merged_lifecycle && p.lifecycle_ready_documents === 0) return false
            if (!globalFilter) return true
            const q = globalFilter.toLowerCase()
            return (
              p.name.toLowerCase().includes(q) ||
              (p.display_name || '').toLowerCase().includes(q) ||
              p.manufacturer.toLowerCase().includes(q) ||
              p.version.toLowerCase().includes(q)
            )
          })
          .map(p => (
            <div
              className="docs-card"
              key={p.firmware_version_id ? `${p.id}-${p.firmware_version_id}` : p.id}
              onClick={p.sync_status === 'deleting' ? undefined : () => navigate(`/app/products/${p.slug}`)}
              style={{ cursor: p.sync_status === 'deleting' ? 'default' : 'pointer', opacity: p.sync_status === 'deleting' ? 0.5 : 1 }}
            >
              <div className="docs-card-header">
                <div className="docs-card-title-row">
                  <div className="docs-card-title">
                    {p.display_name || p.name}
                    {p.manufacturer && <div className="docs-filename">{p.manufacturer}</div>}
                  </div>
                  {p.has_merged_lifecycle && (
                    <button
                      className="docs-lc-badge docs-lc-badge--ready"
                      onClick={e => { e.stopPropagation(); setLifecycleTarget(p) }}
                    >
                      <Activity size={10} />
                      API Lifecycle
                    </button>
                  )}
                  {!p.has_merged_lifecycle && p.lifecycle_ready_documents > 0 && (
                    <button
                      className="docs-lc-badge docs-lc-badge--partial"
                      onClick={e => { e.stopPropagation(); setLifecycleTarget(p) }}
                    >
                      <Activity size={10} />
                      API Lifecycle ({p.lifecycle_ready_documents})
                    </button>
                  )}
                </div>
                <ProductStatusBadge product={p} onCancel={() => setCancelTarget(p)} />
              </div>
              <div className="docs-card-meta">
                <span>{t('products.table.documents')}: {p.total_documents}</span>
                <span>{formatBytes(p.total_file_size_bytes)}</span>
                {p.total_chunks > 0 && <span>{t('products.table.chunks')}: {p.total_chunks}</span>}
                {p.uploaded_at && <span>{formatDateCompact(p.uploaded_at)}</span>}
              </div>
              {p.formats.length > 0 && (
                <div className="docs-card-meta" style={{ marginTop: 4 }}>
                  {p.formats.map(f => (
                    <span key={f.format} className="docs-format-badge">
                      {f.format.toUpperCase()} {f.count > 1 && <span className="docs-format-count">{f.count}</span>}
                    </span>
                  ))}
                </div>
              )}
              {(canEdit || canDebug || canReindex || canSync || canDelete) && (
                <div className="docs-card-actions" onClick={e => e.stopPropagation()}>
                  {canEdit && (
                    <button className="docs-action-btn" onClick={() => setEditTarget(p)}>
                      <Pencil size={16} />
                    </button>
                  )}
                  {canDebug && (
                    <button className="docs-action-btn" onClick={() => openDebug(p)}>
                      <Bug size={16} />
                    </button>
                  )}
                  {canReindex && (
                    <button className="docs-action-btn" onClick={() => setReingestTarget(p)}>
                      <RefreshCw size={16} />
                    </button>
                  )}
                  {canSync && (
                    <button className="docs-action-btn" onClick={() => setSyncTarget(p)}>
                      <CloudDownload size={16} />
                    </button>
                  )}
                  {canDelete && (
                    <button className="docs-action-btn docs-action-btn--danger" onClick={() => setDeleteTarget(p)}>
                      <Trash2 size={16} />
                    </button>
                  )}
                </div>
              )}
            </div>
          ))
        }
      </div>
      </div>

      {debugPanel && (
        <DocsRightPanel
          mode="product"
          productId={debugPanel.id}
          productName={debugPanel.name}
          onClose={closeDebug}
        />
      )}

      {deleteTarget && (
        <ConfirmDialog
          title={t('products.delete.title')}
          message={t('products.delete.message')}
          details={`${deleteTarget.name} (${deleteTarget.total_documents} documents, ${formatBytes(deleteTarget.total_file_size_bytes)})`}
          confirmLabel={t('products.delete.confirm')}
          cancelLabel={t('products.delete.cancel')}
          variant="danger"
          onConfirm={handleDeleteConfirm}
          onCancel={() => setDeleteTarget(null)}
        />
      )}

      {reingestTarget && (
        <ConfirmDialog
          title={t('products.reingest.title')}
          message={t('products.reingest.message')}
          details={`${reingestTarget.name} (${reingestTarget.total_documents} documents)`}
          confirmLabel={t('products.reingest.confirm')}
          cancelLabel={t('products.delete.cancel')}
          variant="default"
          onConfirm={handleReingestConfirm}
          onCancel={() => setReingestTarget(null)}
        />
      )}

      {syncTarget && (
        <ConfirmDialog
          title={t('products.sync.title')}
          message={t('products.sync.message')}
          details={`${syncTarget.name} (${syncTarget.total_documents} documents)`}
          confirmLabel={t('products.sync.confirm')}
          cancelLabel={t('products.delete.cancel')}
          variant="default"
          onConfirm={handleSyncConfirm}
          onCancel={() => setSyncTarget(null)}
        />
      )}

      {cancelTarget && (
        <ConfirmDialog
          title={t('products.cancelIngestion.title')}
          message={t('products.cancelIngestion.message')}
          details={`${cancelTarget.name} (${cancelTarget.pending_documents + cancelTarget.processing_documents} ${t('products.cancelIngestion.documentsLabel')})`}
          confirmLabel={t('products.cancelIngestion.confirm')}
          cancelLabel={t('products.delete.cancel')}
          variant="danger"
          onConfirm={handleCancelConfirm}
          onCancel={() => setCancelTarget(null)}
        />
      )}

      {editTarget && (
        <ProductEditDialog
          product={editTarget}
          onSave={() => { setEditTarget(null); fetchProducts() }}
          onCancel={() => setEditTarget(null)}
        />
      )}

      {lifecycleTarget && (
        <ProductLifecycleModal
          productId={lifecycleTarget.id}
          productName={lifecycleTarget.name}
          canRun={canLifecycle}
          onClose={() => setLifecycleTarget(null)}
          onDeleted={() => {
            setProducts(prev => prev.map(p => p.id === lifecycleTarget.id ? { ...p, lifecycle_ready_documents: 0, has_merged_lifecycle: false } : p))
          }}
          onAnalyzed={() => fetchProducts()}
        />
      )}

      {toast && createPortal(
        <div className={`docs-toast docs-toast--${toast.variant}`}>
          {toast.variant === 'success' && <CheckCircle size={16} />}
          {toast.variant === 'error' && <X size={16} />}
          {toast.message}
        </div>,
        document.body
      )}
    </div>
  )
}
