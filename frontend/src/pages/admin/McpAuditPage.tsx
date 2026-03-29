import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  Plug, X, AlertTriangle, Clock, User, Bug, FileSearch, Search,
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

const GAP_THRESHOLD_MS = 5 * 60 * 1000

function timeRangeToISO(range: string): { start?: string; end?: string } {
  if (!range) return {}
  const now = Date.now()
  const units: Record<string, number> = { h: 3_600_000, d: 86_400_000 }
  const match = range.match(/^(\d+)([hd])$/)
  if (!match) return {}
  const ms = parseInt(match[1]) * units[match[2]]
  return { start: new Date(now - ms).toISOString(), end: new Date(now).toISOString() }
}

function fmtTime(iso: string) {
  const d = new Date(iso)
  return d.toLocaleDateString(undefined, { day: '2-digit', month: '2-digit', year: 'numeric' })
    + ', ' + d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function fmtMs(v: number | null | undefined) { return v != null ? `${Math.round(v)}ms` : '—' }
function fmtUsd(v: string) { return `$${parseFloat(v).toFixed(6)}` }

function fmtGap(ms: number): string {
  if (ms < 60_000) return `${Math.round(ms / 1000)}s`
  if (ms < 3_600_000) return `${Math.round(ms / 60_000)} min`
  return `${(ms / 3_600_000).toFixed(1)}h`
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

  const tableRows: (McpRequestItem | { type: 'gap'; gap_ms: number })[] = []
  for (let i = 0; i < items.length; i++) {
    tableRows.push(items[i])
    if (i < items.length - 1) {
      const curr = items[i]
      const next = items[i + 1]
      if (curr.key_prefix === next.key_prefix) {
        const gap = new Date(curr.created_at).getTime() - new Date(next.created_at).getTime()
        if (gap > GAP_THRESHOLD_MS) {
          tableRows.push({ type: 'gap', gap_ms: gap })
        }
      }
    }
  }

  const panelDetail = panel?.detail ?? null
  const panelContent = panel?.mode === 'mcp-debug'
    ? { mode: 'mcp-debug' as const, detail: panel.detail }
    : panel?.mode === 'mcp-sources'
      ? { mode: 'mcp-sources' as const, sources: panel.sources }
      : null

  const panelSessionId = panelDetail
    ? `${panelDetail.tool_name} · ${panelDetail.request_id.slice(0, 8)}`
    : undefined

  const COL_COUNT = 10

  return (
    <div className={`docs-page${panel ? ' docs-page--with-panel' : ''}`}>
      <div className="docs-page-main">
        <div className="admin-page-header">
          <h1><Plug size={20} /> {t('admin.mcp.title')}</h1>
          <p>{t('admin.mcp.requestsCount', { count: total })}</p>
        </div>

        {/* Row 1: Search bar + count */}
        <div className="chat-audit-toolbar">
          <div className="chat-audit-search-wrap">
            <Search size={14} className="chat-audit-search-wrap__icon" />
            <input
              className="chat-audit-search"
              placeholder={t('admin.mcp.filterByQuery')}
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
            {search && (
              <button className="chat-audit-search-wrap__clear" onClick={() => setSearch('')} aria-label="Clear">
                <X size={14} />
              </button>
            )}
          </div>
          <span className="logs-count">{total} requests</span>
        </div>

        {/* Row 2: Time range + User filter */}
        <div className="chat-audit-toolbar chat-audit-toolbar--filters">
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
        </div>

        {/* Row 3: Tool chips */}
        <div className="mcp-audit-tools-row">
          {TOOLS.map(tool => (
            <button
              key={tool}
              className={`chat-audit-mode-chip${toolFilter === tool ? ' chat-audit-mode-chip--active' : ''}`}
              onClick={() => { setToolFilter(tool); setPage(1) }}
            >
              {tool || t('admin.mcp.allTools')}
            </button>
          ))}
        </div>

        {error && <div className="chat-audit-error"><AlertTriangle size={14} /> {error}</div>}

        {loading ? (
          <div className="admin-loading">{t('admin.common.loading')}</div>
        ) : items.length === 0 ? (
          <div className="admin-empty">{t('admin.mcp.noRequests')}</div>
        ) : (
          <>
            <div className="mcp-table-container">
              <table className="admin-table mcp-audit-table">
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>User</th>
                    <th>Tool</th>
                    <th>Query</th>
                    <th>Results</th>
                    <th>Duration</th>
                    <th>Tokens</th>
                    <th>Charge</th>
                    <th>Status</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {tableRows.map((row, idx) => {
                    if ('type' in row && row.type === 'gap') {
                      return (
                        <tr key={`gap-${idx}`} className="mcp-time-gap-row">
                          <td colSpan={COL_COUNT}>
                            <div className="mcp-time-gap">
                              <span className="mcp-time-gap__line" />
                              <span className="mcp-time-gap__label">{fmtGap(row.gap_ms)}</span>
                              <span className="mcp-time-gap__line" />
                            </div>
                          </td>
                        </tr>
                      )
                    }
                    const r = row as McpRequestItem
                    const isSelected = panelDetail?.request_id === r.request_id
                    return (
                      <tr
                        key={r.id}
                        className={isSelected ? 'admin-table-row--selected' : ''}
                      >
                        <td className="mcp-td-time">{fmtTime(r.created_at)}</td>
                        <td className="mcp-td-user">
                          {r.tenant_email || '—'}
                          {r.key_prefix && <div className="mcp-key-prefix"><code>{r.key_prefix}…</code></div>}
                        </td>
                        <td><span className="badge badge--blue">{r.tool_name.replace('_', ' ')}</span></td>
                        <td className="mcp-td-query">{r.query_text || '—'}</td>
                        <td>{r.result_count}</td>
                        <td className="mcp-td-mono">{fmtMs(r.duration_ms)}</td>
                        <td className="mcp-td-mono">{(r.query_tokens + r.response_tokens + r.embedding_tokens + (r.rerank_total_tokens || 0) + (r.resolve_prompt_tokens || 0) + (r.resolve_completion_tokens || 0)).toLocaleString()}</td>
                        <td className="mcp-td-mono">{fmtUsd(r.charge_usd)}</td>
                        <td>
                          {r.status === 'error'
                            ? <span className="badge badge--red">error</span>
                            : <span className="badge badge--green">ok</span>}
                        </td>
                        <td className="mcp-td-actions">
                          <button
                            className="mcp-action-btn"
                            title="Debug"
                            onClick={() => openPanel(r.request_id, 'mcp-debug')}
                          >
                            <Bug size={14} />
                          </button>
                          <button
                            className="mcp-action-btn"
                            title="Sources"
                            onClick={() => openPanel(r.request_id, 'mcp-sources')}
                          >
                            <FileSearch size={14} />
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
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
