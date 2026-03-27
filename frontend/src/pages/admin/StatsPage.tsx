import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { BarChart3 } from 'lucide-react'
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
  const { t } = useTranslation()
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

  if (loading) return <div className="admin-loading">{t('admin.stats.loadingStats')}</div>

  return (
    <div>
      <div className="admin-page-header">
        <h1><BarChart3 size={20} /> {t('admin.stats.title')}</h1>
        <p>{t('admin.stats.subtitle')}</p>
      </div>

      <div className="admin-toolbar" style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', marginBottom: 16 }}>
        <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{t('admin.stats.period')}</span>
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
        <BarChart data={daily} label={t('admin.stats.requestsPerDay')} valueKey="requests" />
        <BarChart data={daily} label={t('admin.stats.tokensPerDay')} valueKey="tokens" />
      </div>

      <h2 className="admin-section-title">{t('admin.stats.llmModels')}</h2>
      {models.length > 0 ? (
        <div className="admin-table-wrapper">
          <div className="admin-table-scroll">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>{t('admin.stats.model')}</th>
                  <th>{t('admin.stats.provider')}</th>
                  <th>{t('admin.stats.requests')}</th>
                  <th>{t('admin.stats.totalTokens')}</th>
                  <th>{t('admin.stats.avgDuration')}</th>
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
        </div>
      ) : (
        <div className="admin-empty">{t('admin.stats.noModelData')}</div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginTop: 8 }}>
        {ingestion && (
          <div>
            <h2 className="admin-section-title">{t('admin.stats.ingestion')}</h2>
            <div className="admin-detail-card">
              <dl>
                <div className="admin-detail-row"><dt>{t('admin.stats.totalIngested')}</dt><dd>{ingestion.total_ingested}</dd></div>
                <div className="admin-detail-row"><dt>{t('admin.stats.avgDurationMs')}</dt><dd>{ingestion.avg_duration_ms != null ? `${Math.round(ingestion.avg_duration_ms)}ms` : '—'}</dd></div>
                <div className="admin-detail-row"><dt>{t('admin.stats.totalChunks')}</dt><dd>{ingestion.total_chunks.toLocaleString()}</dd></div>
                <div className="admin-detail-row"><dt>{t('admin.stats.pending')}</dt><dd>{ingestion.pending_count}</dd></div>
                <div className="admin-detail-row"><dt>{t('admin.stats.errors')}</dt><dd style={{ color: ingestion.error_count > 0 ? '#ef4444' : undefined }}>{ingestion.error_count}</dd></div>
              </dl>
              {ingestion.top_errors.length > 0 && (
                <div style={{ marginTop: 12 }}>
                  <h3 style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 8 }}>{t('admin.stats.topErrors')}</h3>
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
            <h2 className="admin-section-title">{t('admin.stats.searchQuality')}</h2>
            <div className="admin-detail-card">
              <dl>
                <div className="admin-detail-row"><dt>{t('admin.stats.totalSearches')}</dt><dd>{searchStats.total_searches.toLocaleString()}</dd></div>
                <div className="admin-detail-row"><dt>{t('admin.stats.avgSimilarity')}</dt><dd>{searchStats.avg_similarity != null ? searchStats.avg_similarity.toFixed(4) : '—'}</dd></div>
                <div className="admin-detail-row"><dt>{t('admin.stats.avgDurationMs')}</dt><dd>{searchStats.avg_duration_ms != null ? `${Math.round(searchStats.avg_duration_ms)}ms` : '—'}</dd></div>
                <div className="admin-detail-row"><dt>{t('admin.stats.zeroResults')}</dt><dd style={{ color: searchStats.zero_result_count > 0 ? '#f59e0b' : undefined }}>{searchStats.zero_result_count}</dd></div>
              </dl>
              {searchStats.top_queries.length > 0 && (
                <div style={{ marginTop: 12 }}>
                  <h3 style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 8 }}>{t('admin.stats.topQueries')}</h3>
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
