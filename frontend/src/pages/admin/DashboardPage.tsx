import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  getOverview, getUsageStats,
  type PlatformOverview, type DailyUsageStat,
} from '../../api/admin'

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

  if (loading) return <div className="admin-loading">Loading dashboard...</div>
  if (!overview) return <div className="admin-empty">Failed to load overview</div>

  return (
    <div>
      <div className="admin-page-header">
        <h1>Dashboard</h1>
        <p>Platform overview</p>
      </div>

      <div className="stats-grid">
        <StatCard label="Total Tenants" value={overview.total_tenants} sub={`${overview.active_tenants} active`} />
        <StatCard label="Documents" value={overview.total_documents} sub={`${overview.documents_indexed} indexed`} variant="accent" />
        <StatCard
          label="Pending / Error"
          value={overview.documents_pending}
          sub={`${overview.documents_error} errors`}
          variant={overview.documents_error > 0 ? 'danger' : 'warning'}
        />
        <StatCard label="Chat Sessions" value={overview.total_sessions} sub={`${overview.total_messages} messages`} />
        <StatCard label="Requests (30d)" value={overview.total_requests_30d.toLocaleString()} variant="accent" />
        <StatCard label="Tokens (30d)" value={overview.total_tokens_30d.toLocaleString()} />
        <StatCard label="Revenue (30d)" value={`$${overview.total_charge_usd_30d}`} variant="success" />
      </div>

      <MiniBarChart data={daily} label="Requests per day (30d)" />

      <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))' }}>
        <div
          className="stat-card"
          style={{ cursor: 'pointer' }}
          onClick={() => navigate('/app/admin/tenants')}
        >
          <span className="stat-card__label">Manage Tenants</span>
          <span className="stat-card__sub">View and edit all tenant accounts</span>
        </div>
        <div
          className="stat-card"
          style={{ cursor: 'pointer' }}
          onClick={() => navigate('/app/admin/documents')}
        >
          <span className="stat-card__label">Moderate Documents</span>
          <span className="stat-card__sub">Review and manage uploaded content</span>
        </div>
        <div
          className="stat-card"
          style={{ cursor: 'pointer' }}
          onClick={() => navigate('/app/admin/chats')}
        >
          <span className="stat-card__label">Chat Audit</span>
          <span className="stat-card__sub">Review chat sessions across tenants</span>
        </div>
      </div>
    </div>
  )
}
