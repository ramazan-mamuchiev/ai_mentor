export function fmtUsd(v: string | number | null | undefined): string {
  if (v == null) return '—'
  const n = parseFloat(String(v))
  return isNaN(n) ? String(v) : `$${n.toFixed(2)}`
}
