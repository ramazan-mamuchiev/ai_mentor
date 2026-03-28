import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Plus, Trash2, Pencil, Tags } from 'lucide-react'
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
import type { TenantSearchResult } from '../../api/admin'

export function TaxonomyPage() {
  const { t } = useTranslation()

  const relativeTime = (iso: string | null): string => {
    if (!iso) return ''
    const diff = Date.now() - new Date(iso).getTime()
    const mins = Math.floor(diff / 60000)
    if (mins < 1) return t('admin.common.justNow')
    if (mins < 60) return t('admin.common.minutesAgo', { count: mins })
    const hours = Math.floor(mins / 60)
    if (hours < 24) return t('admin.common.hoursAgo', { count: hours })
    const days = Math.floor(hours / 24)
    return t('admin.common.daysAgo', { count: days })
  }
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

  return (
    <div className="logs-page">
      <div className="admin-page-header">
        <h1>
          <Tags size={20} /> {t('admin.nav.taxonomy')}
        </h1>
      </div>

      {/* Tabs — logs toolbar style */}
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

          <div className="admin-table-wrapper">
            {loading ? (
              <div className="admin-loading">{t('admin.common.loading')}</div>
            ) : (
              <div className="admin-table-scroll">
                <table className="admin-table">
                  <thead>
                    <tr>
                      <th>{t('admin.taxonomy.slug')}</th>
                      <th>{t('admin.taxonomy.icon')}</th>
                      <th>{t('admin.taxonomy.sortOrder')}</th>
                      <th>{t('admin.taxonomy.labelEn')}</th>
                      <th>{t('admin.taxonomy.labelRu')}</th>
                      <th>{t('admin.taxonomy.products')}</th>
                      <th>{t('admin.common.modifiedBy')}</th>
                      <th>{t('admin.common.modifiedAt')}</th>
                      <th>{t('admin.common.actions')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {categories.map(cat =>
                      editingCategoryId === cat.id ? (
                        <tr key={cat.id}>
                          <td>
                            <code>{cat.slug}</code>
                          </td>
                          <td>
                            <input
                              style={{ width: '100%', maxWidth: 120, padding: '6px 10px', borderRadius: 'var(--radius)', border: '1px solid var(--border)' }}
                              value={editIcon}
                              onChange={e => setEditIcon(e.target.value)}
                            />
                          </td>
                          <td>
                            <input
                              type="number"
                              style={{ width: 72, padding: '6px 10px', borderRadius: 'var(--radius)', border: '1px solid var(--border)' }}
                              value={editSortOrder}
                              onChange={e => setEditSortOrder(Number(e.target.value))}
                            />
                          </td>
                          <td>
                            <input
                              style={{ width: '100%', minWidth: 100, padding: '6px 10px', borderRadius: 'var(--radius)', border: '1px solid var(--border)' }}
                              value={editLabelEn}
                              onChange={e => setEditLabelEn(e.target.value)}
                            />
                          </td>
                          <td>
                            <input
                              style={{ width: '100%', minWidth: 100, padding: '6px 10px', borderRadius: 'var(--radius)', border: '1px solid var(--border)' }}
                              value={editLabelRu}
                              onChange={e => setEditLabelRu(e.target.value)}
                            />
                          </td>
                          <td>{cat.product_count}</td>
                          <td className="audit-cell">{cat.modified_by_name || cat.modified_by_email || ''}</td>
                          <td className="audit-cell">{relativeTime(cat.modified_at)}</td>
                          <td>
                            <div className="admin-actions">
                              <button
                                type="button"
                                className="admin-btn admin-btn--primary admin-btn--sm"
                                disabled={savingEdit}
                                onClick={() => void handleSaveCategory(cat.id)}
                              >
                                {t('admin.common.save')}
                              </button>
                              <button type="button" className="logs-icon-btn" onClick={cancelEditCategory}>
                                {t('admin.common.cancel')}
                              </button>
                            </div>
                          </td>
                        </tr>
                      ) : (
                        <tr key={cat.id}>
                          <td>
                            <code>{cat.slug}</code>
                          </td>
                          <td>{cat.icon?.trim() ? cat.icon : t('admin.taxonomy.noLabel')}</td>
                          <td>{cat.sort_order}</td>
                          <td>{labelOrDash(cat.labels?.en)}</td>
                          <td>{labelOrDash(cat.labels?.ru)}</td>
                          <td>{cat.product_count}</td>
                          <td className="audit-cell">{cat.modified_by_name || cat.modified_by_email || ''}</td>
                          <td className="audit-cell">{relativeTime(cat.modified_at)}</td>
                          <td>
                            <div className="admin-actions">
                              <button
                                type="button"
                                className="logs-icon-btn"
                                disabled={cat.is_system}
                                onClick={() => !cat.is_system && startEditCategory(cat)}
                              >
                                <Pencil size={14} />
                              </button>
                              <button
                                type="button"
                                className="logs-icon-btn"
                                disabled={cat.is_system}
                                onClick={() => void handleDeleteCategory(cat.id, cat.is_system)}
                              >
                                <Trash2 size={14} />
                              </button>
                            </div>
                          </td>
                        </tr>
                      ),
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </div>
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

          <div className="admin-table-wrapper">
            {loading ? (
              <div className="admin-loading">{t('admin.common.loading')}</div>
            ) : (
              <div className="admin-table-scroll">
                <table className="admin-table">
                  <thead>
                    <tr>
                      <th>{t('admin.taxonomy.slug')}</th>
                      <th>{t('admin.taxonomy.labelEn')}</th>
                      <th>{t('admin.taxonomy.labelRu')}</th>
                      <th>{t('admin.taxonomy.products')}</th>
                      <th>{t('admin.common.modifiedBy')}</th>
                      <th>{t('admin.common.modifiedAt')}</th>
                      <th>{t('admin.common.actions')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tags.map(tag => (
                      <tr key={tag.id}>
                        <td>
                          <code>{tag.slug}</code>
                        </td>
                        <td>{labelOrDash(tag.labels?.en)}</td>
                        <td>{labelOrDash(tag.labels?.ru)}</td>
                        <td>{tag.product_count}</td>
                        <td className="audit-cell">{tag.modified_by_name || tag.modified_by_email || ''}</td>
                        <td className="audit-cell">{relativeTime(tag.modified_at)}</td>
                        <td>
                          <button
                            type="button"
                            className="logs-icon-btn"
                            disabled={tag.is_system}
                            onClick={() => void handleDeleteTag(tag.id, tag.is_system)}
                          >
                            <Trash2 size={14} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
