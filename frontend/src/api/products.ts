import { apiFetch } from './client'
import type { ProductListItem, ProductDetail, ProductDebugInfo, ProductSearchKeysResponse, ProductUsageStats, SuggestionChip } from '../types'

export async function listProducts(): Promise<ProductListItem[]> {
  return apiFetch<ProductListItem[]>('/products')
}

export async function getProduct(productId: number): Promise<ProductDetail> {
  return apiFetch<ProductDetail>(`/products/${productId}`)
}

export async function getProductBySlug(slug: string): Promise<ProductDetail> {
  return apiFetch<ProductDetail>(`/products/by-slug/${encodeURIComponent(slug)}`)
}

export async function updateProduct(
  productId: number,
  data: { name?: string; manufacturer?: string; category?: string; version?: string; firmware_version_id?: number | null },
): Promise<ProductDetail> {
  return apiFetch<ProductDetail>(`/products/${productId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export interface DeleteProductResult {
  product_id: number
  task_id: string
  total_documents: number
}

export async function deleteProduct(productId: number): Promise<DeleteProductResult> {
  return apiFetch<DeleteProductResult>(`/products/${productId}`, { method: 'DELETE' })
}

export async function reingestProduct(productId: number): Promise<{ product_id: number; status: string; documents_queued: number }> {
  return apiFetch(`/products/${productId}/reingest`, { method: 'POST' })
}

export async function syncProduct(productId: number): Promise<{ product_id: number; status: string; documents_queued: number; placeholders_queued: number }> {
  return apiFetch(`/products/${productId}/sync`, { method: 'POST' })
}

export async function cancelProductIngestion(productId: number): Promise<void> {
  return apiFetch<void>(`/products/${productId}/cancel-ingestion`, { method: 'POST' })
}

export async function getProductDebug(productId: number): Promise<ProductDebugInfo> {
  return apiFetch<ProductDebugInfo>(`/products/${productId}/debug`)
}

export async function getProductUsageStats(productId: number): Promise<ProductUsageStats> {
  return apiFetch<ProductUsageStats>(`/products/${productId}/usage-stats`)
}

export async function getProductSearchKeys(productId: number): Promise<ProductSearchKeysResponse> {
  return apiFetch<ProductSearchKeysResponse>(`/products/${productId}/search-keys`)
}

export async function getSuggestions(): Promise<SuggestionChip[]> {
  return apiFetch<SuggestionChip[]>('/products/suggestions')
}

export interface ProductSuggestion {
  id: number
  name: string
  manufacturer: string
  firmware_versions: Array<{ id: number; version: string }>
}

export async function analyzeProductLifecycle(productId: number): Promise<{ product_id: number; message: string; tasks: Array<{ document_id: number; task_id: string }> }> {
  return apiFetch(`/products/${productId}/analyze-lifecycle`, { method: 'POST' })
}

export interface ProductLifecycle {
  product_id: number
  product_name: string
  document_lifecycles: Array<{ document_id: number; status: string; analysis_ms: number; created_at: string | null }>
  merged: null | {
    status: string
    phases: Array<{
      phase_name: string; step_order: number; action: string; api_call: string
      inputs: string[]; outputs: string[]; is_required: boolean; notes: string
    }>
    unique_patterns: Array<{ pattern: string; description: string; impact: string; code_hint: string }>
    dependency_chains: Array<{ from_action: string; to_action: string; data_flow: string; description: string }>
    data_models: Array<{
      model_name: string; direction: string; content_type?: string
      used_in?: string[]
      fields?: Array<{ name: string; type: string; constraints?: string; required?: boolean; description?: string; example_value?: string }>
    }>
    error_catalog: Array<{
      http_status: number; error_code?: string; meaning: string
      recovery_action: string; retry_after_seconds?: number
    }>
    prerequisites: Array<{ name: string; type: string; description: string; example_value?: string; how_to_obtain?: string }>
    data_access_patterns: Array<{ pattern_type: string; endpoint: string; mechanism: string; code_hint?: string }>
    endpoint_coverage: Array<{
      method: string; endpoint: string; completeness: number
      has_request_body_docs: boolean; has_response_docs: boolean
      has_error_docs: boolean; has_example: boolean
    }>
    code_skeleton: string
    validation_issues: Array<{ error: string }>
    validation_retries: number
    prompt_tokens: number; completion_tokens: number; analysis_ms: number; model: string
    created_at: string | null; updated_at: string | null
  }
  doc_issues: Array<{
    document_id: number; issue_type: string; severity: string; description: string
    affected_entity?: string; suggestion?: string
  }>
}

export async function getProductLifecycle(productId: number): Promise<ProductLifecycle> {
  return apiFetch<ProductLifecycle>(`/products/${productId}/lifecycle`)
}

export async function deleteProductLifecycle(productId: number): Promise<{ product_id: number; deleted_count: number }> {
  return apiFetch(`/products/${productId}/lifecycle`, { method: 'DELETE' })
}

export async function suggestProducts(q: string = '', limit: number = 20): Promise<ProductSuggestion[]> {
  const params = new URLSearchParams()
  if (q) params.set('q', q)
  params.set('limit', String(limit))
  return apiFetch<ProductSuggestion[]>(`/products/suggest?${params}`)
}
