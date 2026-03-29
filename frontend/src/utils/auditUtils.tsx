export const TIME_RANGES = [
  { value: '', label: 'All' },
  { value: '24h', label: '24h' },
  { value: '7d', label: '7d' },
  { value: '30d', label: '30d' },
  { value: '90d', label: '90d' },
] as const

export function timeRangeToISO(range: string): { start?: string; end?: string } {
  if (!range) return {}
  const now = Date.now()
  const units: Record<string, number> = { m: 60_000, h: 3_600_000, d: 86_400_000 }
  const match = range.match(/^(\d+)([mhd])$/)
  if (!match) return {}
  const ms = parseInt(match[1]) * units[match[2]]
  return { start: new Date(now - ms).toISOString(), end: new Date(now).toISOString() }
}

export function fmtTs(iso: string): string {
  const d = new Date(iso)
  const dd = String(d.getDate()).padStart(2, '0')
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const hh = String(d.getHours()).padStart(2, '0')
  const mi = String(d.getMinutes()).padStart(2, '0')
  const ss = String(d.getSeconds()).padStart(2, '0')
  return `${dd}.${mm} ${hh}:${mi}:${ss}`
}

export function fmtTsShort(iso: string): string {
  const d = new Date(iso)
  const dd = String(d.getDate()).padStart(2, '0')
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const hh = String(d.getHours()).padStart(2, '0')
  const mi = String(d.getMinutes()).padStart(2, '0')
  return `${dd}.${mm} ${hh}:${mi}`
}

export function fmtMs(v: number | null | undefined): string {
  return v != null ? `${Math.round(v)}ms` : '—'
}

export function fmtDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

export function fmtUsd(v: string | number): string {
  return `$${parseFloat(String(v)).toFixed(6)}`
}

export function downloadBlob(content: string, filename: string, mime: string): void {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

export function exportItemsJSON<T>(items: T[]): string {
  return JSON.stringify(items, null, 2)
}

export function exportItemsCSV<T extends Record<string, unknown>>(items: T[], columns: string[]): string {
  const esc = (v: unknown) => `"${String(v ?? '').replace(/"/g, '""')}"`
  const header = columns.join(',')
  const rows = items.map(item => columns.map(c => esc(item[c])).join(','))
  return [header, ...rows].join('\n')
}

export function highlightSearch(text: string, query: string): React.ReactNode {
  if (!query || query.length < 2) return text
  const idx = text.toLowerCase().indexOf(query.toLowerCase())
  if (idx === -1) return text
  return (
    <>
      {text.slice(0, idx)}
      <mark className="log-highlight">{text.slice(idx, idx + query.length)}</mark>
      {text.slice(idx + query.length)}
    </>
  )
}
