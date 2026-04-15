const BASE = '/api/v1'

export interface RegisterData {
  email: string
  password: string
  name?: string
}

export interface RegisterResponse {
  id: string
  email: string
  slug: string
}

export interface LoginData {
  email: string
  password: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
}

export interface RoleBrief {
  id: number
  slug: string
  name: string
  priority: number
}

export interface MeResponse {
  id: string
  email: string
  name: string | null
  slug: string
  tier: string
  role: string
  roles: RoleBrief[]
  permissions: Record<string, unknown>
  email_verified: boolean
  created_at: string
}

export interface ApiKeyItem {
  id: string
  key_prefix: string
  name: string
  scopes: string
  is_active: boolean
  last_used_at: string | null
  revoked_at: string | null
  revoke_reason: string | null
  created_at: string
}

export interface ApiKeyCreated extends ApiKeyItem {
  key: string
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || body.error || `HTTP ${res.status}`)
  }
  return res.json()
}

export async function register(data: RegisterData): Promise<RegisterResponse> {
  const res = await fetch(`${BASE}/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    credentials: 'include',
  })
  return handleResponse(res)
}

export async function login(data: LoginData): Promise<TokenResponse> {
  const res = await fetch(`${BASE}/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    credentials: 'include',
  })
  return handleResponse(res)
}

export async function refreshToken(): Promise<TokenResponse> {
  const res = await fetch(`${BASE}/refresh`, {
    method: 'POST',
    credentials: 'include',
  })
  return handleResponse(res)
}

export async function logout(): Promise<void> {
  await fetch(`${BASE}/logout`, {
    method: 'POST',
    credentials: 'include',
  })
}

export async function verifyEmail(token: string): Promise<{ ok: boolean }> {
  const res = await fetch(`${BASE}/verify-email`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
    credentials: 'include',
  })
  return handleResponse(res)
}

export async function resendVerification(): Promise<{ ok: boolean }> {
  const res = await fetch(`${BASE}/resend-verification`, {
    method: 'POST',
    credentials: 'include',
  })
  return handleResponse(res)
}

export async function getMe(): Promise<MeResponse> {
  const res = await fetch(`${BASE}/me`, { credentials: 'include' })
  return handleResponse(res)
}

export async function updateMe(data: { name?: string }): Promise<MeResponse> {
  const res = await fetch(`${BASE}/me`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    credentials: 'include',
  })
  return handleResponse(res)
}

export async function getApiKeys(includeRevoked = false): Promise<ApiKeyItem[]> {
  const qs = includeRevoked ? '?include_revoked=true' : ''
  const res = await fetch(`${BASE}/api-keys${qs}`, { credentials: 'include' })
  return handleResponse(res)
}

export async function createApiKey(name: string): Promise<ApiKeyCreated> {
  const res = await fetch(`${BASE}/api-keys`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
    credentials: 'include',
  })
  return handleResponse(res)
}

export async function revokeApiKey(id: string, reason?: string): Promise<void> {
  await fetch(`${BASE}/api-keys/${id}`, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason: reason || null }),
    credentials: 'include',
  })
}

export interface ActionBreakdown {
  action: string
  count: number
  tokens: number
}

export interface DailyUsage {
  date: string
  requests: number
  tokens: number
}

export interface ApiKeyUsageResponse {
  total_requests: number
  total_tokens: number
  total_charge_usd: string
  by_action: ActionBreakdown[]
  daily: DailyUsage[]
}

export interface KeySummary {
  key_id: string
  key_name: string
  key_prefix: string
  total_requests: number
  total_tokens: number
  total_charge_usd: string
}

export interface UsageSummaryResponse {
  total_requests: number
  total_tokens: number
  total_charge_usd: string
  active_keys: number
  by_action: ActionBreakdown[]
  daily: DailyUsage[]
  by_key: KeySummary[]
}

export async function getApiKeyUsage(keyId: string): Promise<ApiKeyUsageResponse> {
  const res = await fetch(`${BASE}/api-keys/${keyId}/usage`, { credentials: 'include' })
  return handleResponse(res)
}

export async function getUsageSummary(days = 30): Promise<UsageSummaryResponse> {
  const res = await fetch(`${BASE}/usage/summary?days=${days}`, { credentials: 'include' })
  return handleResponse(res)
}


// --- User-level extended analytics ---

export interface UserChatStats {
  total_sessions: number
  total_messages: number
  avg_messages_per_session: number | null
  feedback_positive: number
  feedback_negative: number
  feedback_total: number
  positive_rate: number | null
  query_types: Array<{ query_type: string; count: number; pct: number }>
  avg_response_ms: number | null
  avg_tokens_per_sec: number | null
  response_daily: Array<{ date: string; avg_total: number }>
}

export interface UserDocStats {
  total_documents: number
  documents_indexed: number
  documents_pending: number
  documents_error: number
  total_chunks: number
  total_size_bytes: number
  ocr_prompt_tokens: number
  ocr_completion_tokens: number
  ocr_total_tokens: number
  ocr_documents: number
  embedding_tokens: number
  extract_tokens: number
  product_keys_tokens: number
  ingestion_cost_usd: string
  formats: Array<{ format: string; count: number; pct: number }>
  products: Array<{ name: string; count: number }>
  uploads_daily: Array<{ date: string; count: number }>
}

export interface UserSearchStats {
  total_searches: number
  avg_similarity: number | null
  avg_duration_ms: number | null
  zero_result_count: number
  top_queries: Array<{ query: string; count: number }>
  daily: Array<{ date: string; count: number; avg_similarity: number }>
}

export interface UserMcpStats {
  total_requests: number
  total_tokens: number
  total_charge_usd: string
  avg_duration_ms: number | null
  error_count: number
  by_tool: Array<{ tool_name: string; count: number; pct: number }>
  top_queries: Array<{ query: string; count: number }>
  daily: Array<{ date: string; requests: number; tokens: number; charge_usd: string }>
}

export interface UserCostStats {
  total_charge_usd: string
  avg_per_day: string
  forecast_month_usd: string
  ocr_total_tokens: number
  ocr_cost_usd: string
  ingestion_cost_usd: string
  ingestion_breakdown: Array<{ type: string; tokens: number; cost_usd: string }>
  daily: Array<{ date: string; charge_usd: string; requests: number }>
  by_model: Array<{ model: string; provider: string; total_charge_usd: string; total_tokens: number; request_count: number }>
  by_channel: Array<{ channel: string; total_charge_usd: string; request_count: number }>
}

export async function getUserChatStats(days = 30): Promise<UserChatStats> {
  const res = await fetch(`${BASE}/analytics/chat?days=${days}`, { credentials: 'include' })
  return handleResponse(res)
}

export async function getUserDocStats(days = 30): Promise<UserDocStats> {
  const res = await fetch(`${BASE}/analytics/documents?days=${days}`, { credentials: 'include' })
  return handleResponse(res)
}

export async function getUserSearchStats(days = 30): Promise<UserSearchStats> {
  const res = await fetch(`${BASE}/analytics/search?days=${days}`, { credentials: 'include' })
  return handleResponse(res)
}

export async function getUserMcpStats(days = 30): Promise<UserMcpStats> {
  const res = await fetch(`${BASE}/analytics/mcp?days=${days}`, { credentials: 'include' })
  return handleResponse(res)
}

export async function getUserCostStats(days = 30): Promise<UserCostStats> {
  const res = await fetch(`${BASE}/analytics/costs?days=${days}`, { credentials: 'include' })
  return handleResponse(res)
}
