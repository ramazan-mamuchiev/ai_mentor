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

  it('renders GFM table as HTML table', () => {
    const content = '| Name | Type |\n|------|------|\n| id | string |\n| count | int32 |'
    const { container } = render(<MarkdownRenderer content={content} />)
    const table = container.querySelector('table')
    expect(table).not.toBeNull()
    const ths = container.querySelectorAll('th')
    expect(ths.length).toBe(2)
    expect(ths[0].textContent).toBe('Name')
    expect(ths[1].textContent).toBe('Type')
    const tds = container.querySelectorAll('td')
    expect(tds.length).toBe(4)
    expect(tds[0].textContent).toBe('id')
  })

  it('renders protobuf code block with syntax highlighting', () => {
    const content = '```protobuf\nservice Foo {\n  rpc Bar(Req) returns (Res);\n}\n```'
    render(<MarkdownRenderer content={content} />)
    expect(screen.getByText('protobuf')).toBeInTheDocument()
  })

  it('renders inline code inside GFM table cells', () => {
    const content = '| Field | Type |\n|-------|------|\n| `user_id` | `int32` |'
    const { container } = render(<MarkdownRenderer content={content} />)
    const codes = container.querySelectorAll('td code')
    expect(codes.length).toBe(2)
    expect(codes[0].textContent).toBe('user_id')
    expect(codes[1].textContent).toBe('int32')
  })

  it('renders broken table (no separator row) as HTML table via fixBrokenTables', () => {
    const content = '| Параметр | Описание |\n| id | Идентификатор карты |\n| name | Название |'
    const { container } = render(<MarkdownRenderer content={content} />)
    const table = container.querySelector('table')
    expect(table).not.toBeNull()
    const ths = container.querySelectorAll('th')
    expect(ths.length).toBe(2)
    expect(ths[0].textContent).toBe('Параметр')
    const tds = container.querySelectorAll('td')
    expect(tds.length).toBe(4)
    expect(tds[0].textContent).toBe('id')
  })

  it('renders broken table with blank lines between rows as HTML table', () => {
    const content = '| Name | Type |\n| --- | --- |\n\n| id | string |'
    const { container } = render(<MarkdownRenderer content={content} />)
    const table = container.querySelector('table')
    expect(table).not.toBeNull()
    const tds = container.querySelectorAll('td')
    expect(tds.length).toBe(2)
    expect(tds[0].textContent).toBe('id')
  })

  it('shows blinking cursor when isStreaming is true', () => {
    const { container } = render(<MarkdownRenderer content="Hello" isStreaming={true} />)
    const cursor = container.querySelector('.streaming-cursor')
    expect(cursor).not.toBeNull()
    expect(container.querySelector('.streaming-content')).not.toBeNull()
  })

  it('does not show cursor when isStreaming is false', () => {
    const { container } = render(<MarkdownRenderer content="Hello" isStreaming={false} />)
    expect(container.querySelector('.streaming-cursor')).toBeNull()
    expect(container.querySelector('.streaming-content')).toBeNull()
  })
})
