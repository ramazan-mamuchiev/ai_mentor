import { useState, useEffect, useRef } from 'react'
import { suggestProducts, type ProductSuggestion } from '../api/products'
import { useDebounce } from '../hooks/useDebounce'

export interface ProductSelection {
  productName: string
  manufacturer: string
  firmwareVersion: string
  isExisting: boolean
  productId?: number
}

export interface ProductAutocompleteProps {
  value?: string | ProductSelection
  onSelect?: (product: ProductSuggestion) => void
  onChange?: (sel: ProductSelection | ((prev: ProductSelection) => ProductSelection)) => void
  placeholder?: string
  autoFocus?: boolean
}

export function ProductAutocomplete({ value = '', onSelect, onChange, placeholder, autoFocus }: ProductAutocompleteProps) {
  const initialQuery = typeof value === 'string' ? value : value.productName
  const [query, setQuery] = useState(initialQuery)
  const [suggestions, setSuggestions] = useState<ProductSuggestion[]>([])
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const debouncedQuery = useDebounce(query, 300)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!debouncedQuery || debouncedQuery.length < 2) {
      setSuggestions([])
      return
    }
    setLoading(true)
    suggestProducts(debouncedQuery, 15)
      .then(setSuggestions)
      .catch(() => setSuggestions([]))
      .finally(() => setLoading(false))
  }, [debouncedQuery])

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  return (
    <div ref={containerRef} style={{ position: 'relative' }}>
      <input
        value={query}
        onChange={e => {
          setQuery(e.target.value)
          setOpen(true)
          if (onChange) {
            onChange(prev => ({ ...prev, productName: e.target.value, isExisting: false, productId: undefined }))
          }
        }}
        onFocus={() => { if (suggestions.length > 0) setOpen(true) }}
        placeholder={placeholder}
        autoFocus={autoFocus}
      />
      {open && suggestions.length > 0 && (
        <div style={{
          position: 'absolute', top: '100%', left: 0, right: 0,
          background: 'var(--bg-primary)', border: '1px solid var(--border)',
          borderRadius: 6, maxHeight: 240, overflowY: 'auto', zIndex: 100,
          boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
        }}>
          {suggestions.map(product => (
            <div
              key={product.id}
              onClick={() => {
                if (onSelect) onSelect(product)
                if (onChange) {
                  onChange({
                    productName: product.name,
                    manufacturer: product.manufacturer || '',
                    firmwareVersion: '',
                    isExisting: true,
                    productId: product.id,
                  })
                }
                setQuery(product.name)
                setOpen(false)
              }}
              style={{
                padding: '8px 12px', cursor: 'pointer', fontSize: 13,
                borderBottom: '1px solid var(--border)',
              }}
              onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-secondary)')}
              onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
            >
              <strong>{product.name}</strong>
              {product.manufacturer && <span style={{ opacity: 0.6 }}> — {product.manufacturer}</span>}
            </div>
          ))}
        </div>
      )}
      {open && loading && (
        <div style={{
          position: 'absolute', top: '100%', left: 0, right: 0,
          padding: '8px 12px', fontSize: 13, color: 'var(--text-tertiary)',
          background: 'var(--bg-primary)', border: '1px solid var(--border)',
          borderRadius: 6,
        }}>
          Searching...
        </div>
      )}
    </div>
  )
}
