import ReactMarkdown from 'react-markdown'
import { CodeBlock } from './CodeBlock'

interface Props {
  content: string
}

export function MarkdownRenderer({ content }: Props) {
  return (
    <ReactMarkdown
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

          return (
            <CodeBlock language={match?.[1] || ''}>
              {String(children).replace(/\n$/, '')}
            </CodeBlock>
          )
        },
      }}
    >
      {content}
    </ReactMarkdown>
  )
}
