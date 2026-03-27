import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Search, ChevronDown, X, Globe, Box } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { listProducts } from '../api/products'
import type { ProductListItem } from '../types'

interface ProductSelection {
  productId: number | null
  productName: string | null
  manufacturer: string | null
  versionFilter: string | null
}

interface Props {
  value: ProductSelection
  onChange: (selection: ProductSelection) => void
  onClose?: () => void
}

interface GroupedProduct {
  manufacturer: string
  products: ProductListItem[]
}

export function ProductPicker({ value, onChange, onClose }: Props) {
  const { t } = useTranslation()
  const [products, setProducts] = useState<ProductListItem[]>([])
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const searchRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    listProducts()
      .then(list => { if (!cancelled) setProducts(list) })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    searchRef.current?.focus()
  }, [])

  useEffect(() => {
    if (!onClose) return
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose()
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  const filtered = useMemo(() => {
    if (!search.trim()) return products
    const q = search.toLowerCase()
    return products.filter(
      p => p.display_name.toLowerCase().includes(q)
        || p.name.toLowerCase().includes(q)
        || p.manufacturer.toLowerCase().includes(q)
        || p.version.toLowerCase().includes(q),
    )
  }, [products, search])

  const grouped = useMemo<GroupedProduct[]>(() => {
    const map = new Map<string, ProductListItem[]>()
    for (const p of filtered) {
      const key = p.manufacturer || 'Other'
      const list = map.get(key) ?? []
      list.push(p)
      map.set(key, list)
    }
    return Array.from(map.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([manufacturer, prods]) => ({ manufacturer, products: prods }))
  }, [filtered])

  const handleSelect = useCallback(
    (product: ProductListItem | null) => {
      if (!product) {
        onChange({ productId: null, productName: null, manufacturer: null, versionFilter: null })
      } else {
        onChange({
          productId: product.id,
          productName: product.name,
          manufacturer: product.manufacturer,
          versionFilter: product.version || null,
        })
      }
      onClose?.()
    },
    [onChange, onClose],
  )

  return (
    <div className="product-picker-overlay" onClick={onClose}>
      <div className="product-picker" onClick={e => e.stopPropagation()}>
        <div className="product-picker-header">
          <h3>{t('productPicker.title')}</h3>
          {onClose && (
            <button className="product-picker-close" onClick={onClose}>
              <X size={16} />
            </button>
          )}
        </div>

        <div className="product-picker-search">
          <Search size={16} />
          <input
            ref={searchRef}
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder={t('productPicker.search')}
          />
        </div>

        <div className="product-picker-list">
          <button
            className={`product-picker-item product-picker-item--all${!value.productName ? ' active' : ''}`}
            onClick={() => handleSelect(null)}
          >
            <Globe size={16} />
            <span>{t('productPicker.allProducts')}</span>
          </button>

          {loading && <div className="product-picker-loading">...</div>}

          {!loading && grouped.length === 0 && search && (
            <div className="product-picker-empty">{t('productPicker.noProducts')}</div>
          )}

          {grouped.map(group => (
            <div key={group.manufacturer} className="product-picker-group">
              <div className="product-picker-group-label">{group.manufacturer}</div>
              {group.products.map(p => {
                const isActive = value.productName === p.name
                  && (value.versionFilter ?? '') === (p.version ?? '')
                const itemKey = p.firmware_version_id
                  ? `${p.id}-${p.firmware_version_id}`
                  : String(p.id)
                return (
                  <button
                    key={itemKey}
                    className={`product-picker-item${isActive ? ' active' : ''}`}
                    onClick={() => handleSelect(p)}
                  >
                    <span className="product-picker-item-name">{p.display_name || p.name}</span>
                    <span className="product-picker-item-meta">
                      {p.total_documents} docs · {p.total_chunks} chunks
                    </span>
                  </button>
                )
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

interface BadgeProps {
  productFilter: string | null
  versionFilter: string | null
  autoDetected?: boolean
  locked?: boolean
  onEdit: () => void
  onClear: () => void
  onLock?: () => void
  onUnlock?: () => void
}

export function ProductBadge({ productFilter, versionFilter, autoDetected, locked, onEdit, onClear, onLock, onUnlock }: BadgeProps) {
  const { t } = useTranslation()

  if (!productFilter) {
    return (
      <div className="product-badge product-badge--all" onClick={onEdit} role="button">
        <Globe size={13} className="product-badge-icon" />
        <span className="product-badge-name">{t('productBadge.allProducts')}</span>
        <ChevronDown size={14} className="product-badge-chevron" />
      </div>
    )
  }

  return (
    <div className={`product-badge${locked ? ' product-badge--locked' : ''}`}>
      {autoDetected && !locked && (
        <span
          className="product-badge-auto"
          onClick={e => { e.stopPropagation(); onLock?.() }}
        >
          {t('productBadge.autoDetected')}
        </span>
      )}
      {locked && (
        <span
          className="product-badge-locked-label"
          onClick={e => { e.stopPropagation(); onUnlock?.() }}
        >
          {t('productBadge.locked')}
        </span>
      )}
      <span className="product-badge-label" onClick={onEdit}>
        <Box size={13} className="product-badge-icon" />
        <span className="product-badge-name">{productFilter}</span>
        {versionFilter && <span className="product-badge-version">{versionFilter}</span>}
        <ChevronDown size={14} className="product-badge-chevron" />
      </span>
      <button
        className="product-badge-clear"
        onClick={onClear}
      >
        <X size={12} />
      </button>
    </div>
  )
}
