import { describe, it, expect, vi, beforeEach } from 'vitest'
import { apiFetch } from '../../api/client'

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('apiFetch', () => {
  it('returns JSON on successful response', async () => {
    const data = { id: 1, title: 'Test' }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(data),
    }))

    const result = await apiFetch('/chat/sessions')
    expect(result).toEqual(data)
    expect(fetch).toHaveBeenCalledWith('/api/v1/chat/sessions', expect.objectContaining({
      headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
    }))
  })

  it('throws on HTTP error with status and body', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      text: () => Promise.resolve('Not Found'),
    }))

    await expect(apiFetch('/missing')).rejects.toThrow('API error 404: Not Found')
  })

  it('returns undefined for 204 No Content', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
    }))

    const result = await apiFetch('/chat/sessions/1', { method: 'DELETE' })
    expect(result).toBeUndefined()
  })

  it('passes custom headers alongside defaults', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({}),
    }))

    await apiFetch('/test', { headers: { 'X-Custom': 'value' } })
    const callArgs = (fetch as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(callArgs[0]).toBe('/api/v1/test')
    expect(callArgs[1].headers['X-Custom']).toBe('value')
  })
})
