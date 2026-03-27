import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  RefreshCw, X, Search, Radio, ChevronDown, ChevronRight,
  Copy, Check, Clock, AlertTriangle, ScrollText,
} from 'lucide-react'
import { getLogs, searchTenants, type LogEntry, type TenantSearchResult } from '../../api/admin'
import { User } from 'lucide-react'

const SERVICES = ['api', 'worker', 'beat', 'web', 'postgres', 'redis'] as const

const LEVELS = [
  { value: '', label: 'All', color: '' },
  { value: 'info', label: 'INFO', color: 'var(--log-info)' },
  { value: 'warning', label: 'WARN', color: 'var(--log-warn)' },
  { value: 'error', label: 'ERROR', color: 'var(--log-error)' },
  { value: 'debug', label: 'DEBUG', color: 'var(--log-debug)' },
] as const

const TIME_RANGES = [
  { value: '15m', label: '15m' },
  { value: '1h', label: '1h' },
  { value: '3h', label: '3h' },
  { value: '6h', label: '6h' },
  { value: '24h', label: '24h' },
  { value: '7d', label: '7d' },
] as const

function timeRangeToISO(range: string): { start: string; end: string } {
  const now = Date.now()
  const units: Record<string, number> = { m: 60_000, h: 3_600_000, d: 86_400_000 }
  const match = range.match(/^(\d+)([mhd])$/)
  if (!match) return { start: '', end: '' }
  const ms = parseInt(match[1]) * units[match[2]]
  return {
    start: new Date(now - ms).toISOString(),
    end: new Date(now).toISOString(),
  }
}

function formatTimestamp(ts: string): string {
  try {
    const ns = BigInt(ts)
    const ms = Number(ns / BigInt(1_000_000))
    const d = new Date(ms)
    const dd = String(d.getDate()).padStart(2, '0')
    const mm = String(d.getMonth() + 1).padStart(2, '0')
    const hh = String(d.getHours()).padStart(2, '0')
    const mi = String(d.getMinutes()).padStart(2, '0')
    const ss = String(d.getSeconds()).padStart(2, '0')
    return `${dd}.${mm} ${hh}:${mi}:${ss}`
  } catch {
    return ts
  }
}

function tryParseJSON(msg: string): Record<string, unknown> | null {
  if (!msg.startsWith('{')) return null
  try { return JSON.parse(msg) } catch { return null }
}

function highlightSearch(text: string, query: string): React.ReactNode {
  if (!query || query.length < 2) return text
  const idx = text.toLowerCase().indexOf(query.toLowerCase())
  if (idx === -1) return text
  return (
    <>
      {text.slice(0, idx)}
      <mark className="log-highlight">{text.slice(idx, idx + query.length)}</mark>
      {text.slice(idx + query.length)}
    </>
  )
}

function LogRow({ entry, search, defaultExpanded }: {
  entry: LogEntry; search: string; defaultExpanded: boolean
}) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(defaultExpanded)
  const [copied, setCopied] = useState(false)
  const parsed = useMemo(() => tryParseJSON(entry.message), [entry.message])
  const lvl = entry.level?.toLowerCase() || 'info'

  const summary = useMemo(() => {
    if (!parsed) return entry.message
    const event = parsed.event || parsed.msg || parsed.message || ''
    const method = parsed.method || ''
    const path = parsed.path || ''
    const status = parsed.status_code || parsed.status || ''
    const duration = parsed.duration_ms ? `${parsed.duration_ms}ms` : ''
    const parts = [event, method && path ? `${method} ${path}` : '', status, duration].filter(Boolean)
    return parts.join(' · ') || entry.message
  }, [parsed, entry.message])

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation()
    navigator.clipboard.writeText(entry.message)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  const extraKeys = parsed
    ? Object.entries(parsed).filter(([k]) => !['event', 'msg', 'message', 'level', 'timestamp', 'logger'].includes(k))
    : Object.entries(entry.extra || {})

  return (
    <div className={`log-row ${expanded ? 'log-row--expanded' : ''}`} onClick={() => setExpanded(v => !v)}>
      <div className="log-row__header">
        <span className="log-row__expand">
          {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        </span>
        <span className="log-row__ts">{formatTimestamp(entry.timestamp)}</span>
        <span className={`log-row__level log-row__level--${lvl}`}>{lvl === 'warning' ? 'WARN' : lvl.toUpperCase()}</span>
        <span className="log-row__summary">{highlightSearch(String(summary), search)}</span>
        <button className="log-row__copy" onClick={handleCopy} title={t('admin.logs.copyRaw')}>
          {copied ? <Check size={12} /> : <Copy size={12} />}
        </button>
      </div>
      {expanded && extraKeys.length > 0 && (
        <div className="log-row__details">
          {extraKeys.map(([k, v]) => (
            <div className="log-row__field" key={k}>
              <span className="log-row__key">{k}</span>
              <span className="log-row__value">{highlightSearch(String(v), search)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function LogsPage() {
  const { t } = useTranslation()
  const [entries, setEntries] = useState<LogEntry[]>([])
  const [service, setService] = useState('api')
  const [level, setLevel] = useState('')
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [timeRange, setTimeRange] = useState('1h')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [autoRefresh, setAutoRefresh] = useState(false)
  const [tenantFilter, setTenantFilter] = useState<TenantSearchResult | null>(null)
  const [tenantQuery, setTenantQuery] = useState('')
  const [tenantOptions, setTenantOptions] = useState<TenantSearchResult[]>([])
  const [tenantDropdownOpen, setTenantDropdownOpen] = useState(false)
  const tenantDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const tenantWrapRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => setDebouncedSearch(search), 400)
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current) }
  }, [search])

  useEffect(() => {
    if (tenantDebounceRef.current) clearTimeout(tenantDebounceRef.current)
    if (!tenantQuery || tenantQuery.length < 1) { setTenantOptions([]); return }
    tenantDebounceRef.current = setTimeout(async () => {
      try {
        const results = await searchTenants(tenantQuery)
        setTenantOptions(results)
        setTenantDropdownOpen(true)
      } catch { setTenantOptions([]) }
    }, 300)
    return () => { if (tenantDebounceRef.current) clearTimeout(tenantDebounceRef.current) }
  }, [tenantQuery])

  useEffect(() => {
    if (!tenantDropdownOpen) return
    const handler = (e: MouseEvent) => {
      if (tenantWrapRef.current && !tenantWrapRef.current.contains(e.target as Node)) {
        setTenantDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [tenantDropdownOpen])

  const load = useCallback(async () => {
    setError('')
    try {
      const { start, end } = timeRangeToISO(timeRange)
      const res = await getLogs({
        service,
        level: level || undefined,
        search: debouncedSearch || undefined,
        tenant: tenantFilter?.name || undefined,
        start: start || undefined,
        end: end || undefined,
        limit: 500,
      })
      setEntries(res.entries)
    } catch (err) {
      setError(err instanceof Error ? err.message : t('admin.logs.failedToLoad'))
    }
    setLoading(false)
  }, [service, level, debouncedSearch, tenantFilter, timeRange, t])

  useEffect(() => {
    setLoading(true)
    load()
  }, [load])

  useEffect(() => {
    if (autoRefresh) {
      intervalRef.current = setInterval(load, 3000)
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [autoRefresh, load])

  const levelCounts = useMemo(() => {
    const counts: Record<string, number> = { info: 0, warning: 0, error: 0, debug: 0 }
    for (const e of entries) {
      const l = e.level?.toLowerCase() || 'info'
      if (l in counts) counts[l]++
    }
    return counts
  }, [entries])

  return (
    <div className="logs-page">
      <div className="admin-page-header">
        <h1><ScrollText size={20} /> {t('admin.logs.title')}</h1>
        <p>{t('admin.logs.subtitle')}</p>
      </div>

      {/* Toolbar */}
      <div className="logs-toolbar">
        <div className="logs-toolbar__row">
          {/* Service select */}
          <select className="logs-select" value={service} onChange={e => setService(e.target.value)}>
            {SERVICES.map(s => <option key={s} value={s}>{s}</option>)}
          </select>

          {/* Time range chips */}
          <div className="logs-chips" role="group" aria-label={t('admin.logs.timeRange')}>
            <Clock size={13} className="logs-chips__icon" />
            {TIME_RANGES.map(r => (
              <button
                key={r.value}
                className={`logs-chip${timeRange === r.value ? ' logs-chip--active' : ''}`}
                onClick={() => setTimeRange(r.value)}
              >
                {r.label}
              </button>
            ))}
          </div>

          {/* Tenant filter */}
          <div className="logs-tenant-combo" ref={tenantWrapRef}>
            {tenantFilter ? (
              <div className="logs-tenant-chip">
                <User size={12} />
                <span className="logs-tenant-chip__name">{tenantFilter.name}</span>
                <button
                  className="logs-tenant-chip__clear"
                  onClick={() => { setTenantFilter(null); setTenantQuery('') }}
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
                  value={tenantQuery}
                  onChange={e => setTenantQuery(e.target.value)}
                  onFocus={() => { if (tenantOptions.length) setTenantDropdownOpen(true) }}
                />
                {tenantQuery && (
                  <button className="logs-tenant-combo__clear" onClick={() => { setTenantQuery(''); setTenantOptions([]); setTenantDropdownOpen(false) }}>
                    <X size={12} />
                  </button>
                )}
              </>
            )}
            {tenantDropdownOpen && tenantOptions.length > 0 && (
              <div className="logs-tenant-dropdown">
                {tenantOptions.map(opt => (
                  <button
                    key={opt.id}
                    className="logs-tenant-dropdown__item"
                    onClick={() => {
                      setTenantFilter(opt)
                      setTenantQuery('')
                      setTenantDropdownOpen(false)
                    }}
                  >
                    <span className="logs-tenant-dropdown__name">{opt.name}</span>
                    <span className="logs-tenant-dropdown__email">{opt.email}</span>
                  </button>
                ))}
              </div>
            )}
            {tenantDropdownOpen && tenantQuery && tenantOptions.length === 0 && (
              <div className="logs-tenant-dropdown">
                <div className="logs-tenant-dropdown__empty">{t('admin.logs.noTenantsFound')}</div>
              </div>
            )}
          </div>

          {/* Search */}
          <div className="logs-search-wrap">
            <Search size={14} className="logs-search-wrap__icon" />
            <input
              className="logs-search"
              placeholder={t('admin.logs.searchPlaceholder')}
              value={search}
              onChange={e => setSearch(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && load()}
            />
            {search && (
              <button className="logs-search-wrap__clear" onClick={() => setSearch('')} aria-label={t('admin.logs.clear')}>
                <X size={14} />
              </button>
            )}
          </div>

          {/* Refresh & Live tail */}
          <button className="logs-icon-btn" onClick={load} title={t('admin.logs.refresh')}>
            <RefreshCw size={14} className={loading ? 'spin' : ''} />
          </button>
          <button
            className={`logs-live-btn${autoRefresh ? ' logs-live-btn--active' : ''}`}
            onClick={() => setAutoRefresh(v => !v)}
          >
            <Radio size={13} />
            {t('admin.logs.live')}
          </button>
        </div>

        {/* Level filter chips */}
        <div className="logs-toolbar__row">
          <div className="logs-level-chips" role="group" aria-label={t('admin.logs.logLevel')}>
            {LEVELS.map(l => (
              <button
                key={l.value}
                className={`logs-level-chip logs-level-chip--${l.value || 'all'}${level === l.value ? ' logs-level-chip--active' : ''}`}
                onClick={() => setLevel(l.value)}
              >
                {l.value === '' ? t('admin.logs.levelAll') : l.label}
                {l.value && <span className="logs-level-chip__count">{levelCounts[l.value] ?? 0}</span>}
              </button>
            ))}
          </div>
          <span className="logs-count">{t('admin.logs.entries', { count: entries.length })}</span>
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="logs-error">
          <AlertTriangle size={14} />
          {error}
        </div>
      )}

      {/* Log viewer */}
      {loading ? (
        <div className="admin-loading">{t('admin.logs.loadingLogs')}</div>
      ) : entries.length === 0 && !error ? (
        <div className="admin-empty">{t('admin.logs.noEntries')}</div>
      ) : (
        <div className="log-viewer" ref={containerRef}>
          {entries.map((entry, i) => (
            <LogRow key={i} entry={entry} search={debouncedSearch} defaultExpanded={false} />
          ))}
        </div>
      )}
    </div>
  )
}
