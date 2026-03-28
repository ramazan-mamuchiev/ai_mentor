import { useEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'
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
    () => product.tags?.map(t => t.id) ?? [],
  )
  const [categories, setCategories] = useState<ProductCategoryPublic[]>([])
  const [tags, setTags] = useState<ProductTagPublic[]>([])
  const [taxonomyLoading, setTaxonomyLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const nameRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    setName(product.name)
    setManufacturer(product.manufacturer)
    setModel(product.model)
    setCategoryId(product.category_id ?? null)
    setSelectedTagIds(product.tags?.map(t => t.id) ?? [])
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
        <button className="confirm-close" onClick={onCancel} aria-label="Close">
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
          <label className="product-edit-label">
            <span>{t('products.edit.category')}</span>
            <select
              value={categoryId === null ? '' : String(categoryId)}
              onChange={e => {
                const v = e.target.value
                setCategoryId(v === '' ? null : Number(v))
              }}
              className="product-edit-input"
              disabled={taxonomyLoading}
            >
              <option value="">—</option>
              {categories.map(c => (
                <option key={c.id} value={c.id}>
                  {c.slug}
                </option>
              ))}
            </select>
          </label>
          <div className="product-edit-label product-edit-tags-block">
            <span>{t('products.edit.tags')}</span>
            {taxonomyLoading ? (
              <span className="product-edit-tags-hint">…</span>
            ) : (
              <div className="product-edit-tags">
                {tags.map(tag => (
                  <label key={tag.id} className="product-edit-tag">
                    <input
                      type="checkbox"
                      checked={selectedTagIds.includes(tag.id)}
                      onChange={() => toggleTag(tag.id)}
                    />
                    <span>{tag.slug}</span>
                  </label>
                ))}
              </div>
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
            {saving ? '...' : t('products.edit.save')}
          </button>
        </div>
      </div>
    </div>
  )
}
