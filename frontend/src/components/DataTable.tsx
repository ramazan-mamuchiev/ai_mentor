import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  ArrowUp,
  ArrowDown,
  ArrowUpDown,
  GripVertical,
  X,
  Layers,
  ChevronRight,
  ChevronDown,
  Settings2,
  Eye,
  EyeOff,
  RotateCcw,
} from 'lucide-react'
import {
  flexRender,
  type Table,
  type Row,
  type ColumnOrderState,
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

function SortIcon({ direction }: { direction: false | 'asc' | 'desc' }) {
  if (direction === 'asc') return <ArrowUp size={14} className="docs-sort-icon docs-sort-icon--active" />
  if (direction === 'desc') return <ArrowDown size={14} className="docs-sort-icon docs-sort-icon--active" />
  return <ArrowUpDown size={14} className="docs-sort-icon" />
}

function DraggableHeader({
  headerId,
  canSort,
  isSorted,
  toggleSortingHandler,
  children,
}: {
  headerId: string
  canSort: boolean
  isSorted: false | 'asc' | 'desc'
  toggleSortingHandler: ((e: unknown) => void) | undefined
  children: React.ReactNode
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: headerId })

  const style: React.CSSProperties = {
    transform: CSS.Translate.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  }

  return (
    <th ref={setNodeRef} style={style} className={`docs-th col-${headerId}`}>
      <div className="docs-th-inner">
        <span className="docs-th-drag" {...attributes} {...listeners}>
          <GripVertical size={12} />
        </span>
        <span
          className={canSort ? 'docs-th-label docs-th-label--sortable' : 'docs-th-label'}
          onClick={toggleSortingHandler}
        >
          {children}
          {canSort && <SortIcon direction={isSorted} />}
        </span>
      </div>
    </th>
  )
}

export interface DataTableProps<TData> {
  table: Table<TData>
  columnOrder: string[]
  grouping: string[]
  onColumnOrderChange: (updater: ColumnOrderState | ((old: ColumnOrderState) => ColumnOrderState)) => void
  removeGrouping: (columnId: string) => void
  toggleGrouping: (columnId: string) => void
  resetSettings: () => void
  renderExpandedRow?: (row: Row<TData>) => React.ReactNode | null
  actionsColumnId?: string
}

export function DataTable<TData>({
  table,
  columnOrder,
  grouping,
  onColumnOrderChange,
  removeGrouping,
  toggleGrouping,
  resetSettings,
  renderExpandedRow,
  actionsColumnId = 'actions',
}: DataTableProps<TData>) {
  const { t } = useTranslation()
  const [showColumnSettings, setShowColumnSettings] = useState(false)
  const [activeId, setActiveId] = useState<string | null>(null)
  const colSettingsRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!showColumnSettings) return
    const handler = (e: MouseEvent) => {
      if (colSettingsRef.current && !colSettingsRef.current.contains(e.target as Node)) {
        setShowColumnSettings(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [showColumnSettings])

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
    onColumnOrderChange(prev => {
      const oldIndex = prev.indexOf(String(active.id))
      const newIndex = prev.indexOf(String(over.id))
      return arrayMove(prev, oldIndex, newIndex)
    })
  }, [onColumnOrderChange])

  return (
    <>
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
                <button className="docs-group-chip-remove" onClick={() => removeGrouping(colId)} data-tooltip={t('docs.group.remove')}>
                  <X size={12} />
                </button>
              </span>
            )
          })}
        </div>
      )}

      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
        <div className="docs-table-wrap">
          <table className="docs-table">
            <thead>
              {table.getHeaderGroups().map(headerGroup => (
                <tr key={headerGroup.id}>
                  <SortableContext items={columnOrder} strategy={horizontalListSortingStrategy}>
                    {headerGroup.headers.map(header => {
                      if (header.id === actionsColumnId) {
                        return (
                          <th key={header.id} className={`docs-th docs-th--actions col-${header.id}`}>
                            <div className="docs-th-inner">
                              <span className="docs-th-label">
                                {flexRender(header.column.columnDef.header, header.getContext())}
                              </span>
                              <div className="docs-col-settings-wrap" ref={colSettingsRef}>
                                <button
                                  className="docs-col-settings-btn"
                                  onClick={() => setShowColumnSettings(v => !v)}
                                  data-tooltip={t('docs.columns.settings')}
                                >
                                  <Settings2 size={14} />
                                </button>
                                {showColumnSettings && (
                                  <div className="docs-col-settings-dropdown">
                                    <div className="docs-col-settings-title">{t('docs.columns.settings')}</div>
                                    {table.getAllLeafColumns()
                                      .filter(col => col.id !== actionsColumnId)
                                      .map(col => (
                                        <label key={col.id} className="docs-col-settings-item">
                                          <input
                                            type="checkbox"
                                            checked={col.getIsVisible()}
                                            onChange={col.getToggleVisibilityHandler()}
                                          />
                                          {col.getIsVisible() ? <Eye size={14} /> : <EyeOff size={14} />}
                                          <span>{flexRender(col.columnDef.header, { table, header: null as never, column: col })}</span>
                                        </label>
                                      ))}
                                    <div className="docs-col-settings-divider" />
                                    <button className="docs-col-settings-reset" onClick={() => { resetSettings(); setShowColumnSettings(false) }}>
                                      <RotateCcw size={14} />
                                      {t('docs.columns.reset')}
                                    </button>
                                  </div>
                                )}
                              </div>
                            </div>
                          </th>
                        )
                      }
                      return (
                        <DraggableHeader
                          key={header.id}
                          headerId={header.id}
                          canSort={header.column.getCanSort()}
                          isSorted={header.column.getIsSorted()}
                          toggleSortingHandler={header.column.getToggleSortingHandler()}
                        >
                          {flexRender(header.column.columnDef.header, header.getContext())}
                        </DraggableHeader>
                      )
                    })}
                  </SortableContext>
                </tr>
              ))}
            </thead>
            <tbody>
              {table.getRowModel().rows.map(row => {
                const expandedContent = renderExpandedRow?.(row)
                return (
                  <Fragment key={row.id}>
                    <tr className={row.getIsGrouped() ? 'docs-row-group' : undefined}>
                      {row.getVisibleCells().map(cell => {
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
                        if (cell.getIsAggregated() || cell.getIsPlaceholder()) return null
                        return (
                          <td key={cell.id} className={`col-${cell.column.id}`}>
                            {flexRender(cell.column.columnDef.cell, cell.getContext())}
                          </td>
                        )
                      })}
                    </tr>
                    {expandedContent && (
                      <tr className="docs-debug-expand-row">
                        <td colSpan={row.getVisibleCells().length}>
                          {expandedContent}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })}
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

      <div className="docs-group-actions">
        {table.getAllLeafColumns()
          .filter(col => col.getCanGroup() && col.id !== actionsColumnId)
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
    </>
  )
}
