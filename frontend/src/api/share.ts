import { apiFetch } from './client'
import type { SharedContentResponse, SharedLinkResponse } from '../types'

export async function shareSession(sessionId: number): Promise<SharedLinkResponse> {
  return apiFetch<SharedLinkResponse>(`/share/session/${sessionId}`, {
    method: 'POST',
    body: '{}',
  })
}

export async function shareMessage(messageId: number): Promise<SharedLinkResponse> {
  return apiFetch<SharedLinkResponse>(`/share/message/${messageId}`, {
    method: 'POST',
    body: '{}',
  })
}

export async function getSharedContent(token: string): Promise<SharedContentResponse> {
  return apiFetch<SharedContentResponse>(`/s/${token}`)
}

export async function deleteSharedLink(token: string): Promise<void> {
  return apiFetch<void>(`/share/${token}`, { method: 'DELETE' })
}

export async function listSharedLinks(sessionId?: number): Promise<SharedLinkResponse[]> {
  const params = sessionId != null ? `?session_id=${sessionId}` : ''
  return apiFetch<SharedLinkResponse[]>(`/share/links${params}`)
}
