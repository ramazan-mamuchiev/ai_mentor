import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth/AuthContext'
import { LandingPage } from './pages/LandingPage'
import { RegisterPage } from './pages/RegisterPage'
import { LoginPage } from './pages/LoginPage'
import { ChatApp } from './pages/ChatApp'
import { SharedView } from './pages/SharedView'
import { KBShell } from './pages/KBShell'
import { KBPage } from './pages/KBPage'
import { KBArticlePage } from './pages/KBArticlePage'
import type { ReactNode } from 'react'

const AdminApp = lazy(() => import('./pages/admin/AdminApp'))

function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="auth-loading" />
  if (!user) return <Navigate to="/login" replace />
  return <>{children}</>
}

function AdminRoute({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="auth-loading" />
  if (!user) return <Navigate to="/login" replace />
  if (!(user.permissions as any)?.features?.admin) return <Navigate to="/app" replace />
  return <>{children}</>
}

function GuestRoute({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="auth-loading" />
  if (user) return <Navigate to="/app" replace />
  return <>{children}</>
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/s/:token" element={<SharedView />} />
      <Route path="/register" element={<GuestRoute><RegisterPage /></GuestRoute>} />
      <Route path="/login" element={<GuestRoute><LoginPage /></GuestRoute>} />
      <Route path="/kb" element={<KBShell />}>
        <Route index element={<KBPage />} />
        <Route path=":slug" element={<KBArticlePage />} />
      </Route>
      <Route path="/app/admin/*" element={
        <AdminRoute>
          <Suspense fallback={<div className="auth-loading" />}>
            <AdminApp />
          </Suspense>
        </AdminRoute>
      } />
      <Route path="/app/*" element={<ProtectedRoute><ChatApp /></ProtectedRoute>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
  )
}
