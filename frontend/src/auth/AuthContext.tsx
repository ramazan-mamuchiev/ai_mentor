import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { getMe, login as apiLogin, logout as apiLogout, register as apiRegister, refreshToken, type MeResponse } from './api'

const REFRESH_BUFFER_SEC = 120

interface AuthState {
  user: MeResponse | null
  loading: boolean
  firstApiKey: string | null
}

interface AuthContextType extends AuthState {
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, name?: string) => Promise<string>
  logout: () => Promise<void>
  refreshUser: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    user: null,
    loading: true,
    firstApiKey: null,
  })
  const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const scheduleRefresh = useCallback((expiresIn: number) => {
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current)
    const delay = Math.max((expiresIn - REFRESH_BUFFER_SEC) * 1000, 10_000)
    refreshTimerRef.current = setTimeout(() => {
      refreshToken()
        .then(res => scheduleRefresh(res.expires_in))
        .catch(() => {})
    }, delay)
  }, [])

  const clearRefreshTimer = useCallback(() => {
    if (refreshTimerRef.current) {
      clearTimeout(refreshTimerRef.current)
      refreshTimerRef.current = null
    }
  }, [])

  const refreshUser = useCallback(async () => {
    const user = await getMe()
    setState(prev => ({ ...prev, user, loading: false }))
  }, [])

  useEffect(() => {
    refreshToken()
      .then(res => {
        scheduleRefresh(res.expires_in)
        return refreshUser()
      })
      .catch(() => setState(prev => ({ ...prev, user: null, loading: false })))
    return clearRefreshTimer
  }, [refreshUser, scheduleRefresh, clearRefreshTimer])

  const login = useCallback(async (email: string, password: string) => {
    const res = await apiLogin({ email, password })
    scheduleRefresh(res.expires_in)
    await refreshUser()
  }, [refreshUser, scheduleRefresh])

  const register = useCallback(async (email: string, password: string, name?: string): Promise<string> => {
    const result = await apiRegister({ email, password, name })
    setState(prev => ({ ...prev, firstApiKey: result.api_key }))
    await refreshUser()
    return result.api_key
  }, [refreshUser])

  const logout = useCallback(async () => {
    clearRefreshTimer()
    await apiLogout()
    setState({ user: null, loading: false, firstApiKey: null })
  }, [clearRefreshTimer])

  const value = useMemo(
    () => ({ ...state, login, register, logout, refreshUser }),
    [state, login, register, logout, refreshUser],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
