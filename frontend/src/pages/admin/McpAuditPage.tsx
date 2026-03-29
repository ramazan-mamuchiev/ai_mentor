import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  ArrowLeft, Plug, Search, X, AlertTriangle, Clock, User, ChevronRight,
} from 'lucide-react'
import {
  listMcpRequests, getMcpRequestDetail, searchTenants,
  type McpRequestItem, type McpRequestDetail, type TenantSearchResult,
} from '../../api/admin'

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

function fmtTime(iso: string) {
  const d = new Date(iso)
  return d.toLocaleDateString(undefined, { day: '2-digit', month: '2-digit', year: 'numeric' })
    + ', ' + d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function fmtMs(v: number | null) { return v != null ? `${Math.round(v)}ms` : '—' }
function fmtUsd(v: string) { return `$${parseFloat(v).toFixed(6)}` }

function RequestDetail({ requestId, onBack }: { requestId: string; onBack: () => void }) {
  const { t } = useTranslation()
  const [detail, setDetail] = useState<McpRequestDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    setLoading(true)
    setError('')
    getMcpRequestDetail(requestId)
      .then(setDetail)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [requestId])

  if (loading) return <div className="admin-loading">{t('admin.common.loading')}</div>
  if (error) return (
    <div>
      <button className="chat-audit-back" onClick={onBack}><ArrowLeft size={14} /> {t('admin.mcp.detail.back')}</button>
      <div className="chat-audit-error"><AlertTriangle size={14} /> {error}</div>
    </div>
  )
  if (!detail) return <div className="admin-empty">Not found</div>

  return (
    <div className="admin-page">
      <button className="chat-audit-back" onClick={onBack}><ArrowLeft size={14} /> {t('admin.mcp.detail.back')}</button>
      <div className="admin-page-header" style={{ marginTop: 8 }}>
        <h1>{t('admin.mcp.detail.title')}</h1>
        <p>
          <span className="badge badge--blue">{detail.tool_name}</span>
          {' '}{detail.tenant_email || '—'}
          {detail.key_prefix && <> · <code>{detail.key_prefix}…</code></>}
          {' · '}{fmtTime(detail.created_at)}
          {detail.status === 'error' && <span className="badge badge--red" style={{ marginLeft: 8 }}>error</span>}
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginTop: 16 }}>
        <div className="admin-detail-card">
          <h3 style={{ margin: '0 0 8px' }}>Query</h3>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
            {detail.query_text || '—'}
          </div>
          {(detail.product_filter || detail.version_filter || detail.doc_type_filter) && (
            <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-muted)' }}>
              {detail.product_filter && <span>Product: {detail.product_filter} </span>}
              {detail.version_filter && <span>· Version: {detail.version_filter} </span>}
              {detail.doc_type_filter && <span>· Type: {detail.doc_type_filter}</span>}
            </div>
          )}
          <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-muted)' }}>
            Results: {detail.result_count} · Top similarity: {detail.top_similarity.toFixed(4)} · Response: {detail.response_length.toLocaleString()} chars
          </div>
        </div>

        <div className="admin-detail-card">
          <h3 style={{ margin: '0 0 8px' }}>{t('admin.mcp.detail.timing')}</h3>
          <dl>
            <div className="admin-detail-row"><dt>Total</dt><dd>{fmtMs(detail.duration_ms)}</dd></div>
            <div className="admin-detail-row"><dt>Embedding</dt><dd>{fmtMs(detail.embed_ms)}</dd></div>
            <div className="admin-detail-row"><dt>Search</dt><dd>{fmtMs(detail.search_ms)}</dd></div>
            <div className="admin-detail-row"><dt>Rerank</dt><dd>{fmtMs(detail.rerank_ms)}</dd></div>
          </dl>
        </div>

        <div className="admin-detail-card">
          <h3 style={{ margin: '0 0 8px' }}>{t('admin.mcp.detail.tokens')}</h3>
          <dl>
            <div className="admin-detail-row"><dt>Query tokens</dt><dd>{detail.query_tokens}</dd></div>
            <div className="admin-detail-row"><dt>Response tokens</dt><dd>{detail.response_tokens}</dd></div>
            <div className="admin-detail-row"><dt>Embedding tokens</dt><dd>{detail.embedding_tokens}</dd></div>
            <div className="admin-detail-row"><dt>Rerank prompt</dt><dd>{detail.rerank_prompt_tokens}</dd></div>
            <div className="admin-detail-row"><dt>Rerank completion</dt><dd>{detail.rerank_completion_tokens}</dd></div>
            {detail.rerank_model && <div className="admin-detail-row"><dt>Rerank model</dt><dd>{detail.rerank_model}</dd></div>}
          </dl>
          <div style={{ marginTop: 8, borderTop: '1px solid var(--border)', paddingTop: 8 }}>
            <div className="admin-detail-row"><dt>COGS</dt><dd>{fmtUsd(detail.cogs_usd)}</dd></div>
            <div className="admin-detail-row"><dt>Charge</dt><dd>{fmtUsd(detail.charge_usd)}</dd></div>
          </div>
        </div>

        <div className="admin-detail-card">
          <h3 style={{ margin: '0 0 8px' }}>{t('admin.mcp.detail.client')}</h3>
          <dl>
            <div className="admin-detail-row"><dt>IP</dt><dd>{detail.client_ip || '—'}</dd></div>
            <div className="admin-detail-row"><dt>User-Agent</dt><dd style={{ fontSize: 11, wordBreak: 'break-all' }}>{detail.user_agent || '—'}</dd></div>
            <div className="admin-detail-row"><dt>Request ID</dt><dd style={{ fontSize: 11 }}>{detail.request_id}</dd></div>
          </dl>
          {detail.error && (
            <div style={{ marginTop: 8, padding: 8, background: 'var(--error-bg, #fef2f2)', borderRadius: 4, fontSize: 12, color: '#ef4444' }}>
              {detail.error}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export function McpAuditPage() {
  const { t } = useTranslation()
  const [searchParams, setSearchParams] = useSearchParams()

  const selectedRequestId = searchParams.get('request')

  const [items, setItems] = useState<McpRequestItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [timeRange, setTimeRange] = useState('')
  const [toolFilter, setToolFilter] = useState('')
  const [tenantFilter, setTenantFilter] = useState<TenantSearchResult | null>(null)
  const [tenantQuery, setTenantQuery] = useState('')
  const [tenantOptions, setTenantOptions] = useState<TenantSearchResult[]>([])
  const [tenantDropdownOpen, setTenantDropdownOpen] = useState(false)
  const tenantDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const tenantWrapRef = useRef<HTMLDivElement>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const pageSize = 50

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
        date_from: start,
        date_to: end,
      })
      setItems(res.items)
      setTotal(res.total)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load')
    }
    setLoading(false)
  }, [page, tenantFilter, toolFilter, timeRange])

  useEffect(() => { load() }, [load])

  if (selectedRequestId) {
    return (
      <RequestDetail
        requestId={selectedRequestId}
        onBack={() => setSearchParams({}, { replace: true })}
      />
    )
  }

  const totalPages = Math.ceil(total / pageSize)

  return (
    <div className="chat-audit-page">
      <div className="admin-page-header">
        <h1><Plug size={20} /> {t('admin.mcp.title')}</h1>
        <p>{t('admin.mcp.requestsCount', { count: total })}</p>
      </div>

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

        <div className="chat-audit-mode-chips">
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

        <span className="logs-count">{total} requests</span>
      </div>

      {error && <div className="chat-audit-error"><AlertTriangle size={14} /> {error}</div>}

      {loading ? (
        <div className="admin-loading">{t('admin.common.loading')}</div>
      ) : items.length === 0 ? (
        <div className="admin-empty">{t('admin.mcp.noRequests')}</div>
      ) : (
        <>
          <div className="admin-table-wrapper">
            <div className="admin-table-scroll">
              <table className="admin-table">
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
                  {items.map(r => (
                    <tr
                      key={r.id}
                      style={{ cursor: 'pointer' }}
                      onClick={() => setSearchParams({ request: r.request_id })}
                    >
                      <td style={{ whiteSpace: 'nowrap', fontSize: 12 }}>{fmtTime(r.created_at)}</td>
                      <td style={{ fontSize: 12 }}>
                        {r.tenant_email || '—'}
                        {r.key_prefix && <div style={{ color: 'var(--text-muted)', fontSize: 11 }}><code>{r.key_prefix}…</code></div>}
                      </td>
                      <td><span className="badge badge--blue">{r.tool_name.replace('_', ' ')}</span></td>
                      <td style={{ maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 12 }}>{r.query_text || '—'}</td>
                      <td>{r.result_count}</td>
                      <td style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>{fmtMs(r.duration_ms)}</td>
                      <td style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>{(r.query_tokens + r.response_tokens + r.embedding_tokens).toLocaleString()}</td>
                      <td style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>{fmtUsd(r.charge_usd)}</td>
                      <td>
                        {r.status === 'error'
                          ? <span className="badge badge--red">error</span>
                          : <span className="badge badge--green">ok</span>}
                      </td>
                      <td><ChevronRight size={14} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
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
    </div>
  )
}
