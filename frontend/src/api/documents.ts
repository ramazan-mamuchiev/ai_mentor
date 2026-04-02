import { apiFetch } from './client'
import type {
  DocumentListItem,
  DocumentDebugInfo,
  DocumentDownload,
  DocumentMarkdownPreview,
  DocumentSearchKeysResponse,
  DocumentUsageStats,
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

export async function getDocumentUsageStats(id: number): Promise<DocumentUsageStats> {
  return apiFetch<DocumentUsageStats>(`/documents/${id}/usage-stats`)
}

export async function downloadDocument(id: number): Promise<DocumentDownload> {
  return apiFetch<DocumentDownload>(`/documents/${id}/download`)
}

export async function previewMarkdown(id: number): Promise<DocumentMarkdownPreview> {
  return apiFetch<DocumentMarkdownPreview>(`/documents/${id}/preview-markdown`)
}

export async function deleteDocument(id: number): Promise<void> {
  return apiFetch<void>(`/documents/${id}`, { method: 'DELETE' })
}

export async function reingestDocument(id: number, reindexOnly = false): Promise<{ document_id: number; status: string; task_id: string }> {
  const params = reindexOnly ? '?reindex_only=true' : ''
  return apiFetch(`/documents/${id}/reingest${params}`, { method: 'POST' })
}

export async function cancelDocument(id: number): Promise<void> {
  return apiFetch<void>(`/documents/${id}/cancel`, { method: 'POST' })
}

export interface UrlIngestRequest {
  url: string
  product_name: string
  firmware_version?: string
  manufacturer?: string
  max_pages?: number
  max_depth?: number
  confluence_username?: string
  confluence_password?: string
}

export interface UrlIngestResponse {
  status: string
  message: string
  url: string
  product_name: string
  task_id: string | null
  product_id: number | null
  document_id: number | null
}

export async function ingestUrl(data: UrlIngestRequest): Promise<UrlIngestResponse> {
  return apiFetch<UrlIngestResponse>('/documents/ingest-url', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export interface SiteIngestRequest {
  url: string
  product_name: string
  firmware_version?: string
  manufacturer?: string
  max_depth?: number
  max_pages?: number
  download_resources?: boolean
}

export async function ingestSite(data: SiteIngestRequest): Promise<UrlIngestResponse> {
  return apiFetch<UrlIngestResponse>('/documents/ingest-site', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export interface GitHubIngestRequest {
  url: string
  product_name: string
  firmware_version?: string
  manufacturer?: string
  branch?: string
}

export async function ingestGitHub(data: GitHubIngestRequest): Promise<UrlIngestResponse> {
  return apiFetch<UrlIngestResponse>('/documents/ingest-github', {
    method: 'POST',
    body: JSON.stringify(data),
  })
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

export async function getDocumentSearchKeys(documentId: number): Promise<DocumentSearchKeysResponse> {
  return apiFetch<DocumentSearchKeysResponse>(`/documents/${documentId}/search-keys`)
}
