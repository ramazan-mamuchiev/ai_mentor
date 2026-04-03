import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { User, X } from 'lucide-react'
import { searchTenants, getTenant, type TenantSearchResult } from '../api/admin'

interface Props {
  value: TenantSearchResult | null
  onChange: (tenant: TenantSearchResult | null) => void
  initialTenantId?: string
}

export function TenantFilterCombo({ value, onChange, initialTenantId }: Props) {
  const { t } = useTranslation()
  const [searchParams, setSearchParams] = useSearchParams()
  const [query, setQuery] = useState('')
  const [options, setOptions] = useState<TenantSearchResult[]>([])
  const [open, setOpen] = useState(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const wrapRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!initialTenantId || value) return
    getTenant(initialTenantId)
      .then(tenant => {
        onChange({ id: tenant.id, name: tenant.name || tenant.email.split('@')[0], email: tenant.email })
        if (searchParams.has('tenant_id')) {
          searchParams.delete('tenant_id')
          setSearchParams(searchParams, { replace: true })
        }
      })
      .catch(() => {})
  }, [initialTenantId]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (!query || query.length < 1) { setOptions([]); return }
    debounceRef.current = setTimeout(async () => {
      try {
        const results = await searchTenants(query)
        setOptions(results)
        setOpen(true)
      } catch { setOptions([]) }
    }, 300)
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current) }
  }, [query])

  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  return (
    <div className="logs-tenant-combo" ref={wrapRef}>
      {value ? (
        <div className="logs-tenant-chip">
          <User size={12} />
          <span className="logs-tenant-chip__name">{value.name}</span>
          <button
            className="logs-tenant-chip__clear"
            onClick={() => { onChange(null); setQuery('') }}
            aria-label={t('admin.logs.clear')}
          >
            <X size={12} />
          </button>
        </div>
      ) : (
        <>
          <User size={13} className="logs-tenant-combo__icon" />
          <input
            className="logs-tenant-input"
            placeholder={t('admin.logs.tenantPlaceholder')}
            value={query}
            onChange={e => setQuery(e.target.value)}
            onFocus={() => { if (options.length) setOpen(true) }}
          />
          {query && (
            <button className="logs-tenant-combo__clear" onClick={() => { setQuery(''); setOptions([]); setOpen(false) }}>
              <X size={12} />
            </button>
          )}
        </>
      )}
      {open && options.length > 0 && (
        <div className="logs-tenant-dropdown">
          {options.map(opt => (
            <button
              key={opt.id}
              className="logs-tenant-dropdown__item"
              onClick={() => {
                onChange(opt)
                setQuery('')
                setOpen(false)
              }}
            >
              <span className="logs-tenant-dropdown__name">{opt.name}</span>
              <span className="logs-tenant-dropdown__email">{opt.email}</span>
            </button>
          ))}
        </div>
      )}
      {open && query && options.length === 0 && (
        <div className="logs-tenant-dropdown">
          <div className="logs-tenant-dropdown__empty">{t('admin.logs.noTenantsFound')}</div>
        </div>
      )}
    </div>
  )
}
