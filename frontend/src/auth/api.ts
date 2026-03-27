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
  api_key: string
}

export interface LoginData {
  email: string
  password: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
}

export interface MeResponse {
  id: string
  email: string
  name: string | null
  slug: string
  tier: string
  role: string
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
  created_at: string
}

export interface ApiKeyCreated extends ApiKeyItem {
  key: string
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `HTTP ${res.status}`)
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

export async function getApiKeys(): Promise<ApiKeyItem[]> {
  const res = await fetch(`${BASE}/api-keys`, { credentials: 'include' })
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

export async function deleteApiKey(id: string): Promise<void> {
  await fetch(`${BASE}/api-keys/${id}`, {
    method: 'DELETE',
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
