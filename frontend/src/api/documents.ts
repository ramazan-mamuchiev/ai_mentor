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
  http_username?: string
  http_password?: string
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

export async function analyzeDocumentLifecycle(documentId: number): Promise<{ document_id: number; task_id: string; message: string; previous_status: string }> {
  return apiFetch(`/documents/${documentId}/analyze-lifecycle`, { method: 'POST' })
}

export interface DocumentLifecycle {
  document_id: number
  status: string
  phases?: Array<{
    phase_name: string; step_order: number; action: string; api_call: string
    http_method?: string; content_type?: string
    inputs: string[]; outputs: string[]; is_required: boolean; notes: string
    request_example?: string; response_example?: string
  }>
  unique_patterns?: Array<{ pattern: string; description: string; impact: string; code_hint: string }>
  dependency_chains?: Array<{ from_action: string; to_action: string; data_flow: string; description: string }>
  code_skeleton?: string
  data_models?: Array<{
    model_name: string; used_in: string[]; direction: string; content_type?: string
    fields: Array<{
      name: string; type: string; required: boolean; description: string
      constraints?: string; example_value?: string
    }>
  }>
  error_catalog?: Array<{
    http_status: number; error_code?: string; meaning: string
    phase?: string; recovery_action: string; retry_after_seconds?: number | null
  }>
  prerequisites?: Array<{
    name: string; type: string; description: string
    example_value?: string; how_to_obtain?: string
  }>
  data_access_patterns?: Array<{
    pattern_type: string; endpoint: string; mechanism: string; code_hint?: string
  }>
  endpoint_coverage?: Array<{
    endpoint: string; method: string
    has_request_body_docs: boolean; has_response_docs: boolean
    has_error_docs: boolean; has_example: boolean
    completeness: number; missing: string[]
  }>
  integration_data_flows?: {
    components?: Array<{ id: string; name: string; type: string; description: string }>
    flows?: Array<{ from: string; to: string; label: string; protocol: string; data_type: string; direction: string }>
    diagram_mermaid?: string
  }
  validation_issues?: Array<{ error: string }>
  validation_retries?: number
  prompt_tokens?: number
  completion_tokens?: number
  analysis_ms?: number
  model?: string
  error_message?: string | null
  created_at?: string | null
  updated_at?: string | null
  doc_issues?: Array<{
    issue_type: string; severity: string; description: string
    affected_entity?: string; suggestion?: string
  }>
}

export async function getDocumentLifecycle(documentId: number): Promise<DocumentLifecycle> {
  return apiFetch<DocumentLifecycle>(`/documents/${documentId}/lifecycle`)
}

export async function deleteDocumentLifecycle(documentId: number): Promise<{ document_id: number; deleted: boolean }> {
  return apiFetch(`/documents/${documentId}/lifecycle`, { method: 'DELETE' })
}
