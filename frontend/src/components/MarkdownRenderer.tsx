import { useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { CodeBlock } from './CodeBlock'
import { fixBrokenTables } from '../utils/fixBrokenTables'

function stripCitations(md: string): string {
  let result = md
  result = result.replace(/\[[\d,\s]+\]\([^)]*\)/g, '')
  result = result.replace(/\[[\d,\s]+\](?!\()/g, '')
  result = result.replace(/ {2,}/g, ' ')
  result = result.replace(/ ([.,;:!?])/g, '$1')
  return result
}

interface Props {
  content: string
  isStreaming?: boolean
}

export function MarkdownRenderer({ content, isStreaming }: Props) {
  const processed = useMemo(() => stripCitations(fixBrokenTables(content)), [content])

  return (
    <div className={isStreaming ? 'streaming-content' : undefined}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code({ className, children, ...props }) {
            const match = /language-(\w+)/.exec(className || '')
            const isInline = !match && !className

            if (isInline) {
              return (
                <code
                  style={{
                    background: 'rgba(0,0,0,0.1)',
                    padding: '2px 6px',
                    borderRadius: '4px',
                    fontSize: '0.9em',
                    fontFamily: 'var(--font-mono)',
                  }}
                  {...props}
                >
                  {children}
                </code>
              )
            }

            let language = match?.[1] || ''
            let filename: string | undefined

            const metaMatch = /language-(\w+):(.+)/.exec(className || '')
            if (metaMatch) {
              language = metaMatch[1]
              filename = metaMatch[2]
            }

            return (
              <CodeBlock language={language} filename={filename}>
                {String(children).replace(/\n$/, '')}
              </CodeBlock>
            )
          },
          a({ href, children, ...props }) {
            return <a href={href} target="_blank" rel="noopener noreferrer" {...props}>{children}</a>
          },
        }}
      >
        {processed}
      </ReactMarkdown>
      {isStreaming && <span className="streaming-cursor" />}
    </div>
  )
}
