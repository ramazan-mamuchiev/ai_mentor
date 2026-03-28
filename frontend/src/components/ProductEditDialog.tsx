import { useEffect, useMemo, useRef, useState } from 'react'
import { ChevronDown, Check, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { updateProduct } from '../api/products'
import type { ProductListItem } from '../types'

const CATEGORIES = [
  'video_surveillance',
  'access_control',
  'intercom',
  'alarm_intrusion',
  'building_automation',
  'software',
  'protocols',
] as const

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
  const [category, setCategory] = useState<string>(product.category ?? '')
  const [saving, setSaving] = useState(false)
  const [catOpen, setCatOpen] = useState(false)
  const nameRef = useRef<HTMLInputElement>(null)
  const catRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setName(product.name)
    setManufacturer(product.manufacturer)
    setModel(product.model)
    setCategory(product.category ?? '')
  }, [product.id])

  useEffect(() => {
    nameRef.current?.focus()
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (catOpen) { setCatOpen(false); e.stopPropagation(); return }
        onCancel()
      }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [onCancel, catOpen])

  useEffect(() => {
    if (!catOpen) return
    const handleClickOutside = (e: MouseEvent) => {
      if (catRef.current && !catRef.current.contains(e.target as Node)) setCatOpen(false)
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [catOpen])

  const selectedCatLabel = useMemo(() => {
    if (!category) return t('products.edit.categoryNone')
    return t(`category.${category}`)
  }, [category, t])

  const handleSave = async () => {
    setSaving(true)
    try {
      await updateProduct(product.id, {
        name,
        manufacturer,
        model,
        category: category || undefined,
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

          <div className="product-edit-label">
            <span>{t('products.edit.category')}</span>
            <div className="product-edit-cat-select" ref={catRef}>
              <button
                type="button"
                className={`product-edit-cat-trigger${catOpen ? ' product-edit-cat-trigger--open' : ''}`}
                onClick={() => setCatOpen(v => !v)}
              >
                <span className={!category ? 'product-edit-cat-trigger-placeholder' : ''}>
                  {selectedCatLabel}
                </span>
                <ChevronDown size={15} className="product-edit-cat-chevron" />
              </button>
              {catOpen && (
                <div className="product-edit-cat-dropdown">
                  <button
                    type="button"
                    className={`product-edit-cat-option${!category ? ' product-edit-cat-option--active' : ''}`}
                    onClick={() => { setCategory(''); setCatOpen(false) }}
                  >
                    <span className="product-edit-cat-radio" />
                    <span className="product-edit-cat-option-label product-edit-cat-option-none">{t('products.edit.categoryNone')}</span>
                    {!category && <Check size={14} className="product-edit-cat-check" />}
                  </button>
                  {CATEGORIES.map(slug => (
                    <button
                      key={slug}
                      type="button"
                      className={`product-edit-cat-option${category === slug ? ' product-edit-cat-option--active' : ''}`}
                      onClick={() => { setCategory(slug); setCatOpen(false) }}
                    >
                      <span className="product-edit-cat-radio" />
                      <span className="product-edit-cat-option-label">{t(`category.${slug}`)}</span>
                      {category === slug && <Check size={14} className="product-edit-cat-check" />}
                    </button>
                  ))}
                </div>
              )}
            </div>
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
