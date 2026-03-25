import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ChevronDown, Plus, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { listProducts } from '../api/products'
import type { ProductListItem } from '../types'

export interface ProductSelection {
  productName: string
  manufacturer: string
  firmwareVersion: string
  isExisting: boolean
}

interface Props {
  value: ProductSelection
  onChange: (selection: ProductSelection) => void
  disabled?: boolean
  autoFocus?: boolean
}

export function ProductAutocomplete({ value, onChange, disabled, autoFocus }: Props) {
  const { t } = useTranslation()
  const [products, setProducts] = useState<ProductListItem[]>([])
  const [query, setQuery] = useState(value.isExisting ? value.productName : '')
  const [open, setOpen] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const wrapperRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    let cancelled = false
    listProducts()
      .then(list => { if (!cancelled) { setProducts(list); setLoaded(true) } })
      .catch(() => { if (!cancelled) setLoaded(true) })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    if (value.isExisting) {
      const display = value.firmwareVersion
        ? `${value.productName} ${value.firmwareVersion}`
        : value.productName
      setQuery(display)
    }
  }, [value.isExisting, value.productName, value.firmwareVersion])

  const filtered = useMemo(() => {
    if (!query.trim()) return products
    const q = query.toLowerCase()
    return products.filter(
      p => p.display_name.toLowerCase().includes(q)
        || p.name.toLowerCase().includes(q)
        || p.manufacturer.toLowerCase().includes(q),
    )
  }, [products, query])

  const exactMatch = useMemo(() => {
    const q = query.trim().toLowerCase()
    return q ? products.some(p => p.display_name.toLowerCase() === q) : false
  }, [products, query])

  const handleSelect = useCallback((product: ProductListItem) => {
    onChange({
      productName: product.name,
      manufacturer: product.manufacturer,
      firmwareVersion: product.version || '1.0',
      isExisting: true,
    })
    setQuery(product.display_name || product.name)
    setOpen(false)
  }, [onChange])

  const handleCreateNew = useCallback(() => {
    const name = query.trim()
    if (!name) return
    onChange({
      productName: name,
      manufacturer: '',
      firmwareVersion: '1.0',
      isExisting: false,
    })
    setOpen(false)
  }, [query, onChange])

  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value
    setQuery(val)
    setOpen(true)
    if (value.isExisting) {
      onChange({
        productName: val,
        manufacturer: '',
        firmwareVersion: '1.0',
        isExisting: false,
      })
    }
  }, [value.isExisting, onChange])

  const handleClear = useCallback(() => {
    setQuery('')
    onChange({
      productName: '',
      manufacturer: '',
      firmwareVersion: '1.0',
      isExisting: false,
    })
    inputRef.current?.focus()
  }, [onChange])

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      setOpen(false)
    } else if (e.key === 'ArrowDown' && !open) {
      setOpen(true)
    }
  }, [open])

  return (
    <div className="product-autocomplete" ref={wrapperRef}>
      <div className="product-autocomplete-input-wrap">
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={handleInputChange}
          onFocus={() => loaded && setOpen(true)}
          onKeyDown={handleKeyDown}
          placeholder={t('upload.productPlaceholder')}
          disabled={disabled}
          autoFocus={autoFocus}
          className={value.isExisting ? 'product-autocomplete-selected' : ''}
        />
        {query && !disabled && (
          <button
            type="button"
            className="product-autocomplete-clear"
            onClick={handleClear}
            tabIndex={-1}
          >
            <X size={14} />
          </button>
        )}
        <button
          type="button"
          className="product-autocomplete-toggle"
          onClick={() => loaded && setOpen(!open)}
          disabled={disabled}
          tabIndex={-1}
        >
          <ChevronDown size={14} />
        </button>
      </div>

      {open && (
        <div className="product-autocomplete-dropdown">
          {filtered.length === 0 && !query.trim() && (
            <div className="product-autocomplete-empty">
              {t('productAutocomplete.noProducts')}
            </div>
          )}

          {filtered.map(p => {
            const key = p.firmware_version_id
              ? `${p.id}-${p.firmware_version_id}`
              : String(p.id)
            return (
              <button
                key={key}
                type="button"
                className="product-autocomplete-option"
                onClick={() => handleSelect(p)}
              >
                <span className="product-autocomplete-option-name">
                  {p.display_name || p.name}
                </span>
                <span className="product-autocomplete-option-meta">
                  {p.manufacturer && <span>{p.manufacturer}</span>}
                  <span>{p.total_documents} docs</span>
                </span>
              </button>
            )
          })}

          {query.trim() && !exactMatch && (
            <>
              {filtered.length > 0 && <div className="product-autocomplete-divider" />}
              <button
                type="button"
                className="product-autocomplete-option product-autocomplete-create"
                onClick={handleCreateNew}
              >
                <Plus size={14} />
                <span>{t('productAutocomplete.createNew', { name: query.trim() })}</span>
              </button>
            </>
          )}
        </div>
      )}
    </div>
  )
}
