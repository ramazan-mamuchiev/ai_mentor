import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  RefreshCw, X, Search, Radio, ChevronDown, ChevronRight,
  Copy, Check, Clock, AlertTriangle, ScrollText, Download, Loader2,
} from 'lucide-react'
import { getLogs, type LogEntry, type TenantSearchResult } from '../../api/admin'
import { TenantFilterCombo } from '../../components/TenantFilterCombo'

const SERVICES = ['', 'api', 'worker', 'beat', 'web', 'postgres', 'redis'] as const

const LEVELS = [
  { value: '', label: 'All', color: '' },
  { value: 'info', label: 'INFO', color: 'var(--log-info)' },
  { value: 'warning', label: 'WARN', color: 'var(--log-warn)' },
  { value: 'error', label: 'ERROR', color: 'var(--log-error)' },
  { value: 'debug', label: 'DEBUG', color: 'var(--log-debug)' },
] as const

import { timeRangeToISO, highlightSearch } from '../../utils/auditUtils'
import { LOGS_REFRESH_INTERVAL } from './constants'

const TIME_RANGES = [
  { value: '15m', label: '15m' },
  { value: '1h', label: '1h' },
  { value: '3h', label: '3h' },
  { value: '6h', label: '6h' },
  { value: '24h', label: '24h' },
  { value: '7d', label: '7d' },
] as const

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


function LogRow({ entry, search, defaultExpanded, showService }: {
  entry: LogEntry; search: string; defaultExpanded: boolean; showService?: boolean
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
    <div className={`log-row ${expanded ? 'log-row--expanded' : ''}`} onClick={() => { if (window.getSelection()?.toString()) return; setExpanded(v => !v) }}>
      <div className="log-row__header">
        <span className="log-row__expand">
          {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        </span>
        <span className="log-row__ts">{formatTimestamp(entry.timestamp)}</span>
        <span className={`log-row__level log-row__level--${lvl}`}>{lvl === 'warning' ? 'WARN' : lvl.toUpperCase()}</span>
        {showService && entry.service && <span className="log-row__service">{entry.service}</span>}
        <span className="log-row__summary">{highlightSearch(String(summary), search)}</span>
        <button className="log-row__copy" onClick={handleCopy} title={t('admin.logs.copyRaw')}>
          {copied ? <Check size={12} /> : <Copy size={12} />}
        </button>
      </div>
      {expanded && (
        <div className="log-row__details">
          <div className="log-row__field">
            <span className="log-row__key">timestamp</span>
            <span className="log-row__value">{formatTimestamp(entry.timestamp)}</span>
          </div>
          {extraKeys.map(([k, v]) => (
            <div className="log-row__field" key={k}>
              <span className="log-row__key">{k}</span>
              <span className="log-row__value">{highlightSearch(String(v), search)}</span>
            </div>
          ))}
          <div className="log-row__query-text">
            <span className="log-row__key">message</span>
            <p>{String(summary)}</p>
          </div>
        </div>
      )}
    </div>
  )
}

type ExportFormat = 'json' | 'txt' | 'csv'

function parseLogEntry(entry: LogEntry): Record<string, unknown> {
  const parsed = tryParseJSON(entry.message)
  if (!parsed) return { timestamp: entry.timestamp, level: entry.level, service: entry.service, event: entry.message }
  const { level: _l, timestamp: _t, ...rest } = parsed
  return { timestamp: entry.timestamp, level: entry.level, service: entry.service, ...rest }
}

function entriesToJSON(entries: LogEntry[]): string {
  return JSON.stringify(entries.map(parseLogEntry), null, 2)
}

function entriesToTXT(entries: LogEntry[]): string {
  return entries.map(e => {
    const p = parseLogEntry(e)
    const ts = formatTimestamp(e.timestamp)
    const lvl = String(p.level || 'info').toUpperCase().padEnd(5)
    const svc = p.service ? `[${p.service}]` : ''
    const event = String(p.event || p.message || e.message || '')
    const extra = Object.entries(p)
      .filter(([k]) => !['timestamp', 'level', 'service', 'event', 'message'].includes(k))
      .map(([k, v]) => `${k}=${v}`)
      .join(' ')
    return `${ts} ${lvl} ${svc} ${event}${extra ? ' | ' + extra : ''}`
  }).join('\n')
}

function entriesToCSV(entries: LogEntry[]): string {
  const esc = (v: unknown) => `"${String(v ?? '').replace(/"/g, '""')}"`
  const rows = entries.map(e => {
    const p = parseLogEntry(e)
    return [formatTimestamp(e.timestamp), p.level, p.service, String(p.event || p.message || e.message || '')].map(esc).join(',')
  })
  return ['timestamp,level,service,event', ...rows].join('\n')
}

function downloadBlob(content: string, filename: string, mime: string) {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

export function LogsPage() {
  const { t } = useTranslation()
  const [entries, setEntries] = useState<LogEntry[]>([])
  const [service, setService] = useState('')
  const [level, setLevel] = useState('')
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [timeRange, setTimeRange] = useState('1h')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [autoRefresh, setAutoRefresh] = useState(false)
  const [tenantFilter, setTenantFilter] = useState<TenantSearchResult | null>(null)
  const [exportOpen, setExportOpen] = useState(false)
  const [exporting, setExporting] = useState(false)
  const exportRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => setDebouncedSearch(search), 400)
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current) }
  }, [search])

  useEffect(() => {
    if (!exportOpen) return
    const handler = (e: MouseEvent) => {
      if (exportRef.current && !exportRef.current.contains(e.target as Node)) setExportOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [exportOpen])

  const handleExport = useCallback(async (format: ExportFormat) => {
    setExportOpen(false)
    setExporting(true)
    try {
      const { start, end } = timeRangeToISO(timeRange)
      const res = await getLogs({
        service,
        level: level || undefined,
        search: debouncedSearch || undefined,
        tenant: tenantFilter?.name || undefined,
        start: start || undefined,
        end: end || undefined,
        limit: 5000,
      })
      const data = res.entries
      if (!data.length) return

      const date = new Date().toISOString().slice(0, 10)
      const svc = service || 'all'
      const base = `ai-mentor-logs_${svc}_${timeRange}_${date}`

      const converters: Record<ExportFormat, { fn: (e: LogEntry[]) => string; ext: string; mime: string }> = {
        json: { fn: entriesToJSON, ext: 'json', mime: 'application/json' },
        txt: { fn: entriesToTXT, ext: 'txt', mime: 'text/plain' },
        csv: { fn: entriesToCSV, ext: 'csv', mime: 'text/csv' },
      }
      const c = converters[format]
      downloadBlob(c.fn(data), `${base}.${c.ext}`, c.mime)
    } catch {
      /* silently fail */
    } finally {
      setExporting(false)
    }
  }, [service, level, debouncedSearch, tenantFilter, timeRange])

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
      intervalRef.current = setInterval(load, LOGS_REFRESH_INTERVAL)
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
            {SERVICES.map(s => <option key={s || '_all'} value={s}>{s || t('admin.logs.allServices', { defaultValue: 'Все' })}</option>)}
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
          <TenantFilterCombo
            value={tenantFilter}
            onChange={setTenantFilter}
          />

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

          {/* Refresh, Export & Live tail */}
          <button className="logs-icon-btn" onClick={load}>
            <RefreshCw size={14} className={loading ? 'spin' : ''} />
          </button>
          <div className="logs-export-wrap" ref={exportRef}>
            <button
              className="logs-icon-btn"
              onClick={() => setExportOpen(v => !v)}
              disabled={exporting || entries.length === 0}
            >
              {exporting ? <Loader2 size={14} className="spin" /> : <Download size={14} />}
            </button>
            {exportOpen && (
              <div className="logs-export-dropdown">
                <button className="logs-export-dropdown__item" onClick={() => handleExport('json')}>JSON</button>
                <button className="logs-export-dropdown__item" onClick={() => handleExport('txt')}>TXT</button>
                <button className="logs-export-dropdown__item" onClick={() => handleExport('csv')}>CSV</button>
              </div>
            )}
          </div>
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
            <LogRow key={i} entry={entry} search={debouncedSearch} defaultExpanded={false} showService={!service} />
          ))}
        </div>
      )}
    </div>
  )
}
