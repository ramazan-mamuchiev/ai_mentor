import { apiFetch } from './client'
import type { SharedContentResponse, SharedDebugContentResponse, SharedLinkResponse } from '../types'

export async function shareSession(sessionId: string): Promise<SharedLinkResponse> {
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

export async function shareDebugMessage(messageId: number): Promise<SharedLinkResponse> {
  return apiFetch<SharedLinkResponse>(`/share/debug/message/${messageId}`, {
    method: 'POST',
    body: '{}',
  })
}

export async function shareDebugDocument(documentId: number): Promise<SharedLinkResponse> {
  return apiFetch<SharedLinkResponse>(`/share/debug/document/${documentId}`, {
    method: 'POST',
    body: '{}',
  })
}

export async function shareDebugProduct(productId: number): Promise<SharedLinkResponse> {
  return apiFetch<SharedLinkResponse>(`/share/debug/product/${productId}`, {
    method: 'POST',
    body: '{}',
  })
}

export async function shareLifecycle(productId: number): Promise<SharedLinkResponse> {
  return apiFetch<SharedLinkResponse>(`/share/lifecycle/${productId}`, {
    method: 'POST',
    body: '{}',
  })
}

export async function getSharedContent(token: string): Promise<SharedContentResponse | SharedDebugContentResponse> {
  return apiFetch<SharedContentResponse | SharedDebugContentResponse>(`/s/${token}`)
}

export async function deleteSharedLink(token: string): Promise<void> {
  return apiFetch<void>(`/share/${token}`, { method: 'DELETE' })
}

export async function listSharedLinks(sessionId?: string): Promise<SharedLinkResponse[]> {
  const params = sessionId != null ? `?session_uuid=${sessionId}` : ''
  return apiFetch<SharedLinkResponse[]>(`/share/links${params}`)
}
