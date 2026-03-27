import { useEffect, useState } from 'react'
import {
  getUsageStats, getModelStats, getIngestionStats, getSearchStats,
  type DailyUsageStat, type ModelUsageStat, type IngestionStat, type SearchStat,
} from '../../api/admin'

function BarChart({ data, label, valueKey }: {
  data: DailyUsageStat[]
  label: string
  valueKey: 'requests' | 'tokens'
}) {
  const values = data.map(d => d[valueKey])
  const max = Math.max(...values, 1)
  return (
    <div className="admin-chart">
      <h3>{label}</h3>
      <div className="admin-chart-bars">
        {data.map((d, i) => (
          <div
            key={i}
            className="admin-chart-bar"
            style={{ height: `${(d[valueKey] / max) * 100}%` }}
            title={`${d.date}: ${d[valueKey].toLocaleString()} ${valueKey}`}
          />
        ))}
      </div>
      {data.length > 0 && (
        <div className="admin-chart-labels">
          <span>{data[0]?.date}</span>
          <span>{data[data.length - 1]?.date}</span>
        </div>
      )}
    </div>
  )
}

export function StatsPage() {
  const [daily, setDaily] = useState<DailyUsageStat[]>([])
  const [models, setModels] = useState<ModelUsageStat[]>([])
  const [ingestion, setIngestion] = useState<IngestionStat | null>(null)
  const [searchStats, setSearchStats] = useState<SearchStat | null>(null)
  const [days, setDays] = useState(30)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      getUsageStats(days),
      getModelStats(days),
      getIngestionStats(),
      getSearchStats(days),
    ])
      .then(([usage, mdl, ing, srch]) => {
        setDaily(usage.daily)
        setModels(mdl)
        setIngestion(ing)
        setSearchStats(srch)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [days])

  if (loading) return <div className="admin-loading">Loading stats...</div>

  return (
    <div>
      <div className="admin-page-header">
        <h1>Statistics</h1>
        <p>Platform-wide analytics</p>
      </div>

      <div className="admin-toolbar" style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', marginBottom: 16 }}>
        <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>Period:</span>
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

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 24 }}>
        <BarChart data={daily} label="Requests per day" valueKey="requests" />
        <BarChart data={daily} label="Tokens per day" valueKey="tokens" />
      </div>

      <h2 className="admin-section-title">LLM Models</h2>
      {models.length > 0 ? (
        <div className="admin-table-wrapper">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Model</th>
                <th>Provider</th>
                <th>Requests</th>
                <th>Total Tokens</th>
                <th>Avg Duration</th>
              </tr>
            </thead>
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
      ) : (
        <div className="admin-empty">No model data available</div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginTop: 8 }}>
        {ingestion && (
          <div>
            <h2 className="admin-section-title">Ingestion</h2>
            <div className="admin-detail-card">
              <dl>
                <div className="admin-detail-row"><dt>Total ingested</dt><dd>{ingestion.total_ingested}</dd></div>
                <div className="admin-detail-row"><dt>Avg duration</dt><dd>{ingestion.avg_duration_ms != null ? `${Math.round(ingestion.avg_duration_ms)}ms` : '—'}</dd></div>
                <div className="admin-detail-row"><dt>Total chunks</dt><dd>{ingestion.total_chunks.toLocaleString()}</dd></div>
                <div className="admin-detail-row"><dt>Pending</dt><dd>{ingestion.pending_count}</dd></div>
                <div className="admin-detail-row"><dt>Errors</dt><dd style={{ color: ingestion.error_count > 0 ? '#ef4444' : undefined }}>{ingestion.error_count}</dd></div>
              </dl>
              {ingestion.top_errors.length > 0 && (
                <div style={{ marginTop: 12 }}>
                  <h3 style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 8 }}>TOP ERRORS</h3>
                  {ingestion.top_errors.map((e, i) => (
                    <div key={i} style={{ fontSize: 12, color: '#ef4444', marginBottom: 4 }}>
                      ({e.count}x) {e.message}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {searchStats && (
          <div>
            <h2 className="admin-section-title">Search Quality</h2>
            <div className="admin-detail-card">
              <dl>
                <div className="admin-detail-row"><dt>Total searches</dt><dd>{searchStats.total_searches.toLocaleString()}</dd></div>
                <div className="admin-detail-row"><dt>Avg similarity</dt><dd>{searchStats.avg_similarity != null ? searchStats.avg_similarity.toFixed(4) : '—'}</dd></div>
                <div className="admin-detail-row"><dt>Avg duration</dt><dd>{searchStats.avg_duration_ms != null ? `${Math.round(searchStats.avg_duration_ms)}ms` : '—'}</dd></div>
                <div className="admin-detail-row"><dt>Zero results</dt><dd style={{ color: searchStats.zero_result_count > 0 ? '#f59e0b' : undefined }}>{searchStats.zero_result_count}</dd></div>
              </dl>
              {searchStats.top_queries.length > 0 && (
                <div style={{ marginTop: 12 }}>
                  <h3 style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 8 }}>TOP QUERIES</h3>
                  {searchStats.top_queries.slice(0, 10).map((q, i) => (
                    <div key={i} style={{ fontSize: 12, marginBottom: 4, display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 250 }}>{q.query}</span>
                      <span style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>{q.count}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
