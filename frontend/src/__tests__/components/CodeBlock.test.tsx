import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { CodeBlock } from '../../components/CodeBlock'

beforeEach(() => {
  Object.assign(navigator, {
    clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
  })
})

describe('CodeBlock', () => {
  it('renders language label', () => {
    render(<CodeBlock language="python">print("hi")</CodeBlock>)
    expect(screen.getByText('python')).toBeInTheDocument()
  })

  it('shows "text" when no language provided', () => {
    render(<CodeBlock language="">some code</CodeBlock>)
    expect(screen.getByText('text')).toBeInTheDocument()
  })

  it('renders filename when provided', () => {
    render(<CodeBlock language="python" filename="config.py">x = 1</CodeBlock>)
    expect(screen.getByText('config.py')).toBeInTheDocument()
  })

  it('copies code to clipboard on click', async () => {
    render(<CodeBlock language="js">const x = 1</CodeBlock>)

    await userEvent.click(screen.getByText('Copy'))
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('const x = 1')
    expect(screen.getByText('Copied')).toBeInTheDocument()
  })

  it('downloads code as file on click', async () => {
    const originalCreateElement = document.createElement.bind(document)
    const clickSpy = vi.fn()
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:test')
    const revokeObjectURLSpy = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})

    vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      const el = originalCreateElement(tag)
      if (tag === 'a') el.click = clickSpy
      return el
    })

    render(<CodeBlock language="python">print("hi")</CodeBlock>)

    await userEvent.click(screen.getByText('Download'))
    expect(clickSpy).toHaveBeenCalled()
    expect(revokeObjectURLSpy).toHaveBeenCalledWith('blob:test')

    vi.restoreAllMocks()
  })

  it('uses filename for download when provided', async () => {
    const originalCreateElement = document.createElement.bind(document)
    let downloadAttr = ''
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:test')
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})

    vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      const el = originalCreateElement(tag)
      if (tag === 'a') {
        el.click = vi.fn()
        const orig = Object.getOwnPropertyDescriptor(el, 'download') ||
          Object.getOwnPropertyDescriptor(HTMLAnchorElement.prototype, 'download')
        Object.defineProperty(el, 'download', {
          set(val: string) { downloadAttr = val; if (orig?.set) orig.set.call(el, val) },
          get() { return downloadAttr },
          configurable: true,
        })
      }
      return el
    })

    render(<CodeBlock language="proto" filename="service.proto">syntax = "proto3";</CodeBlock>)

    await userEvent.click(screen.getByText('Download'))
    expect(downloadAttr).toBe('service.proto')

    vi.restoreAllMocks()
  })
})
