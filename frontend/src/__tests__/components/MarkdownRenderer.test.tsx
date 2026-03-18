import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MarkdownRenderer } from '../../components/MarkdownRenderer'

describe('MarkdownRenderer', () => {
  it('renders plain text', () => {
    render(<MarkdownRenderer content="Hello world" />)
    expect(screen.getByText('Hello world')).toBeInTheDocument()
  })

  it('renders bold text', () => {
    render(<MarkdownRenderer content="This is **bold**" />)
    expect(screen.getByText('bold')).toBeInTheDocument()
  })

  it('renders inline code', () => {
    render(<MarkdownRenderer content="Use `fetch()` to call API" />)
    const codeEl = screen.getByText('fetch()')
    expect(codeEl.tagName).toBe('CODE')
  })

  it('renders code blocks with language', () => {
    const content = '```python\nprint("hi")\n```'
    render(<MarkdownRenderer content={content} />)
    expect(screen.getByText('python')).toBeInTheDocument()
  })
})
