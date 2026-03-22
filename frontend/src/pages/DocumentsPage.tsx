import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  FileText,
  Upload,
  Download,
  RefreshCw,
  Trash2,
  Clock,
  Loader2,
  CheckCircle,
  AlertCircle,
  Search,
  ArrowUp,
  ArrowDown,
  ArrowUpDown,
  GripVertical,
  X,
  Layers,
  ChevronRight,
  ChevronDown,
} from 'lucide-react'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  getGroupedRowModel,
  getExpandedRowModel,
  flexRender,
  type ColumnDef,
  type SortingState,
  type ColumnOrderState,
  type GroupingState,
  type ExpandedState,
} from '@tanstack/react-table'
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
  DragOverlay,
  type DragStartEvent,
} from '@dnd-kit/core'
import {
  arrayMove,
  SortableContext,
  horizontalListSortingStrategy,
  useSortable,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { listDocuments, downloadDocument, deleteDocument, reingestDocument } from '../api/documents'
import { ConfirmDialog } from '../components/ConfirmDialog'
import type { DocumentListItem, DocumentStatusValue } from '../types'

const POLL_INTERVAL = 5000

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${(bytes / Math.pow(k, i)).toFixed(i > 0 ? 1 : 0)} ${sizes[i]}`
}

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

function StatusBadge({ status, errorMessage }: { status: DocumentStatusValue; errorMessage?: string | null }) {
  const { t } = useTranslation()
  const icons: Record<DocumentStatusValue, React.ReactNode> = {
    pending: <Clock size={14} />,
    processing: <Loader2 size={14} className="spin-icon" />,
    ready: <CheckCircle size={14} />,
    error: <AlertCircle size={14} />,
  }

  return (
    <div className="docs-status-wrap">
      <span
        className={`docs-status docs-status--${status}`}
        title={status === 'error' && errorMessage ? errorMessage : undefined}
      >
        {icons[status]}
        {t(`docs.status.${status}`)}
      </span>
      {(status === 'pending' || status === 'processing') && (
        <div className="docs-progress-bar">
          <div className={`docs-progress-fill docs-progress-fill--${status}`} />
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

function SortIcon({ direction }: { direction: false | 'asc' | 'desc' }) {
  if (direction === 'asc') return <ArrowUp size={14} className="docs-sort-icon docs-sort-icon--active" />
  if (direction === 'desc') return <ArrowDown size={14} className="docs-sort-icon docs-sort-icon--active" />
  return <ArrowUpDown size={14} className="docs-sort-icon" />
}

function DraggableHeader({ header, children }: { header: { id: string; column: { getCanSort: () => boolean; getIsSorted: () => false | 'asc' | 'desc'; getToggleSortingHandler: () => ((e: unknown) => void) | undefined; getCanGroup: () => boolean } }; children: React.ReactNode }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: header.id })

  const style: React.CSSProperties = {
    transform: CSS.Translate.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  }

  return (
    <th ref={setNodeRef} style={style} className="docs-th">
      <div className="docs-th-inner">
        <span className="docs-th-drag" {...attributes} {...listeners}>
          <GripVertical size={12} />
        </span>
        <span
          className={header.column.getCanSort() ? 'docs-th-label docs-th-label--sortable' : 'docs-th-label'}
          onClick={header.column.getToggleSortingHandler()}
        >
          {children}
          {header.column.getCanSort() && <SortIcon direction={header.column.getIsSorted()} />}
        </span>
      </div>
    </th>
  )
}

interface Props {
  onUploadClick: () => void
  refreshKey?: number
}

export function DocumentsPage({ onUploadClick, refreshKey }: Props) {
  const { t } = useTranslation()
  const [documents, setDocuments] = useState<DocumentListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [deleteTarget, setDeleteTarget] = useState<DocumentListItem | null>(null)
  const [reingestTarget, setReingestTarget] = useState<DocumentListItem | null>(null)
  const [globalFilter, setGlobalFilter] = useState('')
  const [sorting, setSorting] = useState<SortingState>([])
  const [grouping, setGrouping] = useState<GroupingState>([])
  const [expanded, setExpanded] = useState<ExpandedState>(true)
  const [activeId, setActiveId] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const searchRef = useRef<HTMLInputElement>(null)

  const defaultColumnOrder: string[] = useMemo(
    () => ['title', 'format', 'status', 'size', 'chunks', 'product', 'date', 'actions'],
    [],
  )
  const [columnOrder, setColumnOrder] = useState<ColumnOrderState>(defaultColumnOrder)

  const fetchDocs = useCallback(async () => {
    try {
      const docs = await listDocuments()
      setDocuments(docs)
    } catch {
      // keep previous state
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchDocs() }, [fetchDocs, refreshKey])

  useEffect(() => {
    const hasPending = documents.some(d => d.status === 'pending' || d.status === 'processing')
    if (hasPending) {
      pollRef.current = setInterval(fetchDocs, POLL_INTERVAL)
    }
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [documents, fetchDocs])

  const handleDownload = useCallback(async (id: number) => {
    try {
      const result = await downloadDocument(id)
      window.open(result.download_url, '_blank')
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
        prev.map(d => d.id === reingestTarget.id ? { ...d, status: 'pending' as const, error_message: null, total_chunks: 0 } : d)
      )
    } catch { /* ignore */ }
    finally { setReingestTarget(null) }
  }, [reingestTarget])

  const columns = useMemo<ColumnDef<DocumentListItem, unknown>[]>(() => [
    {
      id: 'title',
      accessorFn: row => row.title,
      header: () => t('docs.table.name'),
      cell: ({ row }) => (
        <div>
          <div className="docs-name">{row.original.title}</div>
          <div className="docs-filename">{row.original.original_filename}</div>
        </div>
      ),
      enableGrouping: true,
    },
    {
      id: 'format',
      accessorKey: 'format',
      header: () => t('docs.table.format'),
      cell: ({ getValue }) => <span className="docs-format">{String(getValue())}</span>,
      enableGrouping: true,
    },
    {
      id: 'status',
      accessorKey: 'status',
      header: () => t('docs.table.status'),
      cell: ({ row }) => <StatusBadge status={row.original.status} errorMessage={row.original.error_message} />,
      enableGrouping: true,
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
      meta: { className: 'col-chunks' },
    },
    {
      id: 'product',
      accessorKey: 'product_name',
      header: () => t('docs.table.product'),
      cell: ({ getValue }) => <span className="docs-product">{String(getValue() || '—')}</span>,
      enableGrouping: true,
    },
    {
      id: 'date',
      accessorFn: row => row.ingested_at,
      header: () => t('docs.table.date'),
      cell: ({ getValue }) => <span className="docs-date">{formatDate(getValue() as string | null)}</span>,
      enableGrouping: false,
      sortingFn: 'datetime',
    },
    {
      id: 'actions',
      header: () => t('docs.table.actions'),
      enableSorting: false,
      enableGrouping: false,
      cell: ({ row }) => {
        const doc = row.original
        return (
          <div className="docs-actions">
            {doc.status === 'ready' && (
              <button className="docs-action-btn" onClick={() => handleDownload(doc.id)} title={t('docs.actions.download')}>
                <Download size={16} />
              </button>
            )}
            {(doc.status === 'ready' || doc.status === 'error') && (
              <button className="docs-action-btn" onClick={() => setReingestTarget(doc)} title={t('docs.actions.reindex')}>
                <RefreshCw size={16} />
              </button>
            )}
            <button className="docs-action-btn docs-action-btn--danger" onClick={() => setDeleteTarget(doc)} title={t('docs.actions.delete')}>
              <Trash2 size={16} />
            </button>
          </div>
        )
      },
    },
  ], [t, handleDownload])

  const table = useReactTable({
    data: documents,
    columns,
    state: { sorting, globalFilter, columnOrder, grouping, expanded },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    onColumnOrderChange: setColumnOrder,
    onGroupingChange: setGrouping,
    onExpandedChange: setExpanded,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getGroupedRowModel: getGroupedRowModel(),
    getExpandedRowModel: getExpandedRowModel(),
    enableMultiSort: true,
    getRowId: row => String(row.id),
  })

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor),
  )

  const handleDragStart = useCallback((event: DragStartEvent) => {
    setActiveId(String(event.active.id))
  }, [])

  const handleDragEnd = useCallback((event: DragEndEvent) => {
    setActiveId(null)
    const { active, over } = event
    if (!over || active.id === over.id) return
    setColumnOrder(prev => {
      const oldIndex = prev.indexOf(String(active.id))
      const newIndex = prev.indexOf(String(over.id))
      return arrayMove(prev, oldIndex, newIndex)
    })
  }, [])

  const removeGrouping = useCallback((columnId: string) => {
    setGrouping(prev => prev.filter(g => g !== columnId))
  }, [])

  const toggleGrouping = useCallback((columnId: string) => {
    setGrouping(prev =>
      prev.includes(columnId)
        ? prev.filter(g => g !== columnId)
        : [...prev, columnId]
    )
  }, [])

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
    <div className="docs-page">
      <div className="docs-header">
        <h1>{t('docs.title')}</h1>
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
          <button className="docs-upload-btn" onClick={onUploadClick}>
            <Upload size={16} />
            <span>{t('docs.upload')}</span>
          </button>
        </div>
      </div>

      {grouping.length > 0 && (
        <div className="docs-group-bar">
          <Layers size={14} />
          <span className="docs-group-bar-label">{t('docs.group.label')}:</span>
          {grouping.map(colId => {
            const col = table.getColumn(colId)
            const label = col ? flexRender(col.columnDef.header, { table, header: null as never, column: col }) : colId
            return (
              <span key={colId} className="docs-group-chip">
                {label}
                <button className="docs-group-chip-remove" onClick={() => removeGrouping(colId)}>
                  <X size={12} />
                </button>
              </span>
            )
          })}
        </div>
      )}

      {/* Desktop/Tablet: TanStack Table */}
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
        <div className="docs-table-wrap">
          <table className="docs-table">
            <thead>
              {table.getHeaderGroups().map(headerGroup => (
                <tr key={headerGroup.id}>
                  <SortableContext items={columnOrder} strategy={horizontalListSortingStrategy}>
                    {headerGroup.headers.map(header => {
                      const meta = header.column.columnDef.meta as { className?: string } | undefined
                      if (header.id === 'actions') {
                        return (
                          <th key={header.id} className={meta?.className}>
                            <div className="docs-th-inner">
                              <span className="docs-th-label">
                                {flexRender(header.column.columnDef.header, header.getContext())}
                              </span>
                            </div>
                          </th>
                        )
                      }
                      return (
                        <DraggableHeader key={header.id} header={header}>
                          {flexRender(header.column.columnDef.header, header.getContext())}
                        </DraggableHeader>
                      )
                    })}
                  </SortableContext>
                </tr>
              ))}
            </thead>
            <tbody>
              {table.getRowModel().rows.map(row => (
                <tr key={row.id} className={row.getIsGrouped() ? 'docs-row-group' : undefined}>
                  {row.getVisibleCells().map(cell => {
                    const meta = cell.column.columnDef.meta as { className?: string } | undefined
                    if (cell.getIsGrouped()) {
                      return (
                        <td key={cell.id} colSpan={row.getVisibleCells().length} className="docs-group-cell">
                          <button className="docs-group-toggle" onClick={row.getToggleExpandedHandler()}>
                            {row.getIsExpanded() ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                            <span className="docs-group-value">
                              {flexRender(cell.column.columnDef.cell, cell.getContext())}
                            </span>
                            <span className="docs-group-count">({row.subRows.length})</span>
                          </button>
                        </td>
                      )
                    }
                    if (cell.getIsAggregated()) return null
                    if (cell.getIsPlaceholder()) return <td key={cell.id} className={meta?.className} />
                    return (
                      <td key={cell.id} className={meta?.className}>
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <DragOverlay>
          {activeId ? (
            <div className="docs-drag-overlay">
              {(() => {
                const col = table.getColumn(activeId)
                return col ? flexRender(col.columnDef.header, { table, header: null as never, column: col }) : activeId
              })()}
            </div>
          ) : null}
        </DragOverlay>
      </DndContext>

      {/* Context menu for grouping */}
      <div className="docs-group-actions">
        {table.getAllLeafColumns()
          .filter(col => col.getCanGroup() && col.id !== 'actions')
          .map(col => (
            <button
              key={col.id}
              className={`docs-group-action-btn ${grouping.includes(col.id) ? 'docs-group-action-btn--active' : ''}`}
              onClick={() => toggleGrouping(col.id)}
              title={t('docs.group.toggle')}
            >
              <Layers size={12} />
              {flexRender(col.columnDef.header, { table, header: null as never, column: col })}
            </button>
          ))}
      </div>

      {/* Mobile: Cards */}
      <div className="docs-cards">
        {documents
          .filter(doc => {
            if (!globalFilter) return true
            const q = globalFilter.toLowerCase()
            return (
              doc.title.toLowerCase().includes(q) ||
              doc.original_filename.toLowerCase().includes(q) ||
              doc.format.toLowerCase().includes(q) ||
              (doc.product_name || '').toLowerCase().includes(q)
            )
          })
          .map(doc => (
            <div className="docs-card" key={doc.id}>
              <div className="docs-card-header">
                <div className="docs-card-title">{doc.title}</div>
                <StatusBadge status={doc.status} errorMessage={doc.error_message} />
              </div>
              <div className="docs-card-meta">
                <span><span className="docs-format">{doc.format}</span></span>
                <span>{formatBytes(doc.file_size_bytes)}</span>
                {doc.product_name && <span>{doc.product_name}</span>}
                <span>{formatDate(doc.ingested_at)}</span>
              </div>
              <div className="docs-card-actions">
                {doc.status === 'ready' && (
                  <button className="docs-action-btn" onClick={() => handleDownload(doc.id)} title={t('docs.actions.download')}>
                    <Download size={16} />
                  </button>
                )}
                {(doc.status === 'ready' || doc.status === 'error') && (
                  <button className="docs-action-btn" onClick={() => setReingestTarget(doc)} title={t('docs.actions.reindex')}>
                    <RefreshCw size={16} />
                  </button>
                )}
                <button className="docs-action-btn docs-action-btn--danger" onClick={() => setDeleteTarget(doc)} title={t('docs.actions.delete')}>
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
          ))}
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
    </div>
  )
}
