import { useEffect, useState } from 'react'
import { BarChart3, Key, Zap, Coins, Activity } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { getUsageSummary, type UsageSummaryResponse } from '../auth/api'

export function AnalyticsPage() {
  const { t } = useTranslation()
  const [data, setData] = useState<UsageSummaryResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    getUsageSummary(30)
      .then(setData)
      .catch(() => setError(true))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="analytics-page">
        <h1 className="analytics-title"><BarChart3 size={20} /> {t('analytics.title')}</h1>
        <p className="analytics-loading">{t('settings.loading')}</p>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="analytics-page">
        <h1 className="analytics-title"><BarChart3 size={20} /> {t('analytics.title')}</h1>
        <p className="analytics-error">{t('analytics.noData')}</p>
      </div>
    )
  }

  const formatNum = (n: number) => n.toLocaleString()

  return (
    <div className="analytics-page">
      <h1 className="analytics-title"><BarChart3 size={20} /> {t('analytics.title')}</h1>
      <p className="analytics-subtitle">{t('analytics.description')}</p>

      <div className="analytics-kpi-row">
        <div className="kpi-card">
          <Activity size={20} className="kpi-icon" />
          <span className="kpi-value">{formatNum(data.total_requests)}</span>
          <span className="kpi-label">{t('analytics.kpiRequests')}</span>
        </div>
        <div className="kpi-card">
          <Zap size={20} className="kpi-icon" />
          <span className="kpi-value">{formatNum(data.total_tokens)}</span>
          <span className="kpi-label">{t('analytics.kpiTokens')}</span>
        </div>
        <div className="kpi-card">
          <Coins size={20} className="kpi-icon" />
          <span className="kpi-value">${data.total_charge_usd}</span>
          <span className="kpi-label">{t('analytics.kpiCharge')}</span>
        </div>
        <div className="kpi-card">
          <Key size={20} className="kpi-icon" />
          <span className="kpi-value">{data.active_keys}</span>
          <span className="kpi-label">{t('analytics.kpiActiveKeys')}</span>
        </div>
      </div>

      {data.daily.length > 0 && (
        <section className="analytics-section">
          <h2 className="analytics-section-title">{t('analytics.chartTitle')}</h2>
          <div className="analytics-chart">
            <ResponsiveContainer width="100%" height={240}>
              <AreaChart data={data.daily}>
                <XAxis dataKey="date" tick={{ fontSize: 11 }} tickFormatter={d => d.slice(5)} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Area type="monotone" dataKey="requests" stroke="var(--accent)" fill="var(--accent)" fillOpacity={0.15} name={t('analytics.kpiRequests')} />
                <Area type="monotone" dataKey="tokens" stroke="var(--text-secondary)" fill="var(--text-secondary)" fillOpacity={0.08} name={t('analytics.kpiTokens')} yAxisId={0} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </section>
      )}

      {data.by_action.length > 0 && (
        <section className="analytics-section">
          <h2 className="analytics-section-title">{t('analytics.byAction')}</h2>
          <div className="analytics-table-wrap">
            <table className="analytics-table">
              <thead>
                <tr>
                  <th>{t('analytics.action')}</th>
                  <th>{t('analytics.kpiRequests')}</th>
                  <th>{t('analytics.kpiTokens')}</th>
                </tr>
              </thead>
              <tbody>
                {data.by_action.map(a => (
                  <tr key={a.action}>
                    <td><code>{a.action}</code></td>
                    <td>{formatNum(a.count)}</td>
                    <td>{formatNum(a.tokens)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {data.by_key.length > 0 && (
        <section className="analytics-section">
          <h2 className="analytics-section-title">{t('analytics.byKey')}</h2>
          <div className="analytics-table-wrap">
            <table className="analytics-table">
              <thead>
                <tr>
                  <th>{t('settings.keyName')}</th>
                  <th>{t('settings.keyPrefix')}</th>
                  <th>{t('analytics.kpiRequests')}</th>
                  <th>{t('analytics.kpiTokens')}</th>
                  <th>{t('analytics.kpiCharge')}</th>
                </tr>
              </thead>
              <tbody>
                {data.by_key.map(k => (
                  <tr key={k.key_id}>
                    <td>{k.key_name || '—'}</td>
                    <td><code>{k.key_prefix}</code></td>
                    <td>{formatNum(k.total_requests)}</td>
                    <td>{formatNum(k.total_tokens)}</td>
                    <td>${k.total_charge_usd}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {data.total_requests === 0 && (
        <div className="analytics-empty">
          <BarChart3 size={48} className="stub-icon" />
          <p>{t('analytics.noData')}</p>
        </div>
      )}
    </div>
  )
}
