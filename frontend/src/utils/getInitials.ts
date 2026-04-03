export function getInitials(email: string, name?: string | null): string {
  if (name) {
    const parts = name.trim().split(/\s+/)
    if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase()
    return name.slice(0, 2).toUpperCase()
  }
  const local = email.split('@')[0]
  const dotParts = local.split('.')
  if (dotParts.length >= 2) return (dotParts[0][0] + dotParts[1][0]).toUpperCase()
  return local.slice(0, 2).toUpperCase()
}
