import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createSession, listSessions, deleteSession, streamMessage } from '../../api/chat'

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('createSession', () => {
  it('sends POST with params and returns session', async () => {
    const session = { id: 1, title: 'Test' }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(session),
    }))

    const result = await createSession({ title: 'Test', device_filter: 'Cam' })
    expect(result).toEqual(session)
    expect(fetch).toHaveBeenCalledWith('/api/v1/chat/sessions', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ title: 'Test', device_filter: 'Cam' }),
    }))
  })
})

describe('listSessions', () => {
  it('returns array of sessions', async () => {
    const sessions = [{ id: 1 }, { id: 2 }]
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(sessions),
    }))

    const result = await listSessions()
    expect(result).toEqual(sessions)
  })
})

describe('deleteSession', () => {
  it('sends DELETE and returns undefined', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
    }))

    const result = await deleteSession(5)
    expect(result).toBeUndefined()
    expect(fetch).toHaveBeenCalledWith('/api/v1/chat/sessions/5', expect.objectContaining({
      method: 'DELETE',
    }))
  })
})

describe('streamMessage', () => {
  function makeSSEStream(events: string[]) {
    const text = events.map(e => `data: ${e}\n\n`).join('')
    const encoder = new TextEncoder()
    const chunks = [encoder.encode(text)]
    let index = 0
    return {
      getReader: () => ({
        read: () => {
          if (index < chunks.length) {
            return Promise.resolve({ done: false, value: chunks[index++] })
          }
          return Promise.resolve({ done: true, value: undefined })
        },
      }),
    }
  }

  it('yields parsed SSE events', async () => {
    const body = makeSSEStream([
      JSON.stringify({ type: 'sources', sources: [] }),
      JSON.stringify({ type: 'token', content: 'Hello' }),
      JSON.stringify({ type: 'done', message_id: 1, duration_ms: 500 }),
    ])

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      body,
    }))

    const events = []
    for await (const event of streamMessage(1, 'test')) {
      events.push(event)
    }

    expect(events).toHaveLength(3)
    expect(events[0]).toEqual({ type: 'sources', sources: [] })
    expect(events[1]).toEqual({ type: 'token', content: 'Hello' })
    expect(events[2]).toEqual({ type: 'done', message_id: 1, duration_ms: 500 })
  })

  it('throws on HTTP error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      text: () => Promise.resolve('Internal Server Error'),
    }))

    const gen = streamMessage(1, 'test')
    await expect(gen.next()).rejects.toThrow('API error 500')
  })

  it('throws when response has no body', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      body: null,
    }))

    const gen = streamMessage(1, 'test')
    await expect(gen.next()).rejects.toThrow('No response body')
  })

  it('skips malformed JSON in SSE', async () => {
    const body = makeSSEStream([
      'not-valid-json',
      JSON.stringify({ type: 'token', content: 'ok' }),
    ])

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      body,
    }))

    const events = []
    for await (const event of streamMessage(1, 'test')) {
      events.push(event)
    }

    expect(events).toHaveLength(1)
    expect(events[0]).toEqual({ type: 'token', content: 'ok' })
  })
})
