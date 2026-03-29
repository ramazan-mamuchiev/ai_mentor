import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  Plug, AlertTriangle, Clock, Bug, FileSearch, Search, X,
  ChevronDown, ChevronRight, Copy, Check, RefreshCw, Download, Radio, Loader2,
} from 'lucide-react'
import {
  listMcpRequests, getMcpRequestDetail,
  type McpRequestItem, type McpRequestDetail, type TenantSearchResult,
} from '../../api/admin'
import { RightPanel } from '../../components/RightPanel'
import { TenantFilterCombo } from '../../components/TenantFilterCombo'
import { TIME_RANGES, timeRangeToISO, fmtTs, fmtMs, fmtUsd, highlightSearch, downloadBlob, exportItemsJSON, exportItemsCSV } from '../../utils/auditUtils'
import type { McpSourceInfo } from '../../types'

const TOOLS = ['', 'search_documentation', 'get_api_endpoint', 'list_products'] as const

function totalTokens(r: McpRequestItem): number {
  return r.query_tokens + r.response_tokens + r.embedding_tokens
    + (r.rerank_total_tokens || 0)
    + (r.resolve_prompt_tokens || 0) + (r.resolve_completion_tokens || 0)
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
  const [statusFilter, setStatusFilter] = useState<'' | 'ok' | 'error'>('')
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const searchDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [tenantFilter, setTenantFilter] = useState<TenantSearchResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [panel, setPanel] = useState<PanelState>(null)
  const [panelLoading, setPanelLoading] = useState(false)
  const [autoRefresh, setAutoRefresh] = useState(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const [exportOpen, setExportOpen] = useState(false)
  const [exporting, setExporting] = useState(false)
  const exportRef = useRef<HTMLDivElement>(null)
  const pageSize = 50

  useEffect(() => {
    if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current)
    searchDebounceRef.current = setTimeout(() => {
      setDebouncedSearch(search)
      setPage(1)
    }, 300)
    return () => { if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current) }
  }, [search])

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const { start, end } = timeRangeToISO(timeRange)
      const res = await listMcpRequests({
        page, page_size: pageSize,
        tenant_id: tenantFilter?.id,
        tool_name: toolFilter || undefined,
        status: statusFilter || undefined,
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
  }, [page, tenantFilter, toolFilter, statusFilter, timeRange, debouncedSearch])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (autoRefresh) {
      intervalRef.current = setInterval(load, 5000)
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current) }
  }, [autoRefresh, load])

  useEffect(() => {
    if (!exportOpen) return
    const handler = (e: MouseEvent) => {
      if (exportRef.current && !exportRef.current.contains(e.target as Node)) setExportOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [exportOpen])

  const handleExport = useCallback((format: 'json' | 'csv') => {
    setExportOpen(false)
    setExporting(true)
    try {
      const date = new Date().toISOString().slice(0, 10)
      const base = `lexiro-mcp-audit_${date}`
      if (format === 'json') {
        downloadBlob(exportItemsJSON(items), `${base}.json`, 'application/json')
      } else {
        const cols = ['created_at', 'tool_name', 'query_text', 'result_count', 'top_similarity', 'duration_ms', 'charge_usd', 'status', 'tenant_email', 'request_id']
        downloadBlob(exportItemsCSV(items as unknown as Record<string, unknown>[], cols), `${base}.csv`, 'text/csv')
      }
    } finally {
      setExporting(false)
    }
  }, [items])

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

            <TenantFilterCombo
              value={tenantFilter}
              onChange={v => { setTenantFilter(v); setPage(1) }}
            />

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

          <button className="logs-icon-btn" onClick={load}>
            <RefreshCw size={14} className={loading ? 'spin' : ''} />
          </button>
          <div className="logs-export-wrap" ref={exportRef}>
            <button
              className="logs-icon-btn"
              onClick={() => setExportOpen(v => !v)}
              disabled={exporting || items.length === 0}
            >
              {exporting ? <Loader2 size={14} className="spin" /> : <Download size={14} />}
            </button>
            {exportOpen && (
              <div className="logs-export-dropdown">
                <button className="logs-export-dropdown__item" onClick={() => handleExport('json')}>JSON</button>
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

          <div className="logs-toolbar__row">
            <div className="logs-level-chips" role="group" aria-label="Status">
              <button
                className={`logs-level-chip logs-level-chip--all${statusFilter === '' ? ' logs-level-chip--active' : ''}`}
                onClick={() => { setStatusFilter(''); setPage(1) }}
              >
                All
              </button>
              <button
                className={`logs-level-chip logs-level-chip--info${statusFilter === 'ok' ? ' logs-level-chip--active' : ''}`}
                onClick={() => { setStatusFilter('ok'); setPage(1) }}
              >
                OK <span className="logs-level-chip__count">{statusCounts.ok}</span>
              </button>
              <button
                className={`logs-level-chip logs-level-chip--error${statusFilter === 'error' ? ' logs-level-chip--active' : ''}`}
                onClick={() => { setStatusFilter('error'); setPage(1) }}
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
