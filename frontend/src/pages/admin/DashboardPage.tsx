import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { LayoutDashboard } from 'lucide-react'
import {
  getOverview, getUsageStats,
  type PlatformOverview, type DailyUsageStat,
} from '../../api/admin'
import { fmtUsd } from '../../utils/format'

function StatCard({ label, value, sub, variant }: {
  label: string
  value: string | number
  sub?: string
  variant?: 'accent' | 'warning' | 'danger' | 'success'
}) {
  return (
    <div className={`stat-card${variant ? ` stat-card--${variant}` : ''}`}>
      <span className="stat-card__label">{label}</span>
      <span className="stat-card__value">{value}</span>
      {sub && <span className="stat-card__sub">{sub}</span>}
    </div>
  )
}

function MiniBarChart({ data, label }: { data: DailyUsageStat[]; label: string }) {
  const max = Math.max(...data.map(d => d.requests), 1)
  return (
    <div className="admin-chart">
      <h3>{label}</h3>
      <div className="admin-chart-bars">
        {data.map((d, i) => (
          <div
            key={i}
            className="admin-chart-bar"
            style={{ height: `${(d.requests / max) * 100}%` }}
            title={`${d.date}: ${d.requests} req, ${d.tokens} tokens`}
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

export function DashboardPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [overview, setOverview] = useState<PlatformOverview | null>(null)
  const [daily, setDaily] = useState<DailyUsageStat[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([getOverview(), getUsageStats(30)])
      .then(([ov, us]) => {
        setOverview(ov)
        setDaily(us.daily)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="admin-loading">{t('admin.common.loading')}</div>
  if (!overview) return <div className="admin-empty">{t('admin.dashboard.loadFailed')}</div>

  return (
    <div>
      <div className="admin-page-header">
        <h1><LayoutDashboard size={20} /> {t('admin.dashboard.title')}</h1>
        <p>{t('admin.dashboard.subtitle')}</p>
      </div>

      <div className="stats-grid">
        <StatCard
          label={t('admin.dashboard.totalTenants')}
          value={overview.total_tenants}
          sub={t('admin.dashboard.activeSub', { count: overview.active_tenants })}
        />
        <StatCard
          label={t('admin.dashboard.documents')}
          value={overview.total_documents}
          sub={t('admin.dashboard.indexedSub', { count: overview.documents_indexed })}
          variant="accent"
        />
        <StatCard
          label={t('admin.dashboard.pendingError')}
          value={overview.documents_pending}
          sub={t('admin.dashboard.errorsSub', { count: overview.documents_error })}
          variant={overview.documents_error > 0 ? 'danger' : 'warning'}
        />
        <StatCard
          label={t('admin.dashboard.chatSessions')}
          value={overview.total_sessions}
          sub={t('admin.dashboard.messagesSub', { count: overview.total_messages })}
        />
        <StatCard label={t('admin.dashboard.requests30d')} value={overview.total_requests_30d.toLocaleString()} variant="accent" />
        <StatCard label={t('admin.dashboard.tokens30d')} value={overview.total_tokens_30d.toLocaleString()} />
        <StatCard label={t('admin.dashboard.revenue30d')} value={fmtUsd(overview.total_charge_usd_30d)} variant="success" />
      </div>

      <div className="stats-grid">
        <StatCard
          label={t('admin.dashboard.chatRequests30d')}
          value={overview.chat_requests_30d.toLocaleString()}
          sub={`${overview.chat_tokens_30d.toLocaleString()} tok · ${fmtUsd(overview.chat_charge_usd_30d)}`}
        />
        <StatCard
          label={t('admin.dashboard.mcpRequests30d')}
          value={overview.mcp_requests_30d.toLocaleString()}
          sub={`${overview.mcp_tokens_30d.toLocaleString()} tok · ${fmtUsd(overview.mcp_charge_usd_30d)}`}
          variant="accent"
        />
      </div>

      <MiniBarChart data={daily} label={t('admin.dashboard.requestsPerDay')} />

      <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))' }}>
        <div
          className="stat-card"
          style={{ cursor: 'pointer' }}
          onClick={() => navigate('/app/admin/tenants')}
        >
          <span className="stat-card__label">{t('admin.dashboard.manageTenants')}</span>
          <span className="stat-card__sub">{t('admin.dashboard.manageTenantsDesc')}</span>
        </div>
        <div
          className="stat-card"
          style={{ cursor: 'pointer' }}
          onClick={() => navigate('/app/admin/documents')}
        >
          <span className="stat-card__label">{t('admin.dashboard.moderateDocs')}</span>
          <span className="stat-card__sub">{t('admin.dashboard.moderateDocsDesc')}</span>
        </div>
        <div
          className="stat-card"
          style={{ cursor: 'pointer' }}
          onClick={() => navigate('/app/admin/chats')}
        >
          <span className="stat-card__label">{t('admin.dashboard.chatAudit')}</span>
          <span className="stat-card__sub">{t('admin.dashboard.chatAuditDesc')}</span>
        </div>
        <div
          className="stat-card"
          style={{ cursor: 'pointer' }}
          onClick={() => navigate('/app/admin/mcp')}
        >
          <span className="stat-card__label">{t('admin.dashboard.mcpAudit')}</span>
          <span className="stat-card__sub">{t('admin.dashboard.mcpAuditDesc')}</span>
        </div>
      </div>
    </div>
  )
}
