import { Routes, Route, Navigate } from 'react-router-dom'
import { Layout } from '../../components/Layout'
import { useTheme } from '../../hooks/useTheme'
import { DashboardPage } from './DashboardPage'
import { TenantsPage } from './TenantsPage'
import { TenantDetailPage } from './TenantDetailPage'
import { DocumentsAdminPage } from './DocumentsAdminPage'
import { ChatAuditPage } from './ChatAuditPage'
import { LogsPage } from './LogsPage'
import { StatsPage } from './StatsPage'
import { RolesPage } from './RolesPage'
import { RoleDetailPage } from './RoleDetailPage'
import { PromptsPage } from './PromptsPage'
import { PromptEditorPage } from './PromptEditorPage'

export default function AdminApp() {
  const { theme, toggle: toggleTheme } = useTheme()

  return (
    <Layout
      sessions={[]}
      activeSessionId={null}
      theme={theme}
      onSelectSession={() => {}}
      onNewSession={() => {}}
      onDeleteSession={() => {}}
      onToggleTheme={toggleTheme}
    >
      <div className="admin-main">
        <Routes>
          <Route index element={<DashboardPage />} />
          <Route path="tenants" element={<TenantsPage />} />
          <Route path="tenants/:id" element={<TenantDetailPage />} />
          <Route path="documents" element={<DocumentsAdminPage />} />
          <Route path="chats" element={<ChatAuditPage />} />
          <Route path="chats/:id" element={<ChatAuditPage />} />
          <Route path="roles" element={<RolesPage />} />
          <Route path="roles/:id" element={<RoleDetailPage />} />
          <Route path="prompts" element={<PromptsPage />} />
          <Route path="prompts/:id" element={<PromptEditorPage />} />
          <Route path="logs" element={<LogsPage />} />
          <Route path="stats" element={<StatsPage />} />
          <Route path="*" element={<Navigate to="/app/admin" replace />} />
        </Routes>
      </div>
    </Layout>
  )
}
