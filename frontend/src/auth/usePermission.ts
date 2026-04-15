import { useAuth } from './AuthContext'

/**
 * Check if the current user has a specific feature permission.
 * Returns false if user is not authenticated or permission is not set.
 */
export function usePermission(key: string): boolean {
  const { user } = useAuth()
  if (!user?.permissions) return false
  const features = (user.permissions as any)?.features
  if (!features) return false
  return !!features[key]
}

/**
 * Get a numeric limit from permissions (null = unlimited).
 */
export function useLimit(key: string): number | null {
  const { user } = useAuth()
  if (!user?.permissions) return null
  const limits = (user.permissions as any)?.limits
  if (!limits) return null
  return limits[key] ?? null
}
