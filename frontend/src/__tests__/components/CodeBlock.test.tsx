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

  it('copies code to clipboard on click', async () => {
    render(<CodeBlock language="js">const x = 1</CodeBlock>)

    await userEvent.click(screen.getByText('Copy'))
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('const x = 1')
    expect(screen.getByText('Copied')).toBeInTheDocument()
  })
})
