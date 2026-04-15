import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ChatInput } from '../../components/ChatInput'

describe('ChatInput', () => {
  it('renders textarea with placeholder', () => {
    render(<ChatInput onSend={() => {}} onCancel={() => {}} status="idle" />)
    expect(screen.getByPlaceholderText(/Ask anything about your docs/)).toBeInTheDocument()
  })

  it('calls onSend with trimmed content on button click', async () => {
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} onCancel={() => {}} status="idle" />)

    const textarea = screen.getByPlaceholderText(/Ask anything about your docs/)
    await userEvent.type(textarea, '  Hello world  ')
    await userEvent.click(screen.getByTitle('Send message'))

    expect(onSend).toHaveBeenCalledWith('Hello world')
  })

  it('sends on Enter without Shift', async () => {
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} onCancel={() => {}} status="idle" />)

    const textarea = screen.getByPlaceholderText(/Ask anything about your docs/)
    await userEvent.type(textarea, 'test{enter}')

    expect(onSend).toHaveBeenCalledWith('test')
  })

  it('does not send on empty input', async () => {
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} onCancel={() => {}} status="idle" />)

    await userEvent.click(screen.getByTitle('Send message'))
    expect(onSend).not.toHaveBeenCalled()
  })

  it('shows stop button during streaming', () => {
    render(<ChatInput onSend={() => {}} onCancel={() => {}} status="streaming" />)
    expect(screen.getByTitle('Stop generating')).toBeInTheDocument()
  })

  it('shows cancel button during streaming', () => {
    render(<ChatInput onSend={() => {}} onCancel={() => {}} status="streaming" />)
    expect(screen.getByTitle('Stop generating')).toBeInTheDocument()
  })

  it('calls onCancel when cancel button clicked', async () => {
    const onCancel = vi.fn()
    render(<ChatInput onSend={() => {}} onCancel={onCancel} status="streaming" />)

    await userEvent.click(screen.getByTitle('Stop generating'))
    expect(onCancel).toHaveBeenCalledOnce()
  })
})
