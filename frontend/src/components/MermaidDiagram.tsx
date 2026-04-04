import { useEffect, useRef, useState } from 'react'
import mermaid from 'mermaid'

mermaid.initialize({
  startOnLoad: false,
  theme: 'default',
  securityLevel: 'loose',
  flowchart: { curve: 'basis', htmlLabels: true },
})

interface Props {
  chart: string
  className?: string
}

let counter = 0

export function MermaidDiagram({ chart, className }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [svg, setSvg] = useState<string>('')
  const [error, setError] = useState<string>('')

  useEffect(() => {
    if (!chart.trim()) return
    const id = `mermaid-${++counter}`

    let cancelled = false
    mermaid.render(id, chart).then(
      ({ svg: rendered }) => { if (!cancelled) setSvg(rendered) },
      (err) => { if (!cancelled) setError(String(err)) },
    )
    return () => { cancelled = true }
  }, [chart])

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
