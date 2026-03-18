import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SessionList } from '../../components/SessionList'
import type { ChatSession } from '../../types'

const sessions: ChatSession[] = [
  { id: 1, title: 'Auth Chat', product_filter: null, version_filter: null, created_at: '', updated_at: '', message_count: 3, last_message_preview: null },
  { id: 2, title: null, product_filter: null, version_filter: null, created_at: '', updated_at: '', message_count: 1, last_message_preview: 'How to open door?' },
  { id: 3, title: null, product_filter: null, version_filter: null, created_at: '', updated_at: '', message_count: 0, last_message_preview: null },
]

describe('SessionList', () => {
  it('renders all sessions with correct titles', () => {
    render(<SessionList sessions={sessions} activeSessionId={null} onSelect={() => {}} onNew={() => {}} onDelete={() => {}} />)
    expect(screen.getByText('Auth Chat')).toBeInTheDocument()
    expect(screen.getByText('How to open door?')).toBeInTheDocument()
    const newChatElements = screen.getAllByText('New Chat')
    expect(newChatElements.length).toBe(2)
  })

  it('falls back to last_message_preview then New Chat', () => {
    render(<SessionList sessions={sessions} activeSessionId={null} onSelect={() => {}} onNew={() => {}} onDelete={() => {}} />)
    expect(screen.getByText('How to open door?')).toBeInTheDocument()
    const sessionTitles = document.querySelectorAll('.session-item-title')
    expect(sessionTitles[2].textContent).toBe('New Chat')
  })

  it('calls onSelect when session clicked', async () => {
    const onSelect = vi.fn()
    render(<SessionList sessions={sessions} activeSessionId={null} onSelect={onSelect} onNew={() => {}} onDelete={() => {}} />)

    await userEvent.click(screen.getByText('Auth Chat'))
    expect(onSelect).toHaveBeenCalledWith(1)
  })

  it('calls onNew when New Chat button clicked', async () => {
    const onNew = vi.fn()
    render(<SessionList sessions={[]} activeSessionId={null} onSelect={() => {}} onNew={onNew} onDelete={() => {}} />)

    const buttons = screen.getAllByText('New Chat')
    await userEvent.click(buttons[0])
    expect(onNew).toHaveBeenCalledOnce()
  })

  it('calls onDelete without triggering onSelect', async () => {
    const onSelect = vi.fn()
    const onDelete = vi.fn()
    render(<SessionList sessions={sessions} activeSessionId={null} onSelect={onSelect} onNew={() => {}} onDelete={onDelete} />)

    const deleteButtons = document.querySelectorAll('.session-delete-btn')
    await userEvent.click(deleteButtons[0])
    expect(onDelete).toHaveBeenCalledWith(1)
    expect(onSelect).not.toHaveBeenCalled()
  })

  it('marks active session with active class', () => {
    render(<SessionList sessions={sessions} activeSessionId={1} onSelect={() => {}} onNew={() => {}} onDelete={() => {}} />)
    const activeItem = document.querySelector('.session-item.active')
    expect(activeItem).toBeTruthy()
    expect(activeItem?.textContent).toContain('Auth Chat')
  })
})
