import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { getMe, login as apiLogin, logout as apiLogout, register as apiRegister, refreshToken, type MeResponse } from './api'

interface AuthState {
  user: MeResponse | null
  loading: boolean
  firstApiKey: string | null
}

interface AuthContextType extends AuthState {
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<string>
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

  const refreshUser = useCallback(async () => {
    const user = await getMe()
    setState(prev => ({ ...prev, user, loading: false }))
  }, [])

  useEffect(() => {
    refreshUser().catch(() =>
      refreshToken()
        .then(() => refreshUser())
        .catch(() => setState(prev => ({ ...prev, user: null, loading: false })))
    )
  }, [refreshUser])

  const login = useCallback(async (email: string, password: string) => {
    await apiLogin({ email, password })
    await refreshUser()
  }, [refreshUser])

  const register = useCallback(async (email: string, password: string): Promise<string> => {
    const result = await apiRegister({ email, password })
    setState(prev => ({ ...prev, firstApiKey: result.api_key }))
    await refreshUser()
    return result.api_key
  }, [refreshUser])

  const logout = useCallback(async () => {
    await apiLogout()
    setState({ user: null, loading: false, firstApiKey: null })
  }, [])

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
