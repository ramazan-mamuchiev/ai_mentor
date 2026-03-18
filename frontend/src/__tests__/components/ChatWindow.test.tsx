import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ChatWindow } from '../../components/ChatWindow'
import type { ChatMessage } from '../../types'

const messages: ChatMessage[] = [
  { id: 1, session_id: 1, role: 'user', content: 'Hello', created_at: '' },
  { id: 2, session_id: 1, role: 'assistant', content: 'Hi there!', created_at: '' },
]

const scrollIntoViewMock = vi.fn()

beforeEach(() => {
  scrollIntoViewMock.mockClear()
  Element.prototype.scrollIntoView = scrollIntoViewMock
})

function renderChatWindow(overrides: Partial<Parameters<typeof ChatWindow>[0]> = {}) {
  const defaults = {
    messages: [] as ChatMessage[],
    streamingContent: '',
    streamingSources: [],
    status: 'idle' as const,
    sessionTitle: null,
    onSend: vi.fn(),
    onCancel: vi.fn(),
  }
  return render(<ChatWindow {...defaults} {...overrides} />)
}

describe('ChatWindow', () => {
  it('shows empty state when no messages', () => {
    renderChatWindow()
    expect(screen.getByText('IPCodex AI')).toBeInTheDocument()
    expect(screen.getByText(/Ask me anything/)).toBeInTheDocument()
  })

  it('renders messages when present', () => {
    renderChatWindow({ messages, sessionTitle: 'Test Chat' })
    expect(screen.getByText('Hello')).toBeInTheDocument()
    expect(screen.getByText('Hi there!')).toBeInTheDocument()
  })

  it('displays session title in header', () => {
    renderChatWindow({ messages, sessionTitle: 'My Session' })
    expect(screen.getByText('My Session')).toBeInTheDocument()
  })

  it('shows "New Chat" when no session title', () => {
    renderChatWindow()
    expect(screen.getByText('New Chat')).toBeInTheDocument()
  })

  it('renders streaming message during streaming', () => {
    renderChatWindow({
      messages: [{ id: 1, session_id: 1, role: 'user', content: 'test', created_at: '' }],
      streamingContent: 'Streaming...',
      status: 'streaming',
      sessionTitle: 'Chat',
    })
    expect(screen.getByText('Streaming...')).toBeInTheDocument()
  })
})

describe('ChatWindow smart auto-scroll', () => {
  function getContainer() {
    return document.querySelector('.messages-container') as HTMLDivElement
  }

  function simulateScrollPosition(el: HTMLElement, scrollTop: number, scrollHeight: number, clientHeight: number) {
    Object.defineProperty(el, 'scrollHeight', { value: scrollHeight, configurable: true })
    Object.defineProperty(el, 'scrollTop', { value: scrollTop, configurable: true })
    Object.defineProperty(el, 'clientHeight', { value: clientHeight, configurable: true })
  }

  it('auto-scrolls to bottom when user is near the bottom', () => {
    const { rerender } = renderChatWindow({
      messages: [{ id: 1, session_id: 1, role: 'user', content: 'q', created_at: '' }],
      streamingContent: 'tok1',
      status: 'streaming',
      sessionTitle: 'Chat',
    })

    scrollIntoViewMock.mockClear()

    const container = getContainer()
    simulateScrollPosition(container, 900, 1000, 100)
    fireEvent.scroll(container)

    rerender(
      <ChatWindow
        messages={[{ id: 1, session_id: 1, role: 'user', content: 'q', created_at: '' }]}
        streamingContent="tok1 tok2"
        streamingSources={[]}
        status="streaming"
        sessionTitle="Chat"
        onSend={() => {}}
        onCancel={() => {}}
      />,
    )

    expect(scrollIntoViewMock).toHaveBeenCalled()
  })

  it('does NOT auto-scroll when user scrolled up', () => {
    const { rerender } = renderChatWindow({
      messages: [{ id: 1, session_id: 1, role: 'user', content: 'q', created_at: '' }],
      streamingContent: 'tok1',
      status: 'streaming',
      sessionTitle: 'Chat',
    })

    const container = getContainer()
    simulateScrollPosition(container, 200, 1000, 100)
    fireEvent.scroll(container)

    scrollIntoViewMock.mockClear()

    rerender(
      <ChatWindow
        messages={[{ id: 1, session_id: 1, role: 'user', content: 'q', created_at: '' }]}
        streamingContent="tok1 tok2"
        streamingSources={[]}
        status="streaming"
        sessionTitle="Chat"
        onSend={() => {}}
        onCancel={() => {}}
      />,
    )

    expect(scrollIntoViewMock).not.toHaveBeenCalled()
  })

  it('re-enables auto-scroll when user scrolls back to bottom', () => {
    const { rerender } = renderChatWindow({
      messages: [{ id: 1, session_id: 1, role: 'user', content: 'q', created_at: '' }],
      streamingContent: 'tok1',
      status: 'streaming',
      sessionTitle: 'Chat',
    })

    const container = getContainer()

    simulateScrollPosition(container, 200, 1000, 100)
    fireEvent.scroll(container)

    simulateScrollPosition(container, 920, 1000, 100)
    fireEvent.scroll(container)

    scrollIntoViewMock.mockClear()

    rerender(
      <ChatWindow
        messages={[{ id: 1, session_id: 1, role: 'user', content: 'q', created_at: '' }]}
        streamingContent="tok1 tok2 tok3"
        streamingSources={[]}
        status="streaming"
        sessionTitle="Chat"
        onSend={() => {}}
        onCancel={() => {}}
      />,
    )

    expect(scrollIntoViewMock).toHaveBeenCalled()
  })

  it('re-enables auto-scroll when user sends a new message', async () => {
    const onSend = vi.fn()
    const user = userEvent.setup()

    const { rerender } = renderChatWindow({
      messages: [{ id: 1, session_id: 1, role: 'user', content: 'q', created_at: '' }],
      streamingContent: 'tok1',
      status: 'streaming',
      sessionTitle: 'Chat',
      onSend,
    })

    const container = getContainer()
    simulateScrollPosition(container, 200, 1000, 100)
    fireEvent.scroll(container)

    scrollIntoViewMock.mockClear()

    rerender(
      <ChatWindow
        messages={[
          { id: 1, session_id: 1, role: 'user', content: 'q', created_at: '' },
          { id: 2, session_id: 1, role: 'assistant', content: 'tok1 done', created_at: '' },
        ]}
        streamingContent=""
        streamingSources={[]}
        status="idle"
        sessionTitle="Chat"
        onSend={onSend}
        onCancel={() => {}}
      />,
    )

    const input = screen.getByPlaceholderText(/Ask/i)
    await user.type(input, 'follow up{Enter}')

    rerender(
      <ChatWindow
        messages={[
          { id: 1, session_id: 1, role: 'user', content: 'q', created_at: '' },
          { id: 2, session_id: 1, role: 'assistant', content: 'tok1 done', created_at: '' },
          { id: 3, session_id: 1, role: 'user', content: 'follow up', created_at: '' },
        ]}
        streamingContent="new response"
        streamingSources={[]}
        status="streaming"
        sessionTitle="Chat"
        onSend={onSend}
        onCancel={() => {}}
      />,
    )

    expect(scrollIntoViewMock).toHaveBeenCalled()
  })
})
