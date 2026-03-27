import { Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom'
import {
  LayoutDashboard, Users, FileText, MessageSquare,
  ScrollText, BarChart3, ArrowLeft, Shield,
} from 'lucide-react'
import { DashboardPage } from './DashboardPage'
import { TenantsPage } from './TenantsPage'
import { TenantDetailPage } from './TenantDetailPage'
import { DocumentsAdminPage } from './DocumentsAdminPage'
import { ChatAuditPage } from './ChatAuditPage'
import { LogsPage } from './LogsPage'
import { StatsPage } from './StatsPage'

const NAV = [
  { path: '/app/admin', icon: LayoutDashboard, label: 'Dashboard', exact: true },
  { path: '/app/admin/tenants', icon: Users, label: 'Tenants', exact: false },
  { path: '/app/admin/documents', icon: FileText, label: 'Documents', exact: false },
  { path: '/app/admin/chats', icon: MessageSquare, label: 'Chat Audit', exact: false },
  { path: '/app/admin/logs', icon: ScrollText, label: 'Logs', exact: false },
  { path: '/app/admin/stats', icon: BarChart3, label: 'Stats', exact: false },
] as const

export default function AdminApp() {
  const navigate = useNavigate()
  const location = useLocation()

  return (
    <div className="admin-layout">
      <aside className="admin-sidebar">
        <div className="admin-sidebar-header">
          <h2><Shield size={16} /> Admin</h2>
          <button className="admin-sidebar-back" onClick={() => navigate('/app')}>
            <ArrowLeft size={14} /> Back to app
          </button>
        </div>
        <nav className="admin-nav">
          {NAV.map(item => {
            const Icon = item.icon
            const active = item.exact
              ? location.pathname === item.path || location.pathname === item.path + '/'
              : location.pathname.startsWith(item.path)
            return (
              <button
                key={item.path}
                className={`admin-nav-item${active ? ' admin-nav-item--active' : ''}`}
                onClick={() => navigate(item.path)}
              >
                <Icon size={16} />
                {item.label}
              </button>
            )
          })}
        </nav>
      </aside>
      <main className="admin-main">
        <Routes>
          <Route index element={<DashboardPage />} />
          <Route path="tenants" element={<TenantsPage />} />
          <Route path="tenants/:id" element={<TenantDetailPage />} />
          <Route path="documents" element={<DocumentsAdminPage />} />
          <Route path="chats" element={<ChatAuditPage />} />
          <Route path="chats/:id" element={<ChatAuditPage />} />
          <Route path="logs" element={<LogsPage />} />
          <Route path="stats" element={<StatsPage />} />
          <Route path="*" element={<Navigate to="/app/admin" replace />} />
        </Routes>
      </main>
    </div>
  )
}
