import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useChat } from '../../hooks/useChat'

vi.mock('../../api/chat', () => ({
  streamMessage: vi.fn(),
}))

import { streamMessage } from '../../api/chat'

const mockStreamMessage = vi.mocked(streamMessage)

beforeEach(() => {
  vi.restoreAllMocks()
})

async function* fakeStream(events: Array<{ type: string;[k: string]: unknown }>) {
  for (const event of events) {
    yield event
  }
}

describe('useChat', () => {
  it('starts with idle status and empty messages', () => {
    const { result } = renderHook(() => useChat())
    expect(result.current.status).toBe('idle')
    expect(result.current.messages).toEqual([])
    expect(result.current.streamingContent).toBe('')
  })

  it('sendMessage adds user message and processes stream', async () => {
    mockStreamMessage.mockReturnValue(fakeStream([
      { type: 'sources', sources: [{ doc_title: 'Doc', heading_path: 'Auth', similarity: 0.9, content_preview: '...', product_name: '', firmware_version: '' }] },
      { type: 'token', content: 'Hello' },
      { type: 'token', content: ' world' },
      { type: 'done', message_id: 42, duration_ms: 1500 },
    ]) as any)

    const { result } = renderHook(() => useChat())

    await act(async () => {
      await result.current.sendMessage(1, 'How to auth?')
    })

    expect(result.current.messages).toHaveLength(2)
    expect(result.current.messages[0].role).toBe('user')
    expect(result.current.messages[0].content).toBe('How to auth?')
    expect(result.current.messages[1].role).toBe('assistant')
    expect(result.current.messages[1].content).toBe('Hello world')
    expect(result.current.messages[1].sources).toHaveLength(1)
    expect(result.current.messages[1].duration_ms).toBe(1500)
    expect(result.current.status).toBe('idle')
    expect(result.current.streamingContent).toBe('')
  })

  it('handles error events from stream', async () => {
    mockStreamMessage.mockReturnValue(fakeStream([
      { type: 'sources', sources: [] },
      { type: 'error', content: 'Ollama down' },
    ]) as any)

    const { result } = renderHook(() => useChat())

    await act(async () => {
      await result.current.sendMessage(1, 'test')
    })

    expect(result.current.status).toBe('error')
    expect(result.current.messages).toHaveLength(1)
  })

  it('handles stream exceptions gracefully', async () => {
    mockStreamMessage.mockImplementation(async function* () {
      throw new Error('Network error')
    } as any)

    const { result } = renderHook(() => useChat())

    await act(async () => {
      await result.current.sendMessage(1, 'test')
    })

    expect(result.current.status).toBe('error')
  })

  it('cancel sets status to idle', async () => {
    let resolve: () => void
    const pending = new Promise<void>(r => { resolve = r })

    mockStreamMessage.mockImplementation(async function* () {
      await pending
      yield { type: 'done', message_id: 1, duration_ms: 0 }
    } as any)

    const { result } = renderHook(() => useChat())

    act(() => {
      result.current.sendMessage(1, 'test')
    })

    act(() => {
      result.current.cancel()
    })

    expect(result.current.status).toBe('idle')
    resolve!()
  })

  it('reset clears all state including messages and streaming content', async () => {
    mockStreamMessage.mockReturnValue(fakeStream([
      { type: 'sources', sources: [{ doc_title: 'Doc', heading_path: 'h', similarity: 0.9, content_preview: '...', product_name: '', firmware_version: '' }] },
      { type: 'token', content: 'Hello' },
      { type: 'done', message_id: 10, duration_ms: 100 },
    ]) as any)

    const { result } = renderHook(() => useChat())

    await act(async () => {
      await result.current.sendMessage(1, 'question')
    })

    expect(result.current.messages).toHaveLength(2)
    expect(result.current.status).toBe('idle')

    act(() => {
      result.current.reset()
    })

    expect(result.current.messages).toEqual([])
    expect(result.current.streamingContent).toBe('')
    expect(result.current.streamingSources).toEqual([])
    expect(result.current.status).toBe('idle')
  })

  it('reset aborts an in-flight stream', async () => {
    let resolve: () => void
    const pending = new Promise<void>(r => { resolve = r })

    mockStreamMessage.mockImplementation(async function* () {
      yield { type: 'token', content: 'partial' }
      await pending
      yield { type: 'done', message_id: 1, duration_ms: 0 }
    } as any)

    const { result } = renderHook(() => useChat())

    act(() => {
      result.current.sendMessage(1, 'test')
    })

    act(() => {
      result.current.reset()
    })

    expect(result.current.messages).toEqual([])
    expect(result.current.streamingContent).toBe('')
    expect(result.current.streamingSources).toEqual([])
    expect(result.current.status).toBe('idle')
    resolve!()
  })
})
