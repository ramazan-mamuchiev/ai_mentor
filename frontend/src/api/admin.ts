const BASE = '/api/v1/admin'

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

// --- Tenants ---

export interface TenantListItem {
  id: string
  email: string
  name: string | null
  slug: string
  tier: string
  role: string
  is_active: boolean
  email_verified: boolean
  created_at: string
  updated_at: string
  documents_count: number
  sessions_count: number
}

export interface TenantDetail extends TenantListItem {
  api_keys_count: number
  total_tokens: number
  total_requests: number
  total_charge_usd: string
}

export interface TenantListResponse {
  items: TenantListItem[]
  total: number
  page: number
  page_size: number
}

export async function listTenants(params: {
  page?: number
  page_size?: number
  search?: string
  role?: string
  tier?: string
  is_active?: boolean
} = {}): Promise<TenantListResponse> {
  const sp = new URLSearchParams()
  if (params.page) sp.set('page', String(params.page))
  if (params.page_size) sp.set('page_size', String(params.page_size))
  if (params.search) sp.set('search', params.search)
  if (params.role) sp.set('role', params.role)
  if (params.tier) sp.set('tier', params.tier)
  if (params.is_active !== undefined) sp.set('is_active', String(params.is_active))
  const res = await fetch(`${BASE}/tenants?${sp}`, { credentials: 'include' })
  return handleResponse(res)
}

export async function getTenant(id: string): Promise<TenantDetail> {
  const res = await fetch(`${BASE}/tenants/${id}`, { credentials: 'include' })
  return handleResponse(res)
}

export async function patchTenant(id: string, data: {
  role?: string
  tier?: string
  is_active?: boolean
}): Promise<TenantDetail> {
  const res = await fetch(`${BASE}/tenants/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    credentials: 'include',
  })
  return handleResponse(res)
}

export async function deleteTenant(id: string): Promise<void> {
  const res = await fetch(`${BASE}/tenants/${id}`, {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `HTTP ${res.status}`)
  }
}


// --- Documents ---

export interface AdminDocumentItem {
  id: number
  tenant_id: string | null
  tenant_email: string | null
  product_name: string | null
  manufacturer: string | null
  title: string
  original_filename: string
  format: string
  status: string
  file_size_bytes: number
  total_chunks: number
  error_message: string | null
  uploaded_at: string
  indexed_at: string | null
}

export interface AdminDocumentDetail extends AdminDocumentItem {
  s3_key: string
  source_hash: string
  embedding_model: string | null
  embedding_dims: number | null
  ingest_duration_ms: number | null
  total_tokens: number
  rag_hit_count: number
  rag_avg_similarity: number | null
}

export interface AdminDocumentListResponse {
  items: AdminDocumentItem[]
  total: number
  page: number
  page_size: number
}

export async function listDocumentsAdmin(params: {
  page?: number
  page_size?: number
  status?: string
  tenant_id?: string
  search?: string
} = {}): Promise<AdminDocumentListResponse> {
  const sp = new URLSearchParams()
  if (params.page) sp.set('page', String(params.page))
  if (params.page_size) sp.set('page_size', String(params.page_size))
  if (params.status) sp.set('status', params.status)
  if (params.tenant_id) sp.set('tenant_id', params.tenant_id)
  if (params.search) sp.set('search', params.search)
  const res = await fetch(`${BASE}/documents?${sp}`, { credentials: 'include' })
  return handleResponse(res)
}

export async function getDocumentAdmin(id: number): Promise<AdminDocumentDetail> {
  const res = await fetch(`${BASE}/documents/${id}`, { credentials: 'include' })
  return handleResponse(res)
}

export async function patchDocumentAdmin(id: number, data: { status?: string }): Promise<AdminDocumentDetail> {
  const res = await fetch(`${BASE}/documents/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    credentials: 'include',
  })
  return handleResponse(res)
}

export async function deleteDocumentAdmin(id: number): Promise<void> {
  const res = await fetch(`${BASE}/documents/${id}`, {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `HTTP ${res.status}`)
  }
}


// --- Chat Audit ---

export interface AdminChatSessionItem {
  id: number
  tenant_id: string | null
  tenant_email: string | null
  title: string | null
  product_filter: string | null
  messages_count: number
  created_at: string
  updated_at: string
}

export interface AdminChatMessage {
  id: number
  role: string
  content: string
  sources: Record<string, unknown> | null
  duration_ms: number | null
  feedback: string | null
  created_at: string
}

export interface AdminChatSessionDetail extends AdminChatSessionItem {
  messages: AdminChatMessage[]
}

export interface AdminChatSessionListResponse {
  items: AdminChatSessionItem[]
  total: number
  page: number
  page_size: number
}

export interface AdminChatMessageSearchItem {
  message_id: number
  session_id: number
  role: string
  content: string
  tenant_email: string | null
  created_at: string
}

export async function listChatSessionsAdmin(params: {
  page?: number
  page_size?: number
  tenant_id?: string
  search?: string
} = {}): Promise<AdminChatSessionListResponse> {
  const sp = new URLSearchParams()
  if (params.page) sp.set('page', String(params.page))
  if (params.page_size) sp.set('page_size', String(params.page_size))
  if (params.tenant_id) sp.set('tenant_id', params.tenant_id)
  if (params.search) sp.set('search', params.search)
  const res = await fetch(`${BASE}/chat/sessions?${sp}`, { credentials: 'include' })
  return handleResponse(res)
}

export async function getChatSessionAdmin(id: number): Promise<AdminChatSessionDetail> {
  const res = await fetch(`${BASE}/chat/sessions/${id}`, { credentials: 'include' })
  return handleResponse(res)
}

export async function searchMessagesAdmin(query: string, limit = 50): Promise<{
  items: AdminChatMessageSearchItem[]
  total: number
}> {
  const sp = new URLSearchParams({ query, limit: String(limit) })
  const res = await fetch(`${BASE}/chat/messages?${sp}`, { credentials: 'include' })
  return handleResponse(res)
}


// --- Stats ---

export interface PlatformOverview {
  total_tenants: number
  active_tenants: number
  total_documents: number
  documents_indexed: number
  documents_pending: number
  documents_error: number
  total_sessions: number
  total_messages: number
  total_tokens_30d: number
  total_requests_30d: number
  total_charge_usd_30d: string
}

export interface DailyUsageStat {
  date: string
  requests: number
  tokens: number
  charge_usd: string
}

export interface ModelUsageStat {
  model: string
  provider: string
  request_count: number
  total_tokens: number
  avg_total_ms: number
}

export interface IngestionStat {
  total_ingested: number
  avg_duration_ms: number | null
  total_chunks: number
  pending_count: number
  error_count: number
  top_errors: Array<{ message: string; count: number }>
}

export interface SearchStat {
  total_searches: number
  avg_similarity: number | null
  avg_duration_ms: number | null
  top_queries: Array<{ query: string; count: number }>
  zero_result_count: number
}

export async function getOverview(): Promise<PlatformOverview> {
  const res = await fetch(`${BASE}/stats/overview`, { credentials: 'include' })
  return handleResponse(res)
}

export async function getUsageStats(days = 30): Promise<{ daily: DailyUsageStat[] }> {
  const res = await fetch(`${BASE}/stats/usage?days=${days}`, { credentials: 'include' })
  return handleResponse(res)
}

export async function getModelStats(days = 30): Promise<ModelUsageStat[]> {
  const res = await fetch(`${BASE}/stats/models?days=${days}`, { credentials: 'include' })
  return handleResponse(res)
}

export async function getIngestionStats(): Promise<IngestionStat> {
  const res = await fetch(`${BASE}/stats/ingestion`, { credentials: 'include' })
  return handleResponse(res)
}

export async function getSearchStats(days = 30): Promise<SearchStat> {
  const res = await fetch(`${BASE}/stats/search?days=${days}`, { credentials: 'include' })
  return handleResponse(res)
}


// --- Logs ---

export interface LogEntry {
  timestamp: string
  level: string
  message: string
  service: string
  extra: Record<string, string>
}

export async function getLogs(params: {
  service?: string
  level?: string
  search?: string
  start?: string
  end?: string
  limit?: number
} = {}): Promise<{ entries: LogEntry[]; total: number }> {
  const sp = new URLSearchParams()
  if (params.service) sp.set('service', params.service)
  if (params.level) sp.set('level', params.level)
  if (params.search) sp.set('search', params.search)
  if (params.start) sp.set('start', params.start)
  if (params.end) sp.set('end', params.end)
  if (params.limit) sp.set('limit', String(params.limit))
  const res = await fetch(`${BASE}/logs?${sp}`, { credentials: 'include' })
  return handleResponse(res)
}
