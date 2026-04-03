export function getInitials(email: string, name?: string | null): string {
  if (name) {
    const spaceParts = name.trim().split(/\s+/)
    if (spaceParts.length >= 2) return (spaceParts[0][0] + spaceParts[1][0]).toUpperCase()
    const dotParts = name.trim().split('.')
    if (dotParts.length >= 2) return (dotParts[0][0] + dotParts[1][0]).toUpperCase()
    return name.slice(0, 2).toUpperCase()
  }
  const local = email.split('@')[0]
  const dotParts = local.split('.')
  if (dotParts.length >= 2) return (dotParts[0][0] + dotParts[1][0]).toUpperCase()
  return local.slice(0, 2).toUpperCase()
}
