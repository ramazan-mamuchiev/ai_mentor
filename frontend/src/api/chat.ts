import { apiFetch } from './client'
import type { ChatSession, SessionDetail, SSEEvent } from '../types'

export async function createSession(params?: {
  title?: string
  product_id?: number
  product_filter?: string
  version_filter?: string
}): Promise<ChatSession> {
  return apiFetch<ChatSession>('/chat/sessions', {
    method: 'POST',
    body: JSON.stringify(params ?? {}),
  })
}

export async function listSessions(): Promise<ChatSession[]> {
  return apiFetch<ChatSession[]>('/chat/sessions')
}

export async function getSession(id: string): Promise<SessionDetail> {
  return apiFetch<SessionDetail>(`/chat/sessions/${id}`)
}

export async function deleteSession(id: string): Promise<void> {
  return apiFetch<void>(`/chat/sessions/${id}`, { method: 'DELETE' })
}

export async function updateSession(
  id: string,
  data: {
    product_id?: number | null
    product_filter?: string | null
    product_filter_source?: string | null
    version_filter?: string | null
  },
): Promise<ChatSession> {
  return apiFetch<ChatSession>(`/chat/sessions/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function submitFeedback(
  sessionId: string,
  messageId: number,
  feedback: 'up' | 'down',
  comment?: string,
): Promise<{ status: string; message_id: number; feedback: string }> {
  return apiFetch(`/chat/sessions/${sessionId}/messages/${messageId}/feedback`, {
    method: 'POST',
    body: JSON.stringify({ feedback, comment: comment || null }),
  })
}

export async function* streamMessage(
  sessionId: string,
  content: string,
  signal?: AbortSignal,
): AsyncGenerator<SSEEvent> {
  const res = await fetch(`/api/v1/chat/sessions/${sessionId}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
    signal,
  })

  if (!res.ok) {
    const body = await res.text()
    throw new Error(`API error ${res.status}: ${body}`)
  }

  const reader = res.body?.getReader()
  if (!reader) throw new Error('No response body')

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''

    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed.startsWith('data: ')) continue
      const json = trimmed.slice(6)
      try {
        yield JSON.parse(json) as SSEEvent
      } catch {
        // skip malformed events
      }
    }
  }
}
