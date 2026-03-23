import { apiFetch } from './client'
import type {
  DocumentListItem,
  DocumentDebugInfo,
  DocumentDownload,
  ReindexJob,
  ReindexJobList,
  ReindexMode,
} from '../types'

export async function listDocuments(productId?: number): Promise<DocumentListItem[]> {
  const params = productId != null ? `?product_id=${productId}` : ''
  return apiFetch<DocumentListItem[]>(`/documents${params}`)
}

export async function updateDocument(
  id: number,
  data: { title?: string; product_id?: number; firmware_version_id?: number },
): Promise<void> {
  const params = new URLSearchParams()
  if (data.title != null) params.set('title', data.title)
  if (data.product_id != null) params.set('product_id', String(data.product_id))
  if (data.firmware_version_id != null) params.set('firmware_version_id', String(data.firmware_version_id))
  return apiFetch<void>(`/documents/${id}?${params.toString()}`, { method: 'PATCH' })
}

export async function getDocumentStatus(id: number): Promise<DocumentListItem> {
  return apiFetch<DocumentListItem>(`/documents/${id}/status`)
}

export async function getDocumentDebug(id: number): Promise<DocumentDebugInfo> {
  return apiFetch<DocumentDebugInfo>(`/documents/${id}/debug`)
}

export async function downloadDocument(id: number): Promise<DocumentDownload> {
  return apiFetch<DocumentDownload>(`/documents/${id}/download`)
}

export async function deleteDocument(id: number): Promise<void> {
  return apiFetch<void>(`/documents/${id}`, { method: 'DELETE' })
}

export async function reingestDocument(id: number): Promise<{ document_id: number; status: string; task_id: string }> {
  return apiFetch(`/documents/${id}/reingest`, { method: 'POST' })
}

export async function cancelDocument(id: number): Promise<void> {
  return apiFetch<void>(`/documents/${id}/cancel`, { method: 'POST' })
}

export async function listReindexJobs(): Promise<ReindexJobList> {
  return apiFetch<ReindexJobList>('/reindex/jobs')
}

export async function createReindexJob(
  mode: ReindexMode,
  productName?: string,
  formatFilter?: string,
): Promise<ReindexJob> {
  return apiFetch<ReindexJob>('/reindex/jobs', {
    method: 'POST',
    body: JSON.stringify({
      mode,
      product_name: productName,
      format_filter: formatFilter,
    }),
  })
}

export async function cancelReindexJob(id: number): Promise<ReindexJob> {
  return apiFetch<ReindexJob>(`/reindex/jobs/${id}/cancel`, { method: 'POST' })
}
