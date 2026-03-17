import type { SourceInfo } from '../types'

interface Props {
  source: SourceInfo
}

export function SourceCard({ source }: Props) {
  return (
    <div className="source-card">
      <div className="source-card-title">{source.doc_title}</div>
      <div className="source-card-path">{source.heading_path}</div>
      <div className="source-card-score">
        {source.device_name && `${source.device_name} · `}
        {(source.similarity * 100).toFixed(1)}% match
      </div>
    </div>
  )
}
