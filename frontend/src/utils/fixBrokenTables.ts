/**
 * Pre-processes markdown to fix tables that LLMs sometimes generate
 * without the required GFM separator row (|---|---|).
 *
 * Also collapses blank lines between consecutive pipe-rows so that
 * react-markdown / remark-gfm can parse them as a single table.
 */
export function fixBrokenTables(md: string): string {
  const lines = md.split('\n')
  const out: string[] = []

  for (let i = 0; i < lines.length; i++) {
    const cur = lines[i]
    const curTrimmed = cur.trim()

    // Skip blank lines that sit between two pipe-rows (LLM artifact).
    // Check last *emitted* line rather than lines[i-1] so consecutive blanks are all removed.
    if (
      curTrimmed === '' &&
      out.length > 0 &&
      isPipeRow(out[out.length - 1]) &&
      peekNextNonBlank(lines, i + 1) !== null &&
      isPipeRow(peekNextNonBlank(lines, i + 1)!)
    ) {
      continue
    }

    out.push(cur)

    // If current line looks like a table header and the next non-blank
    // line is a data row (not a separator), inject a separator.
    if (isPipeRow(curTrimmed)) {
      const next = peekNextNonBlank(lines, i + 1)
      if (next !== null && isPipeRow(next) && !isSeparatorRow(next)) {
        const prev = out.length >= 2 ? out[out.length - 2]?.trim() : ''
        if (!isPipeRow(prev)) {
          const cols = countColumns(curTrimmed)
          out.push('|' + ' --- |'.repeat(cols))
        }
      }
    }
  }

  return out.join('\n')
}

function isPipeRow(line: string | undefined): boolean {
  if (!line) return false
  const t = line.trim()
  return t.includes('|') && !t.startsWith('```')
}

function isSeparatorRow(line: string): boolean {
  return /^\|[\s:|-]+\|$/.test(line.trim()) && line.includes('-')
}

function countColumns(row: string): number {
  const stripped = row.trim().replace(/^\|/, '').replace(/\|$/, '')
  return stripped.split('|').length
}

function peekNextNonBlank(lines: string[], from: number): string | null {
  for (let j = from; j < lines.length; j++) {
    if (lines[j].trim() !== '') return lines[j].trim()
  }
  return null
}
