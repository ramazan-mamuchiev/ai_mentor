import { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { BarChart3 } from 'lucide-react'
import {
  getOverview, getUsageStats, getModelStats, getIngestionStats, getSearchStats,
  getChatStats, getDocumentStats, getExtendedSearchStats, getCostStats, getMcpStats,
  type PlatformOverview, type DailyUsageStat, type ModelUsageStat, type IngestionStat,
  type ChatStats as ChatStatsT, type DocumentStats as DocStatsT,
  type ExtendedSearchStats as SearchStatsT, type CostStats as CostStatsT,
  type McpStats as McpStatsT,
} from '../../api/admin'

const TABS = ['overview', 'chat', 'documents', 'search', 'mcp', 'costs'] as const
type Tab = typeof TABS[number]

function SimpleBar({ data, labelKey, valueKey, label }: {
  data: Array<Record<string, any>>; labelKey: string; valueKey: string; label: string
}) {
  const values = data.map(d => Number(d[valueKey]) || 0)
  const max = Math.max(...values, 1)
  return (
    <div className="admin-chart">
      <h3>{label}</h3>
      <div className="admin-chart-bars">
        {data.map((d, i) => (
          <div key={i} className="admin-chart-bar"
            style={{ height: `${(values[i] / max) * 100}%` }}
            title={`${d[labelKey]}: ${values[i].toLocaleString()}`}
          />
        ))}
      </div>
      {data.length > 0 && (
        <div className="admin-chart-labels">
          <span>{data[0]?.[labelKey]}</span>
          <span>{data[data.length - 1]?.[labelKey]}</span>
        </div>
      )}
    </div>
  )
}

function StatCard({ label, value, sub, variant }: {
  label: string; value: string | number; sub?: string; variant?: string
}) {
  return (
    <div className={`stat-card${variant ? ` stat-card--${variant}` : ''}`}>
      <span className="stat-card__label">{label}</span>
      <span className="stat-card__value">{value}</span>
      {sub && <span className="stat-card__sub">{sub}</span>}
    </div>
  )
}

function HorizBar({ items, colorVar }: { items: Array<{ label: string; pct: number; sub?: string }>; colorVar?: string }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {items.map((it, i) => (
        <div key={i}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 2 }}>
            <span>{it.label}</span>
            <span style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>{it.pct.toFixed(1)}%{it.sub ? ` (${it.sub})` : ''}</span>
          </div>
          <div style={{ height: 6, borderRadius: 3, background: 'var(--border)' }}>
            <div style={{ height: '100%', borderRadius: 3, width: `${Math.min(it.pct, 100)}%`, background: colorVar || 'var(--accent)' }} />
          </div>
        </div>
      ))}
    </div>
  )
}

function fmtMs(v: number | null) { return v != null ? `${Math.round(v)}ms` : '—' }
function fmtUsd(v: string) { return `$${parseFloat(v).toFixed(4)}` }

function fmtBytes(b: number) {
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
  if (b < 1024 * 1024 * 1024) return `${(b / 1024 / 1024).toFixed(1)} MB`
  return `${(b / 1024 / 1024 / 1024).toFixed(2)} GB`
}

/* ───── Tab: Overview ───── */
function OverviewTab({ days, t }: { days: number; t: any }) {
  const [overview, setOverview] = useState<PlatformOverview | null>(null)
  const [daily, setDaily] = useState<DailyUsageStat[]>([])
  const [models, setModels] = useState<ModelUsageStat[]>([])
  const [ingestion, setIngestion] = useState<IngestionStat | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    Promise.all([getOverview(), getUsageStats(days), getModelStats(days), getIngestionStats()])
      .then(([ov, u, m, i]) => { setOverview(ov); setDaily(u.daily); setModels(m); setIngestion(i) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [days])

  if (loading) return <div className="admin-loading">{t('admin.common.loading')}</div>

  return (
    <>
      {overview && (
        <div className="stats-grid" style={{ marginBottom: 24 }}>
          <StatCard label={t('admin.stats.overview.tenants')} value={`${overview.active_tenants} / ${overview.total_tenants}`} />
          <StatCard label={t('admin.stats.overview.documents')} value={overview.total_documents} sub={`${overview.documents_indexed} ${t('admin.stats.overview.indexed')}`} />
          <StatCard label={t('admin.stats.overview.chunks')} value={overview.total_chunks.toLocaleString()} />
          <StatCard label={t('admin.stats.overview.sessions')} value={overview.total_sessions.toLocaleString()} />
          <StatCard label={t('admin.stats.overview.messages')} value={overview.total_messages.toLocaleString()} />
          <StatCard label={t('admin.stats.overview.apiKeys')} value={overview.total_api_keys} />
          <StatCard label={t('admin.stats.overview.sharedLinks')} value={overview.total_shared_links} />
          <StatCard label={t('admin.stats.overview.prompts')} value={overview.total_prompts} sub={`${overview.customized_prompts} ${t('admin.stats.overview.customized')}`} />
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 24 }}>
        <SimpleBar data={daily} labelKey="date" valueKey="requests" label={t('admin.stats.requestsPerDay')} />
        <SimpleBar data={daily} labelKey="date" valueKey="tokens" label={t('admin.stats.tokensPerDay')} />
      </div>

      <h2 className="admin-section-title">{t('admin.stats.llmModels')}</h2>
      {models.length > 0 ? (
        <div className="admin-table-wrapper" style={{ marginBottom: 16 }}>
          <div className="admin-table-scroll">
            <table className="admin-table">
              <thead><tr>
                <th>{t('admin.stats.model')}</th><th>{t('admin.stats.provider')}</th>
                <th>{t('admin.stats.requests')}</th><th>{t('admin.stats.totalTokens')}</th>
                <th>{t('admin.stats.avgDuration')}</th>
              </tr></thead>
              <tbody>
                {models.map((m, i) => (
                  <tr key={i}>
                    <td><span className="badge badge--blue">{m.model}</span></td>
                    <td>{m.provider}</td>
                    <td>{m.request_count.toLocaleString()}</td>
                    <td>{m.total_tokens.toLocaleString()}</td>
                    <td>{m.avg_total_ms.toFixed(0)}ms</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : <div className="admin-empty">{t('admin.stats.noModelData')}</div>}

      {ingestion && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <div>
            <h2 className="admin-section-title">{t('admin.stats.ingestion')}</h2>
            <div className="admin-detail-card">
              <dl>
                <div className="admin-detail-row"><dt>{t('admin.stats.totalIngested')}</dt><dd>{ingestion.total_ingested}</dd></div>
                <div className="admin-detail-row"><dt>{t('admin.stats.avgDurationMs')}</dt><dd>{fmtMs(ingestion.avg_duration_ms)}</dd></div>
                <div className="admin-detail-row"><dt>{t('admin.stats.totalChunks')}</dt><dd>{ingestion.total_chunks.toLocaleString()}</dd></div>
                <div className="admin-detail-row"><dt>{t('admin.stats.pending')}</dt><dd>{ingestion.pending_count}</dd></div>
                <div className="admin-detail-row"><dt>{t('admin.stats.errors')}</dt><dd style={{ color: ingestion.error_count > 0 ? '#ef4444' : undefined }}>{ingestion.error_count}</dd></div>
              </dl>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

/* ───── Tab: Chat / LLM ───── */
function ChatTab({ days, t }: { days: number; t: any }) {
  const [data, setData] = useState<ChatStatsT | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    getChatStats(days).then(setData).catch(() => {}).finally(() => setLoading(false))
  }, [days])

  if (loading) return <div className="admin-loading">{t('admin.common.loading')}</div>
  if (!data) return <div className="admin-empty">{t('admin.stats.noData')}</div>

  const fb = data.feedback
  const rt = data.response_time

  return (
    <>
      <div className="stats-grid">
        <StatCard label={t('admin.stats.chat.avgResponse')} value={fmtMs(rt.avg_total_ms)} />
        <StatCard label={t('admin.stats.chat.tokensPerSec')} value={rt.avg_tokens_per_sec?.toFixed(1) || '—'} />
        <StatCard label={t('admin.stats.chat.feedbackRate')} value={fb.positive_rate != null ? `${fb.positive_rate}%` : '—'} sub={`${fb.rated_count} / ${fb.total_messages}`} variant={fb.positive_rate != null && fb.positive_rate >= 70 ? 'success' : 'warning'} />
        <StatCard label={t('admin.stats.chat.avgMsgsSession')} value={data.avg_messages_per_session?.toFixed(1) || '—'} />
        <StatCard label={t('admin.stats.chat.errorRate')} value={`${data.error_rate.rate}%`} sub={`${data.error_rate.errors} / ${data.error_rate.total}`} variant={data.error_rate.rate > 5 ? 'warning' : undefined} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, margin: '16px 0' }}>
        <div>
          <h2 className="admin-section-title">{t('admin.stats.chat.responseTimeDaily')}</h2>
          {rt.daily.length > 0 ? (
            <SimpleBar data={rt.daily} labelKey="date" valueKey="avg_total" label={t('admin.stats.chat.avgTotalMs')} />
          ) : <div className="admin-empty">{t('admin.stats.noData')}</div>}
        </div>
        <div>
          <h2 className="admin-section-title">{t('admin.stats.chat.queryTypes')}</h2>
          {data.query_types.length > 0 ? (
            <div className="admin-detail-card" style={{ padding: 16 }}>
              <HorizBar items={data.query_types.map(q => ({ label: q.query_type, pct: q.pct, sub: String(q.count) }))} />
            </div>
          ) : <div className="admin-empty">{t('admin.stats.noData')}</div>}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <div>
          <h2 className="admin-section-title">{t('admin.stats.chat.timeBreakdown')}</h2>
          <div className="admin-detail-card">
            <dl>
              <div className="admin-detail-row"><dt>Total</dt><dd>{fmtMs(rt.avg_total_ms)}</dd></div>
              <div className="admin-detail-row"><dt>LLM</dt><dd>{fmtMs(rt.avg_llm_ms)}</dd></div>
              <div className="admin-detail-row"><dt>RAG</dt><dd>{fmtMs(rt.avg_rag_ms)}</dd></div>
              <div className="admin-detail-row"><dt>Search</dt><dd>{fmtMs(rt.avg_search_ms)}</dd></div>
              <div className="admin-detail-row"><dt>First token</dt><dd>{fmtMs(rt.avg_first_token_ms)}</dd></div>
            </dl>
          </div>
        </div>
        <div>
          <h2 className="admin-section-title">Feedback</h2>
          <div className="admin-detail-card">
            <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
              <div style={{ flex: fb.positive, height: 24, borderRadius: 4, background: '#22c55e', minWidth: fb.positive > 0 ? 4 : 0 }} title={`${fb.positive} positive`} />
              <div style={{ flex: fb.negative, height: 24, borderRadius: 4, background: '#ef4444', minWidth: fb.negative > 0 ? 4 : 0 }} title={`${fb.negative} negative`} />
              <div style={{ flex: Math.max(fb.total_messages - fb.rated_count, 0), height: 24, borderRadius: 4, background: 'var(--border)', minWidth: 4 }} title={`${fb.total_messages - fb.rated_count} unrated`} />
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              {t('admin.stats.chat.feedbackDetail', { positive: fb.positive, negative: fb.negative, unrated: fb.total_messages - fb.rated_count })}
            </div>
          </div>
        </div>
      </div>

      {data.models.length > 0 && (
        <>
          <h2 className="admin-section-title" style={{ marginTop: 16 }}>{t('admin.stats.llmModels')}</h2>
          <div className="admin-table-wrapper">
            <div className="admin-table-scroll">
              <table className="admin-table">
                <thead><tr>
                  <th>{t('admin.stats.model')}</th><th>{t('admin.stats.provider')}</th>
                  <th>{t('admin.stats.requests')}</th><th>{t('admin.stats.totalTokens')}</th>
                  <th>{t('admin.stats.avgDuration')}</th>
                </tr></thead>
                <tbody>
                  {data.models.map((m, i) => (
                    <tr key={i}>
                      <td><span className="badge badge--blue">{m.model}</span></td>
                      <td>{m.provider}</td>
                      <td>{m.request_count.toLocaleString()}</td>
                      <td>{m.total_tokens.toLocaleString()}</td>
                      <td>{m.avg_total_ms.toFixed(0)}ms</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </>
  )
}

/* ───── Tab: Documents ───── */
function DocumentsTab({ days, t }: { days: number; t: any }) {
  const [data, setData] = useState<DocStatsT | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    getDocumentStats(days).then(setData).catch(() => {}).finally(() => setLoading(false))
  }, [days])

  if (loading) return <div className="admin-loading">{t('admin.common.loading')}</div>
  if (!data) return <div className="admin-empty">{t('admin.stats.noData')}</div>

  return (
    <>
      <div className="stats-grid">
        <StatCard label={t('admin.stats.docs.total')} value={data.total} />
        <StatCard label={t('admin.stats.docs.kbSize')} value={fmtBytes(data.total_size_bytes)} />
        <StatCard label={t('admin.stats.docs.totalChunks')} value={data.total_chunks.toLocaleString()} />
        <StatCard label={t('admin.stats.docs.chunkUtil')} value={data.total_chunks > 0 ? `${(data.used_chunks_count / data.total_chunks * 100).toFixed(1)}%` : '—'} sub={`${data.used_chunks_count.toLocaleString()} / ${data.total_chunks.toLocaleString()}`} />
        <StatCard label={t('admin.stats.docs.avgSize')} value={data.avg_size_bytes != null ? `${(data.avg_size_bytes / 1024).toFixed(1)} KB` : '—'} />
        <StatCard label={t('admin.stats.docs.avgChunks')} value={data.avg_chunks?.toFixed(1) || '—'} />
        <StatCard label={t('admin.stats.docs.unused')} value={data.unused_count} variant={data.unused_count > 10 ? 'warning' : undefined} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, margin: '16px 0' }}>
        <div>
          <h2 className="admin-section-title">{t('admin.stats.docs.uploadsDaily')}</h2>
          {data.uploads_daily.length > 0 ? (
            <SimpleBar data={data.uploads_daily} labelKey="date" valueKey="count" label={t('admin.stats.docs.uploadsDaily')} />
          ) : <div className="admin-empty">{t('admin.stats.noData')}</div>}
        </div>
        <div>
          <h2 className="admin-section-title">{t('admin.stats.docs.topProducts')}</h2>
          {data.top_products.length > 0 ? (
            <div className="admin-detail-card" style={{ padding: 16 }}>
              {data.top_products.map((p, i) => (
                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, padding: '4px 0', borderBottom: '1px solid var(--border)' }}>
                  <span>{p.name}</span>
                  <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>{p.count}</span>
                </div>
              ))}
            </div>
          ) : <div className="admin-empty">{t('admin.stats.noData')}</div>}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <div>
          <h2 className="admin-section-title">{t('admin.stats.docs.formats')}</h2>
          <div className="admin-detail-card" style={{ padding: 16 }}>
            <HorizBar items={data.formats.map(f => ({ label: f.format, pct: f.pct, sub: String(f.count) }))} colorVar="var(--accent2)" />
          </div>
        </div>
        <div>
          <h2 className="admin-section-title">{t('admin.stats.docs.topDocs')}</h2>
          {data.top_documents.length > 0 ? (
            <div className="admin-detail-card" style={{ padding: 16, fontSize: 12 }}>
              {data.top_documents.slice(0, 8).map((d, i) => (
                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid var(--border)', gap: 8 }}>
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>{d.title}</span>
                  <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{d.usage_count}x &middot; {fmtUsd(d.charge_usd)}</span>
                </div>
              ))}
            </div>
          ) : <div className="admin-empty">{t('admin.stats.noData')}</div>}
        </div>
      </div>
    </>
  )
}

/* ───── Tab: Search ───── */
function SearchTab({ days, t }: { days: number; t: any }) {
  const [data, setData] = useState<SearchStatsT | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    getExtendedSearchStats(days).then(setData).catch(() => {}).finally(() => setLoading(false))
  }, [days])

  if (loading) return <div className="admin-loading">{t('admin.common.loading')}</div>
  if (!data) return <div className="admin-empty">{t('admin.stats.noData')}</div>

  return (
    <>
      <div className="stats-grid">
        <StatCard label={t('admin.stats.totalSearches')} value={data.total_searches.toLocaleString()} />
        <StatCard label={t('admin.stats.avgSimilarity')} value={data.avg_similarity?.toFixed(4) || '—'} />
        <StatCard label={t('admin.stats.avgDurationMs')} value={fmtMs(data.avg_duration_ms)} />
        <StatCard label={t('admin.stats.zeroResults')} value={data.zero_result_count} variant={data.zero_result_count > 5 ? 'warning' : undefined} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, margin: '16px 0' }}>
        <div>
          <h2 className="admin-section-title">{t('admin.stats.search.daily')}</h2>
          {data.daily.length > 0 ? (
            <SimpleBar data={data.daily} labelKey="date" valueKey="count" label={t('admin.stats.search.searchesPerDay')} />
          ) : <div className="admin-empty">{t('admin.stats.noData')}</div>}
        </div>
        <div>
          <h2 className="admin-section-title">{t('admin.stats.search.sources')}</h2>
          {data.sources.length > 0 ? (
            <div className="admin-detail-card" style={{ padding: 16 }}>
              <HorizBar items={data.sources.map(s => ({ label: s.source, pct: s.pct, sub: String(s.count) }))} colorVar="var(--accent3)" />
            </div>
          ) : <div className="admin-empty">{t('admin.stats.noData')}</div>}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <div>
          <h2 className="admin-section-title">{t('admin.stats.topQueries')}</h2>
          {data.top_queries.length > 0 ? (
            <div className="admin-detail-card" style={{ padding: 16 }}>
              {data.top_queries.slice(0, 10).map((q, i) => (
                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, padding: '3px 0' }}>
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 280 }}>{q.query}</span>
                  <span style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>{q.count}</span>
                </div>
              ))}
            </div>
          ) : <div className="admin-empty">{t('admin.stats.noData')}</div>}
        </div>
      </div>
    </>
  )
}

/* ───── Tab: MCP ───── */
function McpTab({ days, t }: { days: number; t: any }) {
  const [data, setData] = useState<McpStatsT | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    getMcpStats(days).then(setData).catch(() => {}).finally(() => setLoading(false))
  }, [days])

  if (loading) return <div className="admin-loading">{t('admin.common.loading')}</div>
  if (!data) return <div className="admin-empty">{t('admin.stats.noData')}</div>

  const totalTokens = data.total_query_tokens + data.total_response_tokens + data.total_embedding_tokens + (data.total_rerank_tokens || 0) + (data.total_resolve_tokens || 0)

  return (
    <>
      <div className="stats-grid">
        <StatCard label={t('admin.stats.mcp.totalRequests')} value={data.total_requests.toLocaleString()} />
        <StatCard label={t('admin.stats.mcp.totalTokens')} value={totalTokens.toLocaleString()} />
        <StatCard label={t('admin.stats.mcp.avgLatency')} value={fmtMs(data.avg_duration_ms)} />
        <StatCard label={t('admin.stats.mcp.errorRate')} value={`${data.error_rate}%`} sub={`${data.error_count} errors`} variant={data.error_rate > 5 ? 'warning' : undefined} />
        <StatCard label={t('admin.stats.mcp.totalCharge')} value={fmtUsd(data.total_charge_usd)} variant="accent" />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, margin: '16px 0' }}>
        <div>
          <h2 className="admin-section-title">{t('admin.stats.mcp.requestsPerDay')}</h2>
          {data.daily.length > 0 ? (
            <SimpleBar data={data.daily} labelKey="date" valueKey="requests" label={t('admin.stats.mcp.requestsPerDay')} />
          ) : <div className="admin-empty">{t('admin.stats.noData')}</div>}
        </div>
        <div>
          <h2 className="admin-section-title">{t('admin.stats.mcp.byTool')}</h2>
          {data.by_tool.length > 0 ? (
            <div className="admin-detail-card" style={{ padding: 16 }}>
              <HorizBar items={data.by_tool.map(b => ({ label: b.tool_name, pct: b.pct, sub: String(b.count) }))} colorVar="var(--accent3)" />
            </div>
          ) : <div className="admin-empty">{t('admin.stats.noData')}</div>}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <div>
          <h2 className="admin-section-title">{t('admin.stats.mcp.topQueries')}</h2>
          {data.top_queries.length > 0 ? (
            <div className="admin-detail-card" style={{ padding: 16 }}>
              {data.top_queries.slice(0, 10).map((q, i) => (
                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, padding: '3px 0' }}>
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 280 }}>{q.query}</span>
                  <span style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>{q.count}</span>
                </div>
              ))}
            </div>
          ) : <div className="admin-empty">{t('admin.stats.noData')}</div>}
        </div>
        <div>
          <h2 className="admin-section-title">{t('admin.stats.mcp.topTenants')}</h2>
          {data.top_tenants.length > 0 ? (
            <div className="admin-detail-card" style={{ padding: 16 }}>
              {data.top_tenants.map((te, i) => (
                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, padding: '3px 0', borderBottom: '1px solid var(--border)' }}>
                  <span>{te.email}</span>
                  <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>{te.count} req · {fmtUsd(te.charge_usd)}</span>
                </div>
              ))}
            </div>
          ) : <div className="admin-empty">{t('admin.stats.noData')}</div>}
        </div>
      </div>
    </>
  )
}

/* ───── Tab: Costs ───── */
function CostsTab({ days, t }: { days: number; t: any }) {
  const [data, setData] = useState<CostStatsT | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    getCostStats(days).then(setData).catch(() => {}).finally(() => setLoading(false))
  }, [days])

  if (loading) return <div className="admin-loading">{t('admin.common.loading')}</div>
  if (!data) return <div className="admin-empty">{t('admin.stats.noData')}</div>

  return (
    <>
      <div className="stats-grid">
        <StatCard label={t('admin.stats.costs.total')} value={fmtUsd(data.total_charge_usd)} variant="accent" />
        <StatCard label={t('admin.stats.costs.forecast')} value={fmtUsd(data.forecast_month_usd)} />
        <StatCard label={t('admin.stats.costs.perUser')} value={fmtUsd(data.avg_per_user)} />
        <StatCard label={t('admin.stats.costs.perDay')} value={fmtUsd(data.avg_per_day)} />
      </div>

      <div style={{ margin: '16px 0' }}>
        <h2 className="admin-section-title">{t('admin.stats.costs.daily')}</h2>
        {data.daily.length > 0 ? (
          <SimpleBar data={data.daily.map(d => ({ ...d, charge: parseFloat(d.charge_usd) }))} labelKey="date" valueKey="charge" label={t('admin.stats.costs.chargePerDay')} />
        ) : <div className="admin-empty">{t('admin.stats.noData')}</div>}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <div>
          <h2 className="admin-section-title">{t('admin.stats.costs.byModel')}</h2>
          {data.by_model.length > 0 ? (
            <div className="admin-detail-card" style={{ padding: 16 }}>
              {data.by_model.map((m, i) => (
                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, padding: '4px 0', borderBottom: '1px solid var(--border)' }}>
                  <span><span className="badge badge--blue">{m.model}</span></span>
                  <span style={{ fontFamily: 'var(--font-mono)' }}>{fmtUsd(m.total_charge_usd)} &middot; {m.request_count} req</span>
                </div>
              ))}
            </div>
          ) : <div className="admin-empty">{t('admin.stats.noData')}</div>}
        </div>
        <div>
          <h2 className="admin-section-title">{t('admin.stats.costs.byChannel')}</h2>
          {data.by_channel.length > 0 ? (
            <div className="admin-detail-card" style={{ padding: 16 }}>
              {data.by_channel.map((c, i) => (
                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, padding: '4px 0', borderBottom: '1px solid var(--border)' }}>
                  <span className="badge badge--gray">{c.channel}</span>
                  <span style={{ fontFamily: 'var(--font-mono)' }}>{fmtUsd(c.total_charge_usd)} &middot; {c.request_count} req</span>
                </div>
              ))}
            </div>
          ) : <div className="admin-empty">{t('admin.stats.noData')}</div>}
        </div>
      </div>

      {data.top_api_keys.length > 0 && (
        <>
          <h2 className="admin-section-title" style={{ marginTop: 16 }}>{t('admin.stats.costs.topApiKeys')}</h2>
          <div className="admin-table-wrapper">
            <div className="admin-table-scroll">
              <table className="admin-table">
                <thead><tr>
                  <th>{t('admin.stats.costs.keyPrefix')}</th>
                  <th>{t('admin.stats.costs.keyUser')}</th>
                  <th>{t('admin.stats.requests')}</th>
                  <th>{t('admin.stats.costs.charge')}</th>
                </tr></thead>
                <tbody>
                  {data.top_api_keys.map((k, i) => (
                    <tr key={i}>
                      <td><code>{k.key_prefix}…</code></td>
                      <td>{k.email}</td>
                      <td>{k.request_count.toLocaleString()}</td>
                      <td>{fmtUsd(k.charge_usd)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </>
  )
}

/* ───── Main StatsPage ───── */
export function StatsPage() {
  const { t } = useTranslation()
  const [searchParams, setSearchParams] = useSearchParams()
  const activeTab = (searchParams.get('tab') as Tab) || 'overview'
  const [days, setDays] = useState(30)

  const setTab = useCallback((tab: Tab) => {
    setSearchParams({ tab }, { replace: true })
  }, [setSearchParams])

  const tabLabels: Record<Tab, string> = {
    overview: t('admin.stats.tabs.overview'),
    chat: t('admin.stats.tabs.chat'),
    documents: t('admin.stats.tabs.documents'),
    search: t('admin.stats.tabs.search'),
    mcp: t('admin.stats.tabs.mcp'),
    costs: t('admin.stats.tabs.costs'),
  }

  return (
    <div className="admin-page">
      <div className="admin-page-header">
        <h1><BarChart3 size={20} /> {t('admin.stats.title')}</h1>
        <p>{t('admin.stats.subtitle')}</p>
      </div>

      <div className="stats-toolbar">
        <div className="stats-tabs">
          {TABS.map(tab => (
            <button
              key={tab}
              className={`stats-tab${activeTab === tab ? ' stats-tab--active' : ''}`}
              onClick={() => setTab(tab)}
            >
              {tabLabels[tab]}
            </button>
          ))}
        </div>
        <div className="stats-period">
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{t('admin.stats.period')}</span>
          {[7, 14, 30, 90].map(d => (
            <button
              key={d}
              className={`admin-btn admin-btn--sm${days === d ? ' admin-btn--primary' : ''}`}
              onClick={() => setDays(d)}
            >
              {d}d
            </button>
          ))}
        </div>
      </div>

      <div className="stats-content">
        {activeTab === 'overview' && <OverviewTab days={days} t={t} />}
        {activeTab === 'chat' && <ChatTab days={days} t={t} />}
        {activeTab === 'documents' && <DocumentsTab days={days} t={t} />}
        {activeTab === 'search' && <SearchTab days={days} t={t} />}
        {activeTab === 'mcp' && <McpTab days={days} t={t} />}
        {activeTab === 'costs' && <CostsTab days={days} t={t} />}
      </div>
    </div>
  )
}
