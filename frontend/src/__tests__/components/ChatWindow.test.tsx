import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ChatWindow } from '../../components/ChatWindow'
import type { ChatMessage } from '../../types'

const messages: ChatMessage[] = [
  { id: 1, session_id: 1, role: 'user', content: 'Hello', created_at: '' },
  { id: 2, session_id: 1, role: 'assistant', content: 'Hi there!', created_at: '' },
]

beforeEach(() => {
  vi.restoreAllMocks()
})

function renderChatWindow(overrides: Partial<Parameters<typeof ChatWindow>[0]> = {}) {
  const defaults = {
    messages: [] as ChatMessage[],
    streamingContent: '',
    streamingSources: [],
    status: 'idle' as const,
    onSend: vi.fn(),
    onCancel: vi.fn(),
  }
  return render(<ChatWindow {...defaults} {...overrides} />)
}

describe('ChatWindow', () => {
  it('shows empty state when no messages', () => {
    renderChatWindow()
    expect(screen.getByText('Lexiro')).toBeInTheDocument()
    expect(screen.getByText(/Ask, don't search/)).toBeInTheDocument()
  })

  it('renders messages when present', () => {
    renderChatWindow({ messages })
    expect(screen.getByText('Hello')).toBeInTheDocument()
    expect(screen.getByText('Hi there!')).toBeInTheDocument()
  })

  it('shows branded empty state with badge and slogan', () => {
    renderChatWindow()
    expect(screen.getByText('AI Integration Platform')).toBeInTheDocument()
    expect(screen.getByText('Lexiro')).toBeInTheDocument()
  })

  it('renders streaming message during streaming', () => {
    renderChatWindow({
      messages: [{ id: 1, session_id: 1, role: 'user', content: 'test', created_at: '' }],
      streamingContent: 'Streaming...',
      status: 'streaming',
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
    Object.defineProperty(el, 'scrollTop', { value: scrollTop, writable: true, configurable: true })
    Object.defineProperty(el, 'clientHeight', { value: clientHeight, configurable: true })
  }

  function simulateUserScroll(el: HTMLElement, scrollTop: number, scrollHeight: number, clientHeight: number) {
    simulateScrollPosition(el, scrollTop, scrollHeight, clientHeight)
    fireEvent.wheel(el, { deltaY: scrollTop < scrollHeight - clientHeight ? -1 : 1 })
    fireEvent.scroll(el)
  }

  it('auto-scrolls to bottom when user is near the bottom', () => {
    const { rerender } = renderChatWindow({
      messages: [{ id: 1, session_id: 1, role: 'user', content: 'q', created_at: '' }],
      streamingContent: 'tok1',
      status: 'streaming',
    })

    const container = getContainer()
    simulateUserScroll(container, 900, 1000, 100)

    const scrollTopSpy = vi.spyOn(container, 'scrollTop', 'set')

    rerender(
      <ChatWindow
        messages={[{ id: 1, session_id: 1, role: 'user', content: 'q', created_at: '' }]}
        streamingContent="tok1 tok2"
        streamingSources={[]}
        status="streaming"
        onSend={() => {}}
        onCancel={() => {}}
      />,
    )

    expect(scrollTopSpy).toHaveBeenCalled()
  })

  it('does NOT auto-scroll when user scrolled up', async () => {
    vi.useFakeTimers()
    const { rerender } = renderChatWindow({
      messages: [{ id: 1, session_id: 1, role: 'user', content: 'q', created_at: '' }],
      streamingContent: 'tok1',
      status: 'streaming',
    })

    await vi.runAllTimersAsync()

    const container = getContainer()
    simulateUserScroll(container, 200, 1000, 100)

    const scrollTopSpy = vi.spyOn(container, 'scrollTop', 'set')

    rerender(
      <ChatWindow
        messages={[{ id: 1, session_id: 1, role: 'user', content: 'q', created_at: '' }]}
        streamingContent="tok1 tok2"
        streamingSources={[]}
        status="streaming"
        onSend={() => {}}
        onCancel={() => {}}
      />,
    )

    expect(scrollTopSpy).not.toHaveBeenCalled()
    vi.useRealTimers()
  })

  it('re-enables auto-scroll when user scrolls back to bottom', () => {
    const { rerender } = renderChatWindow({
      messages: [{ id: 1, session_id: 1, role: 'user', content: 'q', created_at: '' }],
      streamingContent: 'tok1',
      status: 'streaming',
    })

    const container = getContainer()

    simulateUserScroll(container, 200, 1000, 100)
    simulateUserScroll(container, 920, 1000, 100)

    const scrollTopSpy = vi.spyOn(container, 'scrollTop', 'set')

    rerender(
      <ChatWindow
        messages={[{ id: 1, session_id: 1, role: 'user', content: 'q', created_at: '' }]}
        streamingContent="tok1 tok2 tok3"
        streamingSources={[]}
        status="streaming"
        onSend={() => {}}
        onCancel={() => {}}
      />,
    )

    expect(scrollTopSpy).toHaveBeenCalled()
  })

  it('re-enables auto-scroll when user sends a new message', async () => {
    const onSend = vi.fn()
    const user = userEvent.setup()

    const { rerender } = renderChatWindow({
      messages: [{ id: 1, session_id: 1, role: 'user', content: 'q', created_at: '' }],
      streamingContent: 'tok1',
      status: 'streaming',
      onSend,
    })

    const container = getContainer()
    simulateUserScroll(container, 200, 1000, 100)

    rerender(
      <ChatWindow
        messages={[
          { id: 1, session_id: 1, role: 'user', content: 'q', created_at: '' },
          { id: 2, session_id: 1, role: 'assistant', content: 'tok1 done', created_at: '' },
        ]}
        streamingContent=""
        streamingSources={[]}
        status="idle"
        onSend={onSend}
        onCancel={() => {}}
      />,
    )

    const input = screen.getByPlaceholderText(/Ask anything about your docs/i)
    await user.type(input, 'follow up{Enter}')

    const scrollTopSpy = vi.spyOn(container, 'scrollTop', 'set')

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
        onSend={onSend}
        onCancel={() => {}}
      />,
    )

    expect(scrollTopSpy).toHaveBeenCalled()
  })
})
