import { useEffect, useMemo, useRef, useState } from 'react'
import { Search, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import {
  listProductCategories,
  listProductTags,
  updateProduct,
  type ProductCategoryPublic,
  type ProductTagPublic,
} from '../api/products'
import type { ProductListItem } from '../types'

interface Props {
  product: ProductListItem
  onSave: () => void
  onCancel: () => void
}

export function ProductEditDialog({ product, onSave, onCancel }: Props) {
  const { t } = useTranslation()
  const [name, setName] = useState(product.name)
  const [manufacturer, setManufacturer] = useState(product.manufacturer)
  const [model, setModel] = useState(product.model)
  const [categoryId, setCategoryId] = useState<number | null>(product.category_id ?? null)
  const [selectedTagIds, setSelectedTagIds] = useState<number[]>(
    () => product.tags?.map(tg => tg.id) ?? [],
  )
  const [categories, setCategories] = useState<ProductCategoryPublic[]>([])
  const [tags, setTags] = useState<ProductTagPublic[]>([])
  const [taxonomyLoading, setTaxonomyLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [tagSearch, setTagSearch] = useState('')
  const nameRef = useRef<HTMLInputElement>(null)
  const tagSearchRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    setName(product.name)
    setManufacturer(product.manufacturer)
    setModel(product.model)
    setCategoryId(product.category_id ?? null)
    setSelectedTagIds(product.tags?.map(tg => tg.id) ?? [])
  }, [product.id])

  useEffect(() => {
    let cancelled = false
    setTaxonomyLoading(true)
    Promise.all([listProductCategories(), listProductTags()])
      .then(([cats, tgs]) => {
        if (!cancelled) {
          setCategories(cats)
          setTags(tgs)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setCategories([])
          setTags([])
        }
      })
      .finally(() => {
        if (!cancelled) setTaxonomyLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    nameRef.current?.focus()
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel()
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [onCancel])

  const toggleTag = (id: number) => {
    setSelectedTagIds(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id],
    )
  }

  const filteredTags = useMemo(() => {
    if (!tagSearch.trim()) return tags
    const q = tagSearch.toLowerCase()
    return tags.filter(tg => {
      const label = t(`tag.${tg.slug}`, { ns: 'taxonomy', defaultValue: tg.slug })
      return label.toLowerCase().includes(q) || tg.slug.toLowerCase().includes(q)
    })
  }, [tags, tagSearch, t])

  const selectedCount = selectedTagIds.length

  const handleSave = async () => {
    setSaving(true)
    try {
      await updateProduct(product.manufacturer_slug, product.slug, {
        name,
        manufacturer,
        model,
        category_id: categoryId,
        tag_ids: selectedTagIds,
      })
      onSave()
    } catch { /* ignore */ }
    finally { setSaving(false) }
  }

  return (
    <div className="confirm-overlay" onClick={onCancel}>
      <div className="confirm-dialog product-edit-dialog" onClick={e => e.stopPropagation()}>
        <button className="confirm-close" onClick={onCancel} aria-label={t('products.edit.close')}>
          <X size={16} />
        </button>

        <h3 className="confirm-title">{t('products.edit.title')}</h3>

        <div className="product-edit-form">
          <label className="product-edit-label">
            <span>{t('products.edit.name')}</span>
            <input
              ref={nameRef}
              type="text"
              value={name}
              onChange={e => setName(e.target.value)}
              className="product-edit-input"
            />
          </label>

          <div className="product-edit-row">
            <label className="product-edit-label">
              <span>{t('products.edit.manufacturer')}</span>
              <input
                type="text"
                value={manufacturer}
                onChange={e => setManufacturer(e.target.value)}
                className="product-edit-input"
              />
            </label>
            <label className="product-edit-label">
              <span>{t('products.edit.model')}</span>
              <input
                type="text"
                value={model}
                onChange={e => setModel(e.target.value)}
                className="product-edit-input"
              />
            </label>
          </div>

          <label className="product-edit-label">
            <span>{t('products.edit.category')}</span>
            <div className="product-edit-categories">
              <button
                type="button"
                className={`product-edit-cat-chip${categoryId === null ? ' product-edit-cat-chip--active' : ''}`}
                onClick={() => setCategoryId(null)}
                disabled={taxonomyLoading}
              >
                {t('products.edit.categoryNone')}
              </button>
              {categories.map(c => (
                <button
                  key={c.id}
                  type="button"
                  className={`product-edit-cat-chip${categoryId === c.id ? ' product-edit-cat-chip--active' : ''}`}
                  onClick={() => setCategoryId(c.id)}
                  disabled={taxonomyLoading}
                >
                  {c.icon && <span className="product-edit-cat-icon">{c.icon}</span>}
                  {t(`category.${c.slug}`, { ns: 'taxonomy', defaultValue: c.slug })}
                </button>
              ))}
            </div>
          </label>

          <div className="product-edit-label product-edit-tags-block">
            <span>
              {t('products.edit.tags')}
              {selectedCount > 0 && (
                <span className="product-edit-tags-count">{selectedCount}</span>
              )}
            </span>
            {taxonomyLoading ? (
              <div className="product-edit-tags-skeleton">
                {[...Array(6)].map((_, i) => <div key={i} className="product-edit-tag-skeleton" />)}
              </div>
            ) : (
              <>
                <div className="product-edit-tag-search">
                  <Search size={14} />
                  <input
                    ref={tagSearchRef}
                    type="text"
                    value={tagSearch}
                    onChange={e => setTagSearch(e.target.value)}
                    placeholder={t('products.edit.tagsSearch')}
                    className="product-edit-tag-search-input"
                  />
                  {tagSearch && (
                    <button
                      className="product-edit-tag-search-clear"
                      onClick={() => { setTagSearch(''); tagSearchRef.current?.focus() }}
                    >
                      <X size={12} />
                    </button>
                  )}
                </div>
                <div className="product-edit-tags">
                  {filteredTags.length === 0 ? (
                    <span className="product-edit-tags-hint">{t('products.edit.tagsEmpty')}</span>
                  ) : (
                    filteredTags.map(tg => (
                      <label key={tg.id} className="product-edit-tag">
                        <input
                          type="checkbox"
                          checked={selectedTagIds.includes(tg.id)}
                          onChange={() => toggleTag(tg.id)}
                        />
                        <span className="product-edit-tag-check">
                          {selectedTagIds.includes(tg.id) && (
                            <svg width="10" height="8" viewBox="0 0 10 8" fill="none">
                              <path d="M1 3.5L3.5 6L9 1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                            </svg>
                          )}
                        </span>
                        <span>{t(`tag.${tg.slug}`, { ns: 'taxonomy', defaultValue: tg.slug })}</span>
                      </label>
                    ))
                  )}
                </div>
              </>
            )}
          </div>
        </div>

        <div className="confirm-actions">
          <button className="confirm-btn confirm-btn--cancel" onClick={onCancel}>
            {t('products.edit.cancel')}
          </button>
          <button
            className="confirm-btn confirm-btn--default"
            onClick={handleSave}
            disabled={saving || !name.trim()}
          >
            {saving ? t('products.edit.saving') : t('products.edit.save')}
          </button>
        </div>
      </div>
    </div>
  )
}
