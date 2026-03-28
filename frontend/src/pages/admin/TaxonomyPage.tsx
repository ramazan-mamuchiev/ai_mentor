import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Plus, Trash2, Pencil, Tags, Check, X as XIcon } from 'lucide-react'
import type { ColumnDef } from '@tanstack/react-table'
import {
  adminListCategories,
  adminCreateCategory,
  adminPatchCategory,
  adminDeleteCategory,
  adminListTags,
  adminCreateTag,
  adminDeleteTag,
  type CategoryItem,
  type TagItem,
} from '../../api/admin-taxonomy'
import { TenantFilterCombo } from '../../components/TenantFilterCombo'
import { DataTable } from '../../components/DataTable'
import { useDataTable } from '../../hooks/useDataTable'
import type { TenantSearchResult } from '../../api/admin'

const CAT_STORAGE_KEY = 'lexiro-admin-taxonomy-categories'
const TAG_STORAGE_KEY = 'lexiro-admin-taxonomy-tags'
const CAT_DEFAULT_ORDER = ['slug', 'icon', 'sortOrder', 'labelEn', 'labelRu', 'products', 'modifiedBy', 'modifiedAt', 'actions']
const TAG_DEFAULT_ORDER = ['slug', 'labelEn', 'labelRu', 'products', 'modifiedBy', 'modifiedAt', 'actions']

export function TaxonomyPage() {
  const { t } = useTranslation()

  const relativeTime = useCallback((iso: string | null): string => {
    if (!iso) return ''
    const diff = Date.now() - new Date(iso).getTime()
    const mins = Math.floor(diff / 60000)
    if (mins < 1) return t('admin.common.justNow')
    if (mins < 60) return t('admin.common.minutesAgo', { count: mins })
    const hours = Math.floor(mins / 60)
    if (hours < 24) return t('admin.common.hoursAgo', { count: hours })
    const days = Math.floor(hours / 24)
    return t('admin.common.daysAgo', { count: days })
  }, [t])

  const [tab, setTab] = useState<'categories' | 'tags'>('categories')
  const [categories, setCategories] = useState<CategoryItem[]>([])
  const [tags, setTags] = useState<TagItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [newCatSlug, setNewCatSlug] = useState('')
  const [newCatIcon, setNewCatIcon] = useState('')
  const [newCatLabelEn, setNewCatLabelEn] = useState('')
  const [newCatLabelRu, setNewCatLabelRu] = useState('')

  const [newTagSlug, setNewTagSlug] = useState('')
  const [newTagLabelEn, setNewTagLabelEn] = useState('')
  const [newTagLabelRu, setNewTagLabelRu] = useState('')

  const [tenantFilter, setTenantFilter] = useState<TenantSearchResult | null>(null)

  const [editingCategoryId, setEditingCategoryId] = useState<number | null>(null)
  const [editIcon, setEditIcon] = useState('')
  const [editSortOrder, setEditSortOrder] = useState(0)
  const [editLabelEn, setEditLabelEn] = useState('')
  const [editLabelRu, setEditLabelRu] = useState('')
  const [savingEdit, setSavingEdit] = useState(false)

  const loadData = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [cats, tgs] = await Promise.all([adminListCategories(tenantFilter?.id), adminListTags(tenantFilter?.id)])
      setCategories(cats)
      setTags(tgs)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      setError(msg)
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [tenantFilter])

  useEffect(() => {
    void loadData()
  }, [loadData])

  const startEditCategory = (cat: CategoryItem) => {
    setEditingCategoryId(cat.id)
    setEditIcon(cat.icon ?? '')
    setEditSortOrder(cat.sort_order)
    setEditLabelEn(cat.labels?.en ?? '')
    setEditLabelRu(cat.labels?.ru ?? '')
  }

  const cancelEditCategory = () => {
    setEditingCategoryId(null)
  }

  const handleSaveCategory = async (id: number) => {
    setSavingEdit(true)
    try {
      await adminPatchCategory(id, {
        icon: editIcon.trim(),
        sort_order: editSortOrder,
        labels: { en: editLabelEn.trim(), ru: editLabelRu.trim() },
      })
      setEditingCategoryId(null)
      await loadData()
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      setError(msg)
      console.error(e)
    } finally {
      setSavingEdit(false)
    }
  }

  const handleCreateCategory = async () => {
    if (!newCatSlug.trim()) return
    try {
      await adminCreateCategory({
        slug: newCatSlug.trim(),
        icon: newCatIcon.trim(),
        labels: {
          en: newCatLabelEn.trim() || newCatSlug.trim(),
          ru: newCatLabelRu.trim() || newCatSlug.trim(),
        },
      })
      setNewCatSlug('')
      setNewCatIcon('')
      setNewCatLabelEn('')
      setNewCatLabelRu('')
      await loadData()
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      setError(msg)
      console.error(e)
    }
  }

  const handleDeleteCategory = async (id: number, isSystem: boolean) => {
    if (isSystem) return
    if (!confirm(t('admin.taxonomy.confirmDeleteCategory'))) return
    try {
      await adminDeleteCategory(id)
      if (editingCategoryId === id) setEditingCategoryId(null)
      await loadData()
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      setError(msg)
      console.error(e)
    }
  }

  const handleCreateTag = async () => {
    if (!newTagSlug.trim()) return
    try {
      await adminCreateTag({
        slug: newTagSlug.trim(),
        labels: {
          en: newTagLabelEn.trim() || newTagSlug.trim(),
          ru: newTagLabelRu.trim() || newTagSlug.trim(),
        },
      })
      setNewTagSlug('')
      setNewTagLabelEn('')
      setNewTagLabelRu('')
      await loadData()
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      setError(msg)
      console.error(e)
    }
  }

  const handleDeleteTag = async (id: number, isSystem: boolean) => {
    if (isSystem) return
    if (!confirm(t('admin.taxonomy.confirmDeleteTag'))) return
    try {
      await adminDeleteTag(id)
      await loadData()
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      setError(msg)
      console.error(e)
    }
  }

  const labelOrDash = (v: string | undefined) => (v?.trim() ? v : t('admin.taxonomy.noLabel'))

  /* ---- Category columns ---- */
  const categoryColumns = useMemo<ColumnDef<CategoryItem, unknown>[]>(() => [
    {
      id: 'slug',
      accessorKey: 'slug',
      header: () => t('admin.taxonomy.slug'),
      cell: ({ row }) => {
        const cat = row.original
        return <code>{cat.slug}</code>
      },
      enableGrouping: false,
    },
    {
      id: 'icon',
      accessorKey: 'icon',
      header: () => t('admin.taxonomy.icon'),
      cell: ({ row }) => {
        const cat = row.original
        if (editingCategoryId === cat.id) {
          return (
            <input
              style={{ width: '100%', maxWidth: 120, padding: '4px 8px', borderRadius: 'var(--radius)', border: '1px solid var(--border)' }}
              value={editIcon}
              onChange={e => setEditIcon(e.target.value)}
            />
          )
        }
        return cat.icon?.trim() ? cat.icon : t('admin.taxonomy.noLabel')
      },
      enableGrouping: false,
    },
    {
      id: 'sortOrder',
      accessorKey: 'sort_order',
      header: () => t('admin.taxonomy.sortOrder'),
      cell: ({ row }) => {
        const cat = row.original
        if (editingCategoryId === cat.id) {
          return (
            <input
              type="number"
              style={{ width: 72, padding: '4px 8px', borderRadius: 'var(--radius)', border: '1px solid var(--border)' }}
              value={editSortOrder}
              onChange={e => setEditSortOrder(Number(e.target.value))}
            />
          )
        }
        return cat.sort_order
      },
      enableGrouping: false,
    },
    {
      id: 'labelEn',
      accessorFn: row => row.labels?.en ?? '',
      header: () => t('admin.taxonomy.labelEn'),
      cell: ({ row }) => {
        const cat = row.original
        if (editingCategoryId === cat.id) {
          return (
            <input
              style={{ width: '100%', minWidth: 100, padding: '4px 8px', borderRadius: 'var(--radius)', border: '1px solid var(--border)' }}
              value={editLabelEn}
              onChange={e => setEditLabelEn(e.target.value)}
            />
          )
        }
        return labelOrDash(cat.labels?.en)
      },
      enableGrouping: false,
    },
    {
      id: 'labelRu',
      accessorFn: row => row.labels?.ru ?? '',
      header: () => t('admin.taxonomy.labelRu'),
      cell: ({ row }) => {
        const cat = row.original
        if (editingCategoryId === cat.id) {
          return (
            <input
              style={{ width: '100%', minWidth: 100, padding: '4px 8px', borderRadius: 'var(--radius)', border: '1px solid var(--border)' }}
              value={editLabelRu}
              onChange={e => setEditLabelRu(e.target.value)}
            />
          )
        }
        return labelOrDash(cat.labels?.ru)
      },
      enableGrouping: false,
    },
    {
      id: 'products',
      accessorKey: 'product_count',
      header: () => t('admin.taxonomy.products'),
      cell: ({ getValue }) => <span className="docs-chunks">{Number(getValue())}</span>,
      enableGrouping: false,
    },
    {
      id: 'modifiedBy',
      accessorFn: row => row.modified_by_name || row.modified_by_email || '',
      header: () => t('admin.common.modifiedBy'),
      cell: ({ getValue }) => <span className="audit-cell">{String(getValue())}</span>,
      enableGrouping: false,
    },
    {
      id: 'modifiedAt',
      accessorKey: 'modified_at',
      header: () => t('admin.common.modifiedAt'),
      cell: ({ getValue }) => <span className="audit-cell">{relativeTime(getValue() as string | null)}</span>,
      enableGrouping: false,
      sortingFn: 'datetime',
    },
    {
      id: 'actions',
      header: () => t('admin.common.actions'),
      enableSorting: false,
      enableGrouping: false,
      cell: ({ row }) => {
        const cat = row.original
        if (editingCategoryId === cat.id) {
          return (
            <div className="docs-actions">
              <button
                className="docs-action-btn"
                disabled={savingEdit}
                onClick={() => void handleSaveCategory(cat.id)}
              >
                <Check size={14} />
              </button>
              <button className="docs-action-btn" onClick={cancelEditCategory}>
                <XIcon size={14} />
              </button>
            </div>
          )
        }
        return (
          <div className="docs-actions">
            <button
              className="docs-action-btn"
              disabled={cat.is_system}
              onClick={() => !cat.is_system && startEditCategory(cat)}
            >
              <Pencil size={14} />
            </button>
            <button
              className="docs-action-btn"
              disabled={cat.is_system}
              onClick={() => void handleDeleteCategory(cat.id, cat.is_system)}
            >
              <Trash2 size={14} />
            </button>
          </div>
        )
      },
    },
  ], [t, editingCategoryId, editIcon, editSortOrder, editLabelEn, editLabelRu, savingEdit, relativeTime])

  /* ---- Tag columns ---- */
  const tagColumns = useMemo<ColumnDef<TagItem, unknown>[]>(() => [
    {
      id: 'slug',
      accessorKey: 'slug',
      header: () => t('admin.taxonomy.slug'),
      cell: ({ getValue }) => <code>{String(getValue())}</code>,
      enableGrouping: false,
    },
    {
      id: 'labelEn',
      accessorFn: row => row.labels?.en ?? '',
      header: () => t('admin.taxonomy.labelEn'),
      cell: ({ row }) => labelOrDash(row.original.labels?.en),
      enableGrouping: false,
    },
    {
      id: 'labelRu',
      accessorFn: row => row.labels?.ru ?? '',
      header: () => t('admin.taxonomy.labelRu'),
      cell: ({ row }) => labelOrDash(row.original.labels?.ru),
      enableGrouping: false,
    },
    {
      id: 'products',
      accessorKey: 'product_count',
      header: () => t('admin.taxonomy.products'),
      cell: ({ getValue }) => <span className="docs-chunks">{Number(getValue())}</span>,
      enableGrouping: false,
    },
    {
      id: 'modifiedBy',
      accessorFn: row => row.modified_by_name || row.modified_by_email || '',
      header: () => t('admin.common.modifiedBy'),
      cell: ({ getValue }) => <span className="audit-cell">{String(getValue())}</span>,
      enableGrouping: false,
    },
    {
      id: 'modifiedAt',
      accessorKey: 'modified_at',
      header: () => t('admin.common.modifiedAt'),
      cell: ({ getValue }) => <span className="audit-cell">{relativeTime(getValue() as string | null)}</span>,
      enableGrouping: false,
      sortingFn: 'datetime',
    },
    {
      id: 'actions',
      header: () => t('admin.common.actions'),
      enableSorting: false,
      enableGrouping: false,
      cell: ({ row }) => {
        const tag = row.original
        return (
          <div className="docs-actions">
            <button
              className="docs-action-btn"
              disabled={tag.is_system}
              onClick={() => void handleDeleteTag(tag.id, tag.is_system)}
            >
              <Trash2 size={14} />
            </button>
          </div>
        )
      },
    },
  ], [t, relativeTime])

  const catTable = useDataTable({
    data: categories,
    columns: categoryColumns,
    storageKey: CAT_STORAGE_KEY,
    defaultColumnOrder: CAT_DEFAULT_ORDER,
    defaultSorting: [{ id: 'sortOrder', desc: false }],
    getRowId: row => String(row.id),
  })

  const tagTable = useDataTable({
    data: tags,
    columns: tagColumns,
    storageKey: TAG_STORAGE_KEY,
    defaultColumnOrder: TAG_DEFAULT_ORDER,
    defaultSorting: [{ id: 'slug', desc: false }],
    getRowId: row => String(row.id),
  })

  return (
    <div className="logs-page">
      <div className="admin-page-header">
        <h1>
          <Tags size={20} /> {t('admin.nav.taxonomy')}
        </h1>
      </div>

      <div className="logs-toolbar">
        <div className="logs-toolbar__row">
          <div className="logs-chips" role="group">
            <button
              type="button"
              className={`logs-chip${tab === 'categories' ? ' logs-chip--active' : ''}`}
              onClick={() => setTab('categories')}
            >
              {t('admin.taxonomy.tabCategories', { count: categories.length })}
            </button>
            <button
              type="button"
              className={`logs-chip${tab === 'tags' ? ' logs-chip--active' : ''}`}
              onClick={() => setTab('tags')}
            >
              {t('admin.taxonomy.tabTags', { count: tags.length })}
            </button>
          </div>

          <TenantFilterCombo value={tenantFilter} onChange={setTenantFilter} />
        </div>
      </div>

      {error && <div className="admin-error">{error}</div>}

      {tab === 'categories' && (
        <>
          <div className="logs-toolbar" style={{ marginTop: 8 }}>
            <div className="logs-toolbar__row">
              <input
                value={newCatSlug}
                onChange={e => setNewCatSlug(e.target.value)}
                placeholder={t('admin.taxonomy.placeholderSlug')}
                className="logs-search"
                style={{ width: 140, minWidth: 100 }}
              />
              <input
                value={newCatIcon}
                onChange={e => setNewCatIcon(e.target.value)}
                placeholder={t('admin.taxonomy.placeholderIcon')}
                className="logs-search"
                style={{ width: 100, minWidth: 70 }}
              />
              <input
                value={newCatLabelEn}
                onChange={e => setNewCatLabelEn(e.target.value)}
                placeholder={t('admin.taxonomy.placeholderLabelEn')}
                className="logs-search"
                style={{ width: 140, minWidth: 100 }}
              />
              <input
                value={newCatLabelRu}
                onChange={e => setNewCatLabelRu(e.target.value)}
                placeholder={t('admin.taxonomy.placeholderLabelRu')}
                className="logs-search"
                style={{ width: 140, minWidth: 100 }}
              />
              <button
                type="button"
                className="admin-btn admin-btn--primary"
                disabled={!newCatSlug.trim()}
                onClick={() => void handleCreateCategory()}
              >
                <Plus size={14} /> {t('admin.common.create')}
              </button>
            </div>
          </div>

          {loading ? (
            <div className="admin-loading">{t('admin.common.loading')}</div>
          ) : categories.length === 0 ? (
            <div className="admin-empty">{t('admin.taxonomy.emptyCategories')}</div>
          ) : (
            <DataTable
              table={catTable.table}
              columnOrder={catTable.columnOrder}
              grouping={catTable.grouping}
              onColumnOrderChange={catTable.handleColumnOrderChange}
              removeGrouping={catTable.removeGrouping}
              toggleGrouping={catTable.toggleGrouping}
              resetSettings={catTable.resetSettings}
            />
          )}
        </>
      )}

      {tab === 'tags' && (
        <>
          <div className="logs-toolbar" style={{ marginTop: 8 }}>
            <div className="logs-toolbar__row">
              <input
                value={newTagSlug}
                onChange={e => setNewTagSlug(e.target.value)}
                placeholder={t('admin.taxonomy.placeholderSlug')}
                className="logs-search"
                style={{ width: 140, minWidth: 100 }}
              />
              <input
                value={newTagLabelEn}
                onChange={e => setNewTagLabelEn(e.target.value)}
                placeholder={t('admin.taxonomy.placeholderLabelEn')}
                className="logs-search"
                style={{ width: 140, minWidth: 100 }}
              />
              <input
                value={newTagLabelRu}
                onChange={e => setNewTagLabelRu(e.target.value)}
                placeholder={t('admin.taxonomy.placeholderLabelRu')}
                className="logs-search"
                style={{ width: 140, minWidth: 100 }}
              />
              <button
                type="button"
                className="admin-btn admin-btn--primary"
                disabled={!newTagSlug.trim()}
                onClick={() => void handleCreateTag()}
              >
                <Plus size={14} /> {t('admin.common.create')}
              </button>
            </div>
          </div>

          {loading ? (
            <div className="admin-loading">{t('admin.common.loading')}</div>
          ) : tags.length === 0 ? (
            <div className="admin-empty">{t('admin.taxonomy.emptyTags')}</div>
          ) : (
            <DataTable
              table={tagTable.table}
              columnOrder={tagTable.columnOrder}
              grouping={tagTable.grouping}
              onColumnOrderChange={tagTable.handleColumnOrderChange}
              removeGrouping={tagTable.removeGrouping}
              toggleGrouping={tagTable.toggleGrouping}
              resetSettings={tagTable.resetSettings}
            />
          )}
        </>
      )}
    </div>
  )
}
