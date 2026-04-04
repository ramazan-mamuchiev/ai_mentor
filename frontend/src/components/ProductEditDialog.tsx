import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { ChevronDown, Check, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { updateProduct } from '../api/products'
import type { ProductListItem } from '../types'

const CATEGORIES = [
  'video_surveillance',
  'access_control',
  'intercom',
  'alarm_intrusion',
  'perimeter_security',
  'building_automation',
  'software',
  'platform',
  'internal_docs',
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
  const [version, setVersion] = useState(product.version ?? '')
  const [category, setCategory] = useState<string>(product.category ?? '')
  const [saving, setSaving] = useState(false)
  const [catOpen, setCatOpen] = useState(false)
  const [catPos, setCatPos] = useState<{ top: number; left: number; width: number; maxHeight: number }>({ top: 0, left: 0, width: 0, maxHeight: 240 })
  const nameRef = useRef<HTMLInputElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const dropRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setName(product.name)
    setManufacturer(product.manufacturer)
    setVersion(product.version ?? '')
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
      const target = e.target as Node
      if (dropRef.current && !dropRef.current.contains(target) &&
          triggerRef.current && !triggerRef.current.contains(target)) {
        setCatOpen(false)
      }
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
        category: category || undefined,
        version: version || undefined,
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
              <span>{t('products.edit.version')}</span>
              <input
                type="text"
                value={version}
                onChange={e => setVersion(e.target.value)}
                className="product-edit-input"
              />
            </label>
          </div>

          <div className="product-edit-label">
            <span>{t('products.edit.category')}</span>
            <div className="product-edit-cat-select">
              <button
                ref={triggerRef}
                type="button"
                className={`product-edit-cat-trigger${catOpen ? ' product-edit-cat-trigger--open' : ''}`}
                onClick={() => {
                  if (!catOpen && triggerRef.current) {
                    const rect = triggerRef.current.getBoundingClientRect()
                    const dropdownHeight = 240
                    const gap = 4
                    const spaceBelow = window.innerHeight - rect.bottom - gap
                    const spaceAbove = rect.top - gap
                    const openBelow = spaceBelow >= dropdownHeight || spaceBelow >= spaceAbove
                    const maxH = openBelow
                      ? Math.min(dropdownHeight, spaceBelow)
                      : Math.min(dropdownHeight, spaceAbove)
                    const top = openBelow ? rect.bottom + gap : rect.top - gap - maxH
                    setCatPos({ top, left: rect.left, width: rect.width, maxHeight: maxH })
                  }
                  setCatOpen(v => !v)
                }}
              >
                <span className={!category ? 'product-edit-cat-trigger-placeholder' : ''}>
                  {selectedCatLabel}
                </span>
                <ChevronDown size={15} className="product-edit-cat-chevron" />
              </button>
              {catOpen && createPortal(
                <div
                  ref={dropRef}
                  className="product-edit-cat-dropdown"
                  style={{ position: 'fixed', top: catPos.top, left: catPos.left, width: catPos.width, maxHeight: catPos.maxHeight }}
                >
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
                </div>,
                document.body
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
