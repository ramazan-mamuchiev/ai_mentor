const BASE = '/api/v1/admin'

async function handleResponse<T>(res: Response): Promise<T> {
  if (res.status === 401) {
    window.location.href = '/login'
    throw new Error('Session expired')
  }
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
  firmware_version: string | null
  title: string
  original_filename: string
  format: string
  status: string
  file_size_bytes: number
  total_chunks: number
  search_keys_count: number
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
  id: string
  tenant_id: string | null
  tenant_email: string | null
  title: string | null
  product_filter: string | null
  messages_count: number
  total_tokens: number
  total_duration_ms: number
  created_at: string
  updated_at: string
}

export interface AdminChatMessageSource {
  doc_title?: string
  heading_path?: string
  similarity?: number
  content_preview?: string
  product_name?: string
  document_id?: number | null
}

export interface AdminChatMessage {
  id: number
  role: string
  content: string
  sources: AdminChatMessageSource[] | null
  duration_ms: number | null
  feedback: string | null
  created_at: string
  debug: Record<string, unknown> | null
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
  session_id: string
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
  created_after?: string
  created_before?: string
} = {}): Promise<AdminChatSessionListResponse> {
  const sp = new URLSearchParams()
  if (params.page) sp.set('page', String(params.page))
  if (params.page_size) sp.set('page_size', String(params.page_size))
  if (params.tenant_id) sp.set('tenant_id', params.tenant_id)
  if (params.search) sp.set('search', params.search)
  if (params.created_after) sp.set('created_after', params.created_after)
  if (params.created_before) sp.set('created_before', params.created_before)
  const res = await fetch(`${BASE}/chat/sessions?${sp}`, { credentials: 'include' })
  return handleResponse(res)
}

export async function getChatSessionAdmin(id: string): Promise<AdminChatSessionDetail> {
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
  total_chunks: number
  total_api_keys: number
  total_shared_links: number
  total_prompts: number
  customized_prompts: number
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

// --- Extended Stats ---

export interface FeedbackStat {
  total_messages: number
  rated_count: number
  positive: number
  negative: number
  positive_rate: number | null
}

export interface QueryTypeStat {
  query_type: string
  count: number
  pct: number
}

export interface ResponseTimeStat {
  avg_total_ms: number | null
  avg_rag_ms: number | null
  avg_llm_ms: number | null
  avg_search_ms: number | null
  avg_first_token_ms: number | null
  avg_tokens_per_sec: number | null
  daily: Array<{ date: string; avg_total: number; avg_llm: number; avg_rag: number }>
}

export interface ErrorRateStat {
  total: number
  errors: number
  rate: number
}

export interface ChatStats {
  feedback: FeedbackStat
  query_types: QueryTypeStat[]
  response_time: ResponseTimeStat
  models: ModelUsageStat[]
  avg_messages_per_session: number | null
  error_rate: ErrorRateStat
}

export interface TopDocumentStat {
  document_id: number
  title: string
  product_name: string | null
  usage_count: number
  context_tokens: number
  charge_usd: string
}

export interface DocumentFormatStat {
  format: string
  count: number
  pct: number
}

export interface DocumentStats {
  total: number
  avg_size_bytes: number | null
  avg_chunks: number | null
  uploads_daily: Array<{ date: string; count: number }>
  top_products: Array<{ name: string; count: number }>
  top_documents: TopDocumentStat[]
  formats: DocumentFormatStat[]
  unused_count: number
  total_chunks: number
  total_size_bytes: number
  used_chunks_count: number
}

export interface SearchSourceStat {
  source: string
  count: number
  pct: number
}

export interface ExtendedSearchStats extends SearchStat {
  sources: SearchSourceStat[]
  daily: Array<{ date: string; count: number; avg_similarity: number; zero_count: number }>
}

export interface CostByModelStat {
  model: string
  provider: string | null
  total_charge_usd: string
  total_tokens: number
  request_count: number
}

export interface CostByChannelStat {
  channel: string
  total_charge_usd: string
  request_count: number
}

export interface TopApiKeyStat {
  key_prefix: string
  email: string
  request_count: number
  charge_usd: string
}

export interface CostStats {
  total_charge_usd: string
  total_cogs_usd: string
  avg_per_day: string
  avg_per_user: string
  forecast_month_usd: string
  daily: Array<{ date: string; charge_usd: string; cogs_usd: string; requests: number }>
  by_model: CostByModelStat[]
  by_channel: CostByChannelStat[]
  top_api_keys: TopApiKeyStat[]
}

export async function getChatStats(days = 30): Promise<ChatStats> {
  const res = await fetch(`${BASE}/stats/chat?days=${days}`, { credentials: 'include' })
  return handleResponse(res)
}

export async function getDocumentStats(days = 30): Promise<DocumentStats> {
  const res = await fetch(`${BASE}/stats/documents?days=${days}`, { credentials: 'include' })
  return handleResponse(res)
}

export async function getExtendedSearchStats(days = 30): Promise<ExtendedSearchStats> {
  const res = await fetch(`${BASE}/stats/search-extended?days=${days}`, { credentials: 'include' })
  return handleResponse(res)
}

export async function getCostStats(days = 30): Promise<CostStats> {
  const res = await fetch(`${BASE}/stats/costs?days=${days}`, { credentials: 'include' })
  return handleResponse(res)
}


// --- MCP Audit ---

export interface McpRequestItem {
  id: number
  created_at: string
  tenant_email: string | null
  key_prefix: string | null
  request_id: string
  tool_name: string
  query_text: string | null
  result_count: number
  top_similarity: number
  duration_ms: number
  query_tokens: number
  response_tokens: number
  embedding_tokens: number
  rerank_total_tokens: number
  resolve_prompt_tokens: number
  resolve_completion_tokens: number
  resolve_model: string | null
  resolve_ms: number | null
  charge_usd: string
  status: string
}

export interface McpRequestDetail extends McpRequestItem {
  tenant_id: string | null
  api_key_id: string | null
  product_filter: string | null
  version_filter: string | null
  doc_type_filter: string | null
  response_length: number
  rerank_prompt_tokens: number
  rerank_completion_tokens: number
  rerank_total_tokens: number
  rerank_model: string | null
  embed_ms: number
  search_ms: number
  rerank_ms: number
  cogs_usd: string
  client_ip: string | null
  user_agent: string | null
  error: string | null
  sources: import('../types').McpSourceInfo[] | null
}

export interface McpRequestListResponse {
  items: McpRequestItem[]
  total: number
  page: number
  page_size: number
}

export interface McpToolBreakdown {
  tool_name: string
  count: number
  pct: number
}

export interface McpStats {
  total_requests: number
  total_query_tokens: number
  total_response_tokens: number
  total_embedding_tokens: number
  total_rerank_tokens: number
  total_resolve_tokens: number
  total_charge_usd: string
  avg_duration_ms: number | null
  error_count: number
  error_rate: number
  daily: Array<{ date: string; requests: number; tokens: number; charge_usd: string; errors: number }>
  by_tool: McpToolBreakdown[]
  top_queries: Array<{ query: string; count: number }>
  top_tenants: Array<{ email: string; count: number; charge_usd: string }>
}

export async function listMcpRequests(params: {
  page?: number
  page_size?: number
  tenant_id?: string
  tool_name?: string
  status?: string
  search?: string
  date_from?: string
  date_to?: string
} = {}): Promise<McpRequestListResponse> {
  const sp = new URLSearchParams()
  if (params.page) sp.set('page', String(params.page))
  if (params.page_size) sp.set('page_size', String(params.page_size))
  if (params.tenant_id) sp.set('tenant_id', params.tenant_id)
  if (params.tool_name) sp.set('tool_name', params.tool_name)
  if (params.status) sp.set('status', params.status)
  if (params.search) sp.set('search', params.search)
  if (params.date_from) sp.set('date_from', params.date_from)
  if (params.date_to) sp.set('date_to', params.date_to)
  const res = await fetch(`${BASE}/mcp/requests?${sp}`, { credentials: 'include' })
  return handleResponse(res)
}

export async function getMcpRequestDetail(requestId: string): Promise<McpRequestDetail> {
  const res = await fetch(`${BASE}/mcp/requests/${requestId}`, { credentials: 'include' })
  return handleResponse(res)
}

export async function getMcpStats(days = 30): Promise<McpStats> {
  const res = await fetch(`${BASE}/mcp/stats?days=${days}`, { credentials: 'include' })
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
  tenant?: string
  start?: string
  end?: string
  limit?: number
} = {}): Promise<{ entries: LogEntry[]; total: number }> {
  const sp = new URLSearchParams()
  if (params.service !== undefined) sp.set('service', params.service)
  if (params.level) sp.set('level', params.level)
  if (params.search) sp.set('search', params.search)
  if (params.tenant) sp.set('tenant', params.tenant)
  if (params.start) sp.set('start', params.start)
  if (params.end) sp.set('end', params.end)
  if (params.limit) sp.set('limit', String(params.limit))
  const res = await fetch(`${BASE}/logs?${sp}`, { credentials: 'include' })
  return handleResponse(res)
}

export interface TenantSearchResult {
  id: string
  name: string
  email: string
}

export async function searchTenants(q: string, limit = 10): Promise<TenantSearchResult[]> {
  const sp = new URLSearchParams({ q, limit: String(limit) })
  const res = await fetch(`${BASE}/tenants/search/autocomplete?${sp}`, { credentials: 'include' })
  return handleResponse(res)
}


// --- Roles ---

export interface RoleListItem {
  id: number
  slug: string
  name: string
  description: string
  is_system: boolean
  priority: number
  tenants_count: number
  created_at: string
}

export interface RoleDetail extends RoleListItem {
  permissions: Record<string, unknown>
  updated_at: string
}

export async function listRoles(): Promise<RoleListItem[]> {
  const res = await fetch(`${BASE}/roles`, { credentials: 'include' })
  return handleResponse(res)
}

export async function getRole(id: number): Promise<RoleDetail> {
  const res = await fetch(`${BASE}/roles/${id}`, { credentials: 'include' })
  return handleResponse(res)
}

export async function createRole(data: {
  slug: string
  name: string
  description?: string
  priority?: number
  permissions?: Record<string, unknown>
}): Promise<RoleDetail> {
  const res = await fetch(`${BASE}/roles`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    credentials: 'include',
  })
  return handleResponse(res)
}

export async function patchRole(id: number, data: {
  name?: string
  description?: string
  priority?: number
  permissions?: Record<string, unknown>
}): Promise<RoleDetail> {
  const res = await fetch(`${BASE}/roles/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    credentials: 'include',
  })
  return handleResponse(res)
}

export async function deleteRole(id: number): Promise<void> {
  const res = await fetch(`${BASE}/roles/${id}`, {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `HTTP ${res.status}`)
  }
}

export interface TenantRoleItem {
  id: number
  role_id: number
  role_slug: string
  role_name: string
  assigned_at: string
}

export async function getTenantRoles(tenantId: string): Promise<TenantRoleItem[]> {
  const res = await fetch(`${BASE}/tenants/${tenantId}/roles`, { credentials: 'include' })
  return handleResponse(res)
}

export async function assignTenantRole(tenantId: string, roleId: number): Promise<TenantRoleItem> {
  const res = await fetch(`${BASE}/tenants/${tenantId}/roles`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ role_id: roleId }),
    credentials: 'include',
  })
  return handleResponse(res)
}

export async function unassignTenantRole(tenantId: string, roleId: number): Promise<void> {
  const res = await fetch(`${BASE}/tenants/${tenantId}/roles/${roleId}`, {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `HTTP ${res.status}`)
  }
}


// --- Prompt Templates ---

export interface PromptTemplateItem {
  id: number
  query_type: string
  role_id: number | null
  role_slug: string | null
  parent_id: number | null
  is_system: boolean
  is_customized: boolean
  classifier_hint: string
  max_response_tokens: number | null
  rag_top_k: number | null
  created_at: string
  updated_at: string
}

export interface PromptTemplateDetail extends PromptTemplateItem {
  body: string
}

export interface PromptPreview {
  query_type: string
  resolved_body: string
  resolved_classifier_hint: string
  resolved_max_response_tokens: number | null
  resolved_rag_top_k: number | null
}

export async function listPrompts(): Promise<PromptTemplateItem[]> {
  const res = await fetch(`${BASE}/prompts`, { credentials: 'include' })
  return handleResponse(res)
}

export async function getPrompt(id: number): Promise<PromptTemplateDetail> {
  const res = await fetch(`${BASE}/prompts/${id}`, { credentials: 'include' })
  return handleResponse(res)
}

export async function createPrompt(data: {
  query_type: string
  role_id?: number | null
  body?: string
  classifier_hint?: string
  max_response_tokens?: number | null
  rag_top_k?: number | null
}): Promise<PromptTemplateDetail> {
  const res = await fetch(`${BASE}/prompts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    credentials: 'include',
  })
  return handleResponse(res)
}

export async function patchPrompt(id: number, data: {
  body?: string
  classifier_hint?: string
  max_response_tokens?: number | null
  rag_top_k?: number | null
}): Promise<PromptTemplateDetail> {
  const res = await fetch(`${BASE}/prompts/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    credentials: 'include',
  })
  return handleResponse(res)
}

export async function deletePrompt(id: number): Promise<void> {
  const res = await fetch(`${BASE}/prompts/${id}`, {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `HTTP ${res.status}`)
  }
}

export async function previewPrompt(id: number): Promise<PromptPreview> {
  const res = await fetch(`${BASE}/prompts/${id}/preview`, {
    method: 'POST',
    credentials: 'include',
  })
  return handleResponse(res)
}

export async function seedPrompts(): Promise<{ seeded: number }> {
  const res = await fetch(`${BASE}/prompts/seed`, {
    method: 'POST',
    credentials: 'include',
  })
  return handleResponse(res)
}


// --- System Monitor ---

export interface ServiceHealth {
  name: string
  status: string
  latency_ms: number
  detail: string | null
}

export interface LLMStatus {
  provider: string
  model: string
  avg_response_ms: number | null
  errors_last_hour: number
  timeouts_last_hour: number
}

export interface IngestionPipelineStatus {
  pending: number
  processing: number
  error: number
  docs_per_hour_24h: number
  stale_count: number
  tus_uploads_active: number
}

export interface TableSize {
  name: string
  size_bytes: number
}

export interface SystemInfo {
  cpu_percent: number
  cpu_count: number
  ram_used_bytes: number
  ram_total_bytes: number
  ram_percent: number
  disk_used_bytes: number
  disk_total_bytes: number
  disk_percent: number
  uptime_sec: number

  db_size_bytes: number
  db_active_connections: number
  db_pool_size: number
  db_pool_checked_out: number
  db_pool_overflow: number
  db_top_tables: TableSize[]

  redis_used_memory_bytes: number
  redis_total_keys: number
  redis_queue_celery: number
  redis_queue_monitoring: number

  s3_bucket_size_bytes: number
  s3_objects_count: number
  s3_quota_bytes: number

  ingestion: IngestionPipelineStatus
  llm: LLMStatus

  active_requests: number
  online_users_5min: number
  active_chat_sessions_5min: number

  services: ServiceHealth[]
}

export async function getSystemInfo(): Promise<SystemInfo> {
  const res = await fetch(`${BASE}/system/info`, { credentials: 'include' })
  return handleResponse(res)
}
