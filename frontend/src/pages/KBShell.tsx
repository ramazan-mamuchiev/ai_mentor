import { Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { useTheme } from '../hooks/useTheme'
import { Layout } from '../components/Layout'
import { PublicKBLayout } from '../components/PublicKBLayout'

export function KBShell() {
  const { user, loading } = useAuth()
  const { theme, toggle: toggleTheme } = useTheme()
  const navigate = useNavigate()

  if (loading) return <div className="auth-loading" />

  if (user) {
    return (
      <Layout
        sessions={[]}
        activeSessionId={null}
        theme={theme}
        onSelectSession={() => {}}
        onNewSession={() => navigate('/app')}
        onDeleteSession={() => {}}
        onToggleTheme={toggleTheme}
        onLogoClick={() => navigate('/app')}
      >
        <Outlet />
      </Layout>
    )
  }

  return (
    <PublicKBLayout>
      <Outlet />
    </PublicKBLayout>
  )
}
