import { useState, useEffect, useRef } from 'react'
import { Search } from 'lucide-react'
import { suggestProducts, type ProductSuggestion } from '../api/products'
import { useDebounce } from '../hooks/useDebounce'

interface ProductAutocompleteProps {
  value?: string
  onSelect: (product: ProductSuggestion) => void
  placeholder?: string
}

export function ProductAutocomplete({ value = '', onSelect, placeholder = 'Search products...' }: ProductAutocompleteProps) {
  const [query, setQuery] = useState(value)
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
      <div style={{ position: 'relative' }}>
        <Search size={14} style={{ position: 'absolute', left: 8, top: '50%', transform: 'translateY(-50%)', opacity: 0.5 }} />
        <input
          value={query}
          onChange={e => { setQuery(e.target.value); setOpen(true) }}
          onFocus={() => { if (suggestions.length > 0) setOpen(true) }}
          placeholder={placeholder}
          className="admin-input"
          style={{ paddingLeft: 28, width: '100%' }}
        />
      </div>
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
              onClick={() => { onSelect(product); setQuery(product.name); setOpen(false) }}
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
