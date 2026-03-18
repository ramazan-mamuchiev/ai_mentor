import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ChatMessageComponent } from '../../components/ChatMessage'
import type { ChatMessage } from '../../types'

const userMsg: ChatMessage = {
  id: 1,
  session_id: 1,
  role: 'user',
  content: 'How to authenticate?',
  created_at: '2026-01-01T00:00:00Z',
}

const assistantMsg: ChatMessage = {
  id: 2,
  session_id: 1,
  role: 'assistant',
  content: 'Use **HMAC-SHA256** for authentication.',
  sources: [
    { doc_title: 'API Guide', heading_path: 'Auth', similarity: 0.9, content_preview: 'HMAC details...', device_name: 'Cam', firmware_version: '1.0' },
  ],
  duration_ms: 2500,
  created_at: '2026-01-01T00:00:01Z',
}

describe('ChatMessageComponent', () => {
  it('renders user message as plain text', () => {
    render(<ChatMessageComponent message={userMsg} />)
    expect(screen.getByText('How to authenticate?')).toBeInTheDocument()
  })

  it('renders assistant message with markdown', () => {
    render(<ChatMessageComponent message={assistantMsg} />)
    expect(screen.getByText('HMAC-SHA256')).toBeInTheDocument()
  })

  it('shows collapsed sources toggle', () => {
    render(<ChatMessageComponent message={assistantMsg} />)
    expect(screen.getByText('Sources (1)')).toBeInTheDocument()
    expect(screen.queryByText('API Guide')).not.toBeInTheDocument()
  })

  it('expands sources on toggle click', async () => {
    const user = (await import('@testing-library/user-event')).default
    render(<ChatMessageComponent message={assistantMsg} />)
    await user.setup().click(screen.getByText('Sources (1)'))
    expect(screen.getByText('API Guide')).toBeInTheDocument()
  })

  it('shows duration for non-streaming assistant', () => {
    render(<ChatMessageComponent message={assistantMsg} />)
    expect(screen.getByText('2.5s')).toBeInTheDocument()
  })

  it('hides duration when streaming', () => {
    render(
      <ChatMessageComponent
        message={{ ...assistantMsg, content: '' }}
        isStreaming
        streamingContent="partial..."
      />,
    )
    expect(screen.queryByText('2.5s')).not.toBeInTheDocument()
  })

  it('uses streamingContent when isStreaming', () => {
    render(
      <ChatMessageComponent
        message={{ ...assistantMsg, content: '' }}
        isStreaming
        streamingContent="Streaming text here"
      />,
    )
    expect(screen.getByText('Streaming text here')).toBeInTheDocument()
  })

  it('shows typing indicator when streaming with no content', () => {
    render(
      <ChatMessageComponent
        message={{ ...assistantMsg, content: '' }}
        isStreaming
        streamingContent=""
      />,
    )
    expect(screen.getByText(/Searching documentation/)).toBeInTheDocument()
  })

  it('does not show typing indicator when streaming has content', () => {
    render(
      <ChatMessageComponent
        message={{ ...assistantMsg, content: '' }}
        isStreaming
        streamingContent="Hello"
      />,
    )
    expect(screen.queryByText(/Searching documentation/)).not.toBeInTheDocument()
  })
})
