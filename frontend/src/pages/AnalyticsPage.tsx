import { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { BarChart3 } from 'lucide-react'
import {
  getUsageSummary, getUserChatStats, getUserDocStats, getUserSearchStats, getUserCostStats,
  type UsageSummaryResponse, type UserChatStats as ChatStatsT,
  type UserDocStats as DocStatsT, type UserSearchStats as SearchStatsT,
  type UserCostStats as CostStatsT,
} from '../auth/api'

const TABS = ['overview', 'chat', 'documents', 'search', 'costs'] as const
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
  const [data, setData] = useState<UsageSummaryResponse | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    getUsageSummary(days).then(setData).catch(() => {}).finally(() => setLoading(false))
  }, [days])

  if (loading) return <div className="admin-loading">{t('admin.common.loading')}</div>
  if (!data) return <div className="admin-empty">{t('analytics.noData')}</div>

  return (
    <>
      <div className="stats-grid">
        <StatCard label={t('analytics.kpiRequests')} value={data.total_requests.toLocaleString()} />
        <StatCard label={t('analytics.kpiTokens')} value={data.total_tokens.toLocaleString()} />
        <StatCard label={t('analytics.kpiCharge')} value={`$${data.total_charge_usd}`} variant="accent" />
        <StatCard label={t('analytics.kpiActiveKeys')} value={data.active_keys} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, margin: '16px 0' }}>
        <SimpleBar data={data.daily} labelKey="date" valueKey="requests" label={t('analytics.chartRequests')} />
        <SimpleBar data={data.daily} labelKey="date" valueKey="tokens" label={t('analytics.chartTokens')} />
      </div>

      {data.by_action.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <div>
            <h2 className="admin-section-title">{t('analytics.byAction')}</h2>
            <div className="admin-detail-card" style={{ padding: 16 }}>
              {data.by_action.map((a, i) => (
                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, padding: '4px 0', borderBottom: '1px solid var(--border)' }}>
                  <span><code>{a.action}</code></span>
                  <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>{a.count.toLocaleString()} req · {a.tokens.toLocaleString()} tok</span>
                </div>
              ))}
            </div>
          </div>
          {data.by_key.length > 0 && (
            <div>
              <h2 className="admin-section-title">{t('analytics.byKey')}</h2>
              <div className="admin-detail-card" style={{ padding: 16 }}>
                {data.by_key.map((k, i) => (
                  <div key={i} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, padding: '4px 0', borderBottom: '1px solid var(--border)' }}>
                    <span><code>{k.key_prefix}…</code> {k.key_name && <span style={{ color: 'var(--text-muted)' }}>{k.key_name}</span>}</span>
                    <span style={{ fontFamily: 'var(--font-mono)' }}>{k.total_requests.toLocaleString()} · ${k.total_charge_usd}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </>
  )
}

/* ───── Tab: Chat ───── */
function ChatTab({ days, t }: { days: number; t: any }) {
  const [data, setData] = useState<ChatStatsT | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    getUserChatStats(days).then(setData).catch(() => {}).finally(() => setLoading(false))
  }, [days])

  if (loading) return <div className="admin-loading">{t('admin.common.loading')}</div>
  if (!data) return <div className="admin-empty">{t('analytics.noData')}</div>

  return (
    <>
      <div className="stats-grid">
        <StatCard label={t('analytics.chat.sessions')} value={data.total_sessions.toLocaleString()} />
        <StatCard label={t('analytics.chat.messages')} value={data.total_messages.toLocaleString()} />
        <StatCard label={t('analytics.chat.avgResponse')} value={fmtMs(data.avg_response_ms)} />
        <StatCard label={t('analytics.chat.tokensPerSec')} value={data.avg_tokens_per_sec?.toFixed(1) || '—'} />
        <StatCard label={t('analytics.chat.feedbackRate')} value={data.positive_rate != null ? `${data.positive_rate}%` : '—'}
          sub={`${data.feedback_total} ${t('analytics.chat.rated')}`}
          variant={data.positive_rate != null && data.positive_rate >= 70 ? 'success' : 'warning'} />
        <StatCard label={t('analytics.chat.avgMsgsSession')} value={data.avg_messages_per_session?.toFixed(1) || '—'} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, margin: '16px 0' }}>
        <div>
          <h2 className="admin-section-title">{t('analytics.chat.responseDaily')}</h2>
          {data.response_daily.length > 0 ? (
            <SimpleBar data={data.response_daily} labelKey="date" valueKey="avg_total" label={t('analytics.chat.avgTotalMs')} />
          ) : <div className="admin-empty">{t('analytics.noData')}</div>}
        </div>
        <div>
          <h2 className="admin-section-title">{t('analytics.chat.queryTypes')}</h2>
          {data.query_types.length > 0 ? (
            <div className="admin-detail-card" style={{ padding: 16 }}>
              <HorizBar items={data.query_types.map(q => ({ label: q.query_type, pct: q.pct, sub: String(q.count) }))} />
            </div>
          ) : <div className="admin-empty">{t('analytics.noData')}</div>}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <div>
          <h2 className="admin-section-title">Feedback</h2>
          <div className="admin-detail-card">
            <div style={{ display: 'flex', gap: 8, marginBottom: 12, padding: '12px 16px 0' }}>
              <div style={{ flex: data.feedback_positive, height: 24, borderRadius: 4, background: '#22c55e', minWidth: data.feedback_positive > 0 ? 4 : 0 }} title={`${data.feedback_positive} positive`} />
              <div style={{ flex: data.feedback_negative, height: 24, borderRadius: 4, background: '#ef4444', minWidth: data.feedback_negative > 0 ? 4 : 0 }} title={`${data.feedback_negative} negative`} />
              <div style={{ flex: Math.max(data.total_messages - data.feedback_total, 0), height: 24, borderRadius: 4, background: 'var(--border)', minWidth: 4 }} title="unrated" />
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', padding: '0 16px 12px' }}>
              {t('analytics.chat.feedbackDetail', { positive: data.feedback_positive, negative: data.feedback_negative, unrated: data.total_messages - data.feedback_total })}
            </div>
          </div>
        </div>
      </div>
    </>
  )
}

/* ───── Tab: Documents ───── */
function DocumentsTab({ days, t }: { days: number; t: any }) {
  const [data, setData] = useState<DocStatsT | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    getUserDocStats(days).then(setData).catch(() => {}).finally(() => setLoading(false))
  }, [days])

  if (loading) return <div className="admin-loading">{t('admin.common.loading')}</div>
  if (!data) return <div className="admin-empty">{t('analytics.noData')}</div>

  return (
    <>
      <div className="stats-grid">
        <StatCard label={t('analytics.docs.total')} value={data.total_documents} sub={`${data.documents_indexed} ${t('analytics.docs.indexed')}`} />
        <StatCard label={t('analytics.docs.kbSize')} value={fmtBytes(data.total_size_bytes)} />
        <StatCard label={t('analytics.docs.totalChunks')} value={data.total_chunks.toLocaleString()} />
        <StatCard label={t('analytics.docs.pending')} value={data.documents_pending} variant={data.documents_pending > 0 ? 'warning' : undefined} />
        <StatCard label={t('analytics.docs.errors')} value={data.documents_error} variant={data.documents_error > 0 ? 'warning' : undefined} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, margin: '16px 0' }}>
        <div>
          <h2 className="admin-section-title">{t('analytics.docs.uploadsDaily')}</h2>
          {data.uploads_daily.length > 0 ? (
            <SimpleBar data={data.uploads_daily} labelKey="date" valueKey="count" label={t('analytics.docs.uploadsDaily')} />
          ) : <div className="admin-empty">{t('analytics.noData')}</div>}
        </div>
        <div>
          <h2 className="admin-section-title">{t('analytics.docs.topProducts')}</h2>
          {data.products.length > 0 ? (
            <div className="admin-detail-card" style={{ padding: 16 }}>
              {data.products.map((p, i) => (
                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, padding: '4px 0', borderBottom: '1px solid var(--border)' }}>
                  <span>{p.name}</span>
                  <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>{p.count}</span>
                </div>
              ))}
            </div>
          ) : <div className="admin-empty">{t('analytics.noData')}</div>}
        </div>
      </div>

      {data.formats.length > 0 && (
        <div>
          <h2 className="admin-section-title">{t('analytics.docs.formats')}</h2>
          <div className="admin-detail-card" style={{ padding: 16, maxWidth: 400 }}>
            <HorizBar items={data.formats.map(f => ({ label: f.format, pct: f.pct, sub: String(f.count) }))} colorVar="var(--accent2)" />
          </div>
        </div>
      )}
    </>
  )
}

/* ───── Tab: Search ───── */
function SearchTab({ days, t }: { days: number; t: any }) {
  const [data, setData] = useState<SearchStatsT | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    getUserSearchStats(days).then(setData).catch(() => {}).finally(() => setLoading(false))
  }, [days])

  if (loading) return <div className="admin-loading">{t('admin.common.loading')}</div>
  if (!data) return <div className="admin-empty">{t('analytics.noData')}</div>

  return (
    <>
      <div className="stats-grid">
        <StatCard label={t('analytics.search.totalSearches')} value={data.total_searches.toLocaleString()} />
        <StatCard label={t('analytics.search.avgSimilarity')} value={data.avg_similarity?.toFixed(4) || '—'} />
        <StatCard label={t('analytics.search.avgDuration')} value={fmtMs(data.avg_duration_ms)} />
        <StatCard label={t('analytics.search.zeroResults')} value={data.zero_result_count} variant={data.zero_result_count > 5 ? 'warning' : undefined} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, margin: '16px 0' }}>
        <div>
          <h2 className="admin-section-title">{t('analytics.search.daily')}</h2>
          {data.daily.length > 0 ? (
            <SimpleBar data={data.daily} labelKey="date" valueKey="count" label={t('analytics.search.searchesPerDay')} />
          ) : <div className="admin-empty">{t('analytics.noData')}</div>}
        </div>
        <div>
          <h2 className="admin-section-title">{t('analytics.search.topQueries')}</h2>
          {data.top_queries.length > 0 ? (
            <div className="admin-detail-card" style={{ padding: 16 }}>
              {data.top_queries.map((q, i) => (
                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, padding: '3px 0' }}>
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 280 }}>{q.query}</span>
                  <span style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>{q.count}</span>
                </div>
              ))}
            </div>
          ) : <div className="admin-empty">{t('analytics.noData')}</div>}
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
    getUserCostStats(days).then(setData).catch(() => {}).finally(() => setLoading(false))
  }, [days])

  if (loading) return <div className="admin-loading">{t('admin.common.loading')}</div>
  if (!data) return <div className="admin-empty">{t('analytics.noData')}</div>

  return (
    <>
      <div className="stats-grid">
        <StatCard label={t('analytics.costs.total')} value={fmtUsd(data.total_charge_usd)} variant="accent" />
        <StatCard label={t('analytics.costs.forecast')} value={fmtUsd(data.forecast_month_usd)} />
        <StatCard label={t('analytics.costs.perDay')} value={fmtUsd(data.avg_per_day)} />
      </div>

      <div style={{ margin: '16px 0' }}>
        <h2 className="admin-section-title">{t('analytics.costs.daily')}</h2>
        {data.daily.length > 0 ? (
          <SimpleBar data={data.daily.map(d => ({ ...d, charge: parseFloat(d.charge_usd) }))} labelKey="date" valueKey="charge" label={t('analytics.costs.chargePerDay')} />
        ) : <div className="admin-empty">{t('analytics.noData')}</div>}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <div>
          <h2 className="admin-section-title">{t('analytics.costs.byModel')}</h2>
          {data.by_model.length > 0 ? (
            <div className="admin-detail-card" style={{ padding: 16 }}>
              {data.by_model.map((m, i) => (
                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, padding: '4px 0', borderBottom: '1px solid var(--border)' }}>
                  <span><span className="badge badge--blue">{m.model}</span></span>
                  <span style={{ fontFamily: 'var(--font-mono)' }}>{fmtUsd(m.total_charge_usd)} · {m.request_count} req</span>
                </div>
              ))}
            </div>
          ) : <div className="admin-empty">{t('analytics.noData')}</div>}
        </div>
        <div>
          <h2 className="admin-section-title">{t('analytics.costs.byChannel')}</h2>
          {data.by_channel.length > 0 ? (
            <div className="admin-detail-card" style={{ padding: 16 }}>
              {data.by_channel.map((c, i) => (
                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, padding: '4px 0', borderBottom: '1px solid var(--border)' }}>
                  <span className="badge badge--gray">{c.channel}</span>
                  <span style={{ fontFamily: 'var(--font-mono)' }}>{fmtUsd(c.total_charge_usd)} · {c.request_count} req</span>
                </div>
              ))}
            </div>
          ) : <div className="admin-empty">{t('analytics.noData')}</div>}
        </div>
      </div>
    </>
  )
}

/* ───── Main AnalyticsPage ───── */
export function AnalyticsPage() {
  const { t } = useTranslation()
  const [searchParams, setSearchParams] = useSearchParams()
  const activeTab = (searchParams.get('tab') as Tab) || 'overview'
  const [days, setDays] = useState(30)

  const setTab = useCallback((tab: Tab) => {
    setSearchParams({ tab }, { replace: true })
  }, [setSearchParams])

  const tabLabels: Record<Tab, string> = {
    overview: t('analytics.tabs.overview'),
    chat: t('analytics.tabs.chat'),
    documents: t('analytics.tabs.documents'),
    search: t('analytics.tabs.search'),
    costs: t('analytics.tabs.costs'),
  }

  return (
    <div className="analytics-page">
      <div className="admin-page-header">
        <h1><BarChart3 size={20} /> {t('analytics.title')}</h1>
        <p>{t('analytics.description')}</p>
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
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{t('analytics.period')}</span>
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
        {activeTab === 'costs' && <CostsTab days={days} t={t} />}
      </div>
    </div>
  )
}
