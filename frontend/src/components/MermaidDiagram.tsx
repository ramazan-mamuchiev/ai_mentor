import { useEffect, useRef, useState, useMemo } from 'react'
import mermaid from 'mermaid'

mermaid.initialize({
  startOnLoad: false,
  theme: 'default',
  securityLevel: 'loose',
  flowchart: { curve: 'basis', htmlLabels: true },
})

function sanitizeMermaid(src: string): string {
  return src
    .replace(/(-->|===|~~~|-\.->?)\|([^|]+)\|/g, (_m, arrow, label) =>
      `${arrow}|${label.replace(/[(){}]/g, '')}|`)
    .replace(/\[([^\]]+)\]/g, (_m, label) =>
      `[${label.replace(/[(){}]/g, '')}]`)
}

interface Props {
  chart: string
  className?: string
}

let counter = 0

export function MermaidDiagram({ chart, className }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [svg, setSvg] = useState<string>('')
  const [error, setError] = useState<string>('')
  const safeChart = useMemo(() => sanitizeMermaid(chart), [chart])

  useEffect(() => {
    if (!safeChart.trim()) return
    const id = `mermaid-${++counter}`

    let cancelled = false
    mermaid.render(id, safeChart).then(
      ({ svg: rendered }) => { if (!cancelled) setSvg(rendered) },
      (err) => { if (!cancelled) setError(String(err)) },
    )
    return () => { cancelled = true }
  }, [safeChart])

  if (error) {
    return <pre className="lc-mermaid-error">{error}</pre>
  }

  if (!svg) {
    return <div className={`lc-mermaid-placeholder ${className ?? ''}`}>Loading diagram…</div>
  }

  return (
    <div
      ref={containerRef}
      className={`lc-mermaid ${className ?? ''}`}
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  )
}
