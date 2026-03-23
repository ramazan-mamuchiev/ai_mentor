import { useEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { updateProduct } from '../api/products'
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
  const [category, setCategory] = useState(product.category)
  const [saving, setSaving] = useState(false)
  const nameRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    nameRef.current?.focus()
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel()
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [onCancel])

  const handleSave = async () => {
    setSaving(true)
    try {
      await updateProduct(product.id, { name, manufacturer, model, category })
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
            <input
              type="text"
              value={category}
              onChange={e => setCategory(e.target.value)}
              className="product-edit-input"
            />
          </label>
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
