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

export function TaxonomyPage() {
  const { t } = useTranslation()
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
      const [cats, tgs] = await Promise.all([adminListCategories(), adminListTags()])
      setCategories(cats)
      setTags(tgs)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      setError(msg)
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [])

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
    <div className="admin-page">
      <div className="admin-page-header">
        <h1>
          <Tags size={20} /> {t('admin.nav.taxonomy')}
        </h1>
      </div>

      <div className="stats-toolbar" style={{ marginBottom: 16 }}>
        <div className="stats-tabs">
          <button
            type="button"
            className={`stats-tab${tab === 'categories' ? ' stats-tab--active' : ''}`}
            onClick={() => setTab('categories')}
          >
            {t('admin.taxonomy.tabCategories', { count: categories.length })}
          </button>
          <button
            type="button"
            className={`stats-tab${tab === 'tags' ? ' stats-tab--active' : ''}`}
            onClick={() => setTab('tags')}
          >
            {t('admin.taxonomy.tabTags', { count: tags.length })}
          </button>
        </div>
      </div>

      {error && <div className="admin-error">{error}</div>}

      {tab === 'categories' && (
        <>
          <div className="admin-card" style={{ marginBottom: 16 }}>
            <div className="admin-form-row" style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'flex-end' }}>
              <div style={{ flex: '1 1 140px', minWidth: 120 }}>
                <label>{t('admin.taxonomy.slug')}</label>
                <input
                  value={newCatSlug}
                  onChange={e => setNewCatSlug(e.target.value)}
                  placeholder={t('admin.taxonomy.placeholderSlug')}
                />
              </div>
              <div style={{ flex: '1 1 100px', minWidth: 80 }}>
                <label>{t('admin.taxonomy.icon')}</label>
                <input
                  value={newCatIcon}
                  onChange={e => setNewCatIcon(e.target.value)}
                  placeholder={t('admin.taxonomy.placeholderIcon')}
                />
              </div>
              <div style={{ flex: '1 1 140px', minWidth: 120 }}>
                <label>{t('admin.taxonomy.labelEn')}</label>
                <input
                  value={newCatLabelEn}
                  onChange={e => setNewCatLabelEn(e.target.value)}
                  placeholder={t('admin.taxonomy.placeholderLabelEn')}
                />
              </div>
              <div style={{ flex: '1 1 140px', minWidth: 120 }}>
                <label>{t('admin.taxonomy.labelRu')}</label>
                <input
                  value={newCatLabelRu}
                  onChange={e => setNewCatLabelRu(e.target.value)}
                  placeholder={t('admin.taxonomy.placeholderLabelRu')}
                />
              </div>
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
                          <td>
                            <div className="admin-actions">
                              <button
                                type="button"
                                className="admin-btn admin-btn--sm admin-btn--primary"
                                disabled={savingEdit}
                                onClick={() => void handleSaveCategory(cat.id)}
                              >
                                {t('admin.common.save')}
                              </button>
                              <button type="button" className="admin-btn admin-btn--sm" onClick={cancelEditCategory}>
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
                          <td>
                            <div className="admin-actions">
                              <button
                                type="button"
                                className="admin-btn admin-btn--sm"
                                disabled={cat.is_system}
                                title={cat.is_system ? t('admin.taxonomy.systemCategory') : t('admin.taxonomy.edit')}
                                onClick={() => !cat.is_system && startEditCategory(cat)}
                              >
                                <Pencil size={14} />
                              </button>
                              <button
                                type="button"
                                className="admin-btn admin-btn--sm admin-btn--danger"
                                disabled={cat.is_system}
                                title={cat.is_system ? t('admin.taxonomy.systemCategory') : t('admin.common.delete')}
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
          <div className="admin-card" style={{ marginBottom: 16 }}>
            <div className="admin-form-row" style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'flex-end' }}>
              <div style={{ flex: '1 1 140px', minWidth: 120 }}>
                <label>{t('admin.taxonomy.slug')}</label>
                <input
                  value={newTagSlug}
                  onChange={e => setNewTagSlug(e.target.value)}
                  placeholder={t('admin.taxonomy.placeholderSlug')}
                />
              </div>
              <div style={{ flex: '1 1 140px', minWidth: 120 }}>
                <label>{t('admin.taxonomy.labelEn')}</label>
                <input
                  value={newTagLabelEn}
                  onChange={e => setNewTagLabelEn(e.target.value)}
                  placeholder={t('admin.taxonomy.placeholderLabelEn')}
                />
              </div>
              <div style={{ flex: '1 1 140px', minWidth: 120 }}>
                <label>{t('admin.taxonomy.labelRu')}</label>
                <input
                  value={newTagLabelRu}
                  onChange={e => setNewTagLabelRu(e.target.value)}
                  placeholder={t('admin.taxonomy.placeholderLabelRu')}
                />
              </div>
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
                        <td>
                          <button
                            type="button"
                            className="admin-btn admin-btn--sm admin-btn--danger"
                            disabled={tag.is_system}
                            title={tag.is_system ? t('admin.taxonomy.systemTag') : t('admin.common.delete')}
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
