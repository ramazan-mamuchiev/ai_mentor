import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  Plug, X, AlertTriangle, Clock, User, Bug, FileSearch, Search,
  ChevronDown, ChevronRight, Copy, Check,
} from 'lucide-react'
import {
  listMcpRequests, getMcpRequestDetail, searchTenants,
  type McpRequestItem, type McpRequestDetail, type TenantSearchResult,
} from '../../api/admin'
import { RightPanel } from '../../components/RightPanel'
import type { McpSourceInfo } from '../../types'

const TIME_RANGES = [
  { value: '', label: 'All' },
  { value: '24h', label: '24h' },
  { value: '7d', label: '7d' },
  { value: '30d', label: '30d' },
  { value: '90d', label: '90d' },
] as const

const TOOLS = ['', 'search_documentation', 'get_api_endpoint', 'list_products'] as const

function timeRangeToISO(range: string): { start?: string; end?: string } {
  if (!range) return {}
  const now = Date.now()
  const units: Record<string, number> = { h: 3_600_000, d: 86_400_000 }
  const match = range.match(/^(\d+)([hd])$/)
  if (!match) return {}
  const ms = parseInt(match[1]) * units[match[2]]
  return { start: new Date(now - ms).toISOString(), end: new Date(now).toISOString() }
}

function fmtTs(iso: string) {
  const d = new Date(iso)
  const dd = String(d.getDate()).padStart(2, '0')
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const hh = String(d.getHours()).padStart(2, '0')
  const mi = String(d.getMinutes()).padStart(2, '0')
  const ss = String(d.getSeconds()).padStart(2, '0')
  return `${dd}.${mm} ${hh}:${mi}:${ss}`
}

function fmtMs(v: number | null | undefined) { return v != null ? `${Math.round(v)}ms` : '—' }
function fmtUsd(v: string) { return `$${parseFloat(v).toFixed(6)}` }

function totalTokens(r: McpRequestItem): number {
  return r.query_tokens + r.response_tokens + r.embedding_tokens
    + (r.rerank_total_tokens || 0)
    + (r.resolve_prompt_tokens || 0) + (r.resolve_completion_tokens || 0)
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

function McpRow({ item, search, isSelected, onDebug, onSources }: {
  item: McpRequestItem
  search: string
  isSelected: boolean
  onDebug: () => void
  onSources: () => void
}) {
  const [expanded, setExpanded] = useState(false)
  const [copied, setCopied] = useState(false)

  const summary = item.query_text || '—'
  const tokens = totalTokens(item)

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation()
    navigator.clipboard.writeText(JSON.stringify(item, null, 2))
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  const handleClick = () => {
    if (window.getSelection()?.toString()) return
    setExpanded(v => !v)
  }

  const details: [string, string | React.ReactNode][] = [
    ['request_id', item.request_id],
    ['user', item.tenant_email || '—'],
    ['key_prefix', item.key_prefix ? `${item.key_prefix}…` : '—'],
    ['results', String(item.result_count)],
    ['top_similarity', item.top_similarity > 0 ? item.top_similarity.toFixed(4) : '—'],
    ['duration', fmtMs(item.duration_ms)],
    ['query_tokens', item.query_tokens.toLocaleString()],
    ['response_tokens', item.response_tokens.toLocaleString()],
    ['embedding_tokens', item.embedding_tokens.toLocaleString()],
    ['rerank_tokens', (item.rerank_total_tokens || 0).toLocaleString()],
    ['resolve_tokens', ((item.resolve_prompt_tokens || 0) + (item.resolve_completion_tokens || 0)).toLocaleString()],
    ['resolve_model', item.resolve_model || '—'],
    ['resolve_ms', fmtMs(item.resolve_ms)],
    ['charge', fmtUsd(item.charge_usd)],
  ]

  return (
    <div className={`log-row${expanded ? ' log-row--expanded' : ''}${isSelected ? ' log-row--expanded' : ''}`} onClick={handleClick}>
      <div className="log-row__header">
        <span className="log-row__expand">
          {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        </span>
        <span className="log-row__ts">{fmtTs(item.created_at)}</span>
        <span className={`log-row__level log-row__level--${item.status === 'error' ? 'error' : 'info'}`}>
          {item.tool_name.replace(/_/g, ' ')}
        </span>
        <span className="log-row__summary">{highlightSearch(summary, search)}</span>
        <span className="log-row__meta-pill">{tokens.toLocaleString()} tok</span>
        <span className="log-row__meta-pill">{fmtUsd(item.charge_usd)}</span>
        <span className="log-row__meta-pill">{fmtMs(item.duration_ms)}</span>
        {item.status === 'error' && <span className="badge badge--red">error</span>}
        <button className="log-row__copy" onClick={handleCopy} title="Copy JSON">
          {copied ? <Check size={12} /> : <Copy size={12} />}
        </button>
      </div>
      {expanded && (
        <div className="log-row__details">
          {details.map(([k, v]) => (
            <div className="log-row__field" key={k}>
              <span className="log-row__key">{k}</span>
              <span className="log-row__value">{v}</span>
            </div>
          ))}
          <div className="log-row__actions">
            <button className="admin-btn admin-btn--sm" onClick={e => { e.stopPropagation(); onDebug() }}>
              <Bug size={12} /> Debug
            </button>
            <button className="admin-btn admin-btn--sm" onClick={e => { e.stopPropagation(); onSources() }}>
              <FileSearch size={12} /> Sources
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

type PanelState = {
  mode: 'mcp-debug'
  detail: McpRequestDetail
} | {
  mode: 'mcp-sources'
  sources: McpSourceInfo[]
  detail: McpRequestDetail
} | null

export function McpAuditPage() {
  const { t } = useTranslation()
  const [searchParams, setSearchParams] = useSearchParams()

  const [items, setItems] = useState<McpRequestItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [timeRange, setTimeRange] = useState('')
  const [toolFilter, setToolFilter] = useState('')
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const searchDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [tenantFilter, setTenantFilter] = useState<TenantSearchResult | null>(null)
  const [tenantQuery, setTenantQuery] = useState('')
  const [tenantOptions, setTenantOptions] = useState<TenantSearchResult[]>([])
  const [tenantDropdownOpen, setTenantDropdownOpen] = useState(false)
  const tenantDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const tenantWrapRef = useRef<HTMLDivElement>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [panel, setPanel] = useState<PanelState>(null)
  const [panelLoading, setPanelLoading] = useState(false)
  const pageSize = 50

  useEffect(() => {
    if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current)
    searchDebounceRef.current = setTimeout(() => {
      setDebouncedSearch(search)
      setPage(1)
    }, 300)
    return () => { if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current) }
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
    setLoading(true)
    setError('')
    try {
      const { start, end } = timeRangeToISO(timeRange)
      const res = await listMcpRequests({
        page, page_size: pageSize,
        tenant_id: tenantFilter?.id,
        tool_name: toolFilter || undefined,
        search: debouncedSearch || undefined,
        date_from: start,
        date_to: end,
      })
      setItems(res.items)
      setTotal(res.total)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load')
    }
    setLoading(false)
  }, [page, tenantFilter, toolFilter, timeRange, debouncedSearch])

  useEffect(() => { load() }, [load])

  const openPanel = useCallback(async (requestId: string, mode: 'mcp-debug' | 'mcp-sources') => {
    setPanelLoading(true)
    try {
      const detail = await getMcpRequestDetail(requestId)
      if (mode === 'mcp-sources' && detail.sources?.length) {
        setPanel({ mode: 'mcp-sources', sources: detail.sources, detail })
      } else {
        setPanel({ mode: 'mcp-debug', detail })
      }
      setSearchParams({ request: requestId }, { replace: true })
    } catch { /* ignore */ }
    setPanelLoading(false)
  }, [setSearchParams])

  useEffect(() => {
    const rid = searchParams.get('request')
    if (rid && !panel) {
      openPanel(rid, 'mcp-debug')
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const handleClose = useCallback(() => {
    setPanel(null)
    setSearchParams({}, { replace: true })
  }, [setSearchParams])

  const handleSwitchToSources = useCallback(() => {
    if (panel?.mode === 'mcp-debug' && panel.detail.sources?.length) {
      setPanel({ mode: 'mcp-sources', sources: panel.detail.sources, detail: panel.detail })
    }
  }, [panel])

  const totalPages = Math.ceil(total / pageSize)

  const panelDetail = panel?.detail ?? null
  const panelContent = panel?.mode === 'mcp-debug'
    ? { mode: 'mcp-debug' as const, detail: panel.detail }
    : panel?.mode === 'mcp-sources'
      ? { mode: 'mcp-sources' as const, sources: panel.sources }
      : null

  const panelSessionId = panelDetail
    ? `${panelDetail.tool_name} · ${panelDetail.request_id.slice(0, 8)}`
    : undefined

  const statusCounts = useMemo(() => {
    const c = { ok: 0, error: 0 }
    for (const i of items) {
      if (i.status === 'error') c.error++; else c.ok++
    }
    return c
  }, [items])

  return (
    <div className={`docs-page${panel ? ' docs-page--with-panel' : ''}`}>
      <div className="docs-page-main">
        <div className="admin-page-header">
          <h1><Plug size={20} /> {t('admin.mcp.title')}</h1>
          <p>{t('admin.mcp.requestsCount', { count: total })}</p>
        </div>

        <div className="logs-toolbar">
          <div className="logs-toolbar__row">
            <select
              className="logs-select"
              value={toolFilter}
              onChange={e => { setToolFilter(e.target.value); setPage(1) }}
            >
              {TOOLS.map(tool => (
                <option key={tool || '_all'} value={tool}>
                  {tool || t('admin.mcp.allTools')}
                </option>
              ))}
            </select>

            <div className="logs-chips" role="group" aria-label="Time range">
              <Clock size={13} className="logs-chips__icon" />
              {TIME_RANGES.map(r => (
                <button
                  key={r.value}
                  className={`logs-chip${timeRange === r.value ? ' logs-chip--active' : ''}`}
                  onClick={() => { setTimeRange(r.value); setPage(1) }}
                >
                  {r.label}
                </button>
              ))}
            </div>

            <div className="logs-tenant-combo" ref={tenantWrapRef}>
              {tenantFilter ? (
                <div className="logs-tenant-chip">
                  <User size={12} />
                  <span className="logs-tenant-chip__name">{tenantFilter.name}</span>
                  <button className="logs-tenant-chip__clear" onClick={() => { setTenantFilter(null); setTenantQuery(''); setPage(1) }}><X size={12} /></button>
                </div>
              ) : (
                <>
                  <User size={13} className="logs-tenant-combo__icon" />
                  <input
                    className="logs-tenant-input"
                    placeholder="User..."
                    value={tenantQuery}
                    onChange={e => setTenantQuery(e.target.value)}
                    onFocus={() => { if (tenantOptions.length) setTenantDropdownOpen(true) }}
                  />
                  {tenantQuery && (
                    <button className="logs-tenant-combo__clear" onClick={() => { setTenantQuery(''); setTenantOptions([]); setTenantDropdownOpen(false) }}><X size={12} /></button>
                  )}
                </>
              )}
              {tenantDropdownOpen && tenantOptions.length > 0 && (
                <div className="logs-tenant-dropdown">
                  {tenantOptions.map(opt => (
                    <button key={opt.id} className="logs-tenant-dropdown__item" onClick={() => { setTenantFilter(opt); setTenantQuery(''); setTenantDropdownOpen(false); setPage(1) }}>
                      <span className="logs-tenant-dropdown__name">{opt.name}</span>
                      <span className="logs-tenant-dropdown__email">{opt.email}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="logs-search-wrap">
              <Search size={14} className="logs-search-wrap__icon" />
              <input
                className="logs-search"
                placeholder={t('admin.mcp.filterByQuery')}
                value={search}
                onChange={e => setSearch(e.target.value)}
              />
              {search && (
                <button className="logs-search-wrap__clear" onClick={() => setSearch('')} aria-label="Clear">
                  <X size={14} />
                </button>
              )}
            </div>
          </div>

          <div className="logs-toolbar__row">
            <div className="logs-level-chips" role="group" aria-label="Status">
              <button
                className={`logs-level-chip logs-level-chip--all${!statusCounts ? '' : ' logs-level-chip--active'}`}
                disabled
                style={{ opacity: 1, cursor: 'default' }}
              >
                OK <span className="logs-level-chip__count">{statusCounts.ok}</span>
              </button>
              <button
                className="logs-level-chip logs-level-chip--error"
                disabled
                style={{ opacity: 1, cursor: 'default' }}
              >
                ERROR <span className="logs-level-chip__count">{statusCounts.error}</span>
              </button>
            </div>
            <span className="logs-count">{total} requests</span>
          </div>
        </div>

        {error && <div className="chat-audit-error"><AlertTriangle size={14} /> {error}</div>}

        {loading ? (
          <div className="admin-loading">{t('admin.common.loading')}</div>
        ) : items.length === 0 ? (
          <div className="admin-empty">{t('admin.mcp.noRequests')}</div>
        ) : (
          <>
            <div className="log-viewer">
              {items.map(r => (
                <McpRow
                  key={r.id}
                  item={r}
                  search={debouncedSearch}
                  isSelected={panelDetail?.request_id === r.request_id}
                  onDebug={() => openPanel(r.request_id, 'mcp-debug')}
                  onSources={() => openPanel(r.request_id, 'mcp-sources')}
                />
              ))}
            </div>

            {totalPages > 1 && (
              <div className="admin-pagination">
                <span>{t('admin.common.page', { page, total: totalPages })}</span>
                <div className="admin-pagination-buttons">
                  <button className="admin-btn admin-btn--sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>{t('admin.common.prev')}</button>
                  <button className="admin-btn admin-btn--sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>{t('admin.common.next')}</button>
                </div>
              </div>
            )}
          </>
        )}

        {panelLoading && (
          <div style={{ position: 'fixed', top: '50%', right: panel ? '15%' : '50%', transform: 'translate(50%, -50%)', zIndex: 100 }}>
            <div className="admin-loading" style={{ background: 'var(--bg)', padding: '12px 24px', borderRadius: 8, boxShadow: '0 2px 12px rgba(0,0,0,0.15)' }}>
              {t('admin.common.loading')}
            </div>
          </div>
        )}
      </div>

      {panelContent && panelDetail && (
        <RightPanel
          content={panelContent}
          sessionId={panelSessionId}
          onClose={handleClose}
          onSwitchToSources={handleSwitchToSources}
        />
      )}
    </div>
  )
}
