"""Pydantic request/response schemas for auth endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


# --- Register ---

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str | None = Field(default=None, max_length=128)


class RegisterResponse(BaseModel):
    id: uuid.UUID
    email: str
    slug: str
    api_key: str  # shown once on registration


# --- Login ---

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 900


# --- Me ---

class RoleBrief(BaseModel):
    id: int
    slug: str
    name: str
    priority: int


class MeResponse(BaseModel):
    id: uuid.UUID
    email: str
    name: str | None
    slug: str
    tier: str
    role: str
    roles: list[RoleBrief] = []
    permissions: dict = {}
    email_verified: bool
    created_at: datetime


# --- Update profile ---

class UpdateMeRequest(BaseModel):
    name: str | None = Field(default=None, max_length=128)


# --- API Keys ---

class CreateApiKeyRequest(BaseModel):
    name: str = Field(default="", max_length=128)
    scopes: str = "search,list"


class RevokeApiKeyRequest(BaseModel):
    reason: str | None = None


class ApiKeyResponse(BaseModel):
    id: uuid.UUID
    key_prefix: str
    name: str
    scopes: str
    is_active: bool
    last_used_at: datetime | None
    revoked_at: datetime | None = None
    revoke_reason: str | None = None
    created_at: datetime


class ApiKeyCreatedResponse(ApiKeyResponse):
    key: str  # full key shown once


# --- OAuth ---

class OAuthCallbackResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    is_new_account: bool


# --- Password reset ---

class RequestPasswordResetRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


# --- Usage analytics ---

class ActionBreakdown(BaseModel):
    action: str
    count: int
    tokens: int

class DailyUsage(BaseModel):
    date: str
    requests: int
    tokens: int

class ApiKeyUsageResponse(BaseModel):
    total_requests: int
    total_tokens: int
    total_charge_usd: str
    by_action: list[ActionBreakdown]
    daily: list[DailyUsage]

class KeySummary(BaseModel):
    key_id: str
    key_name: str
    key_prefix: str
    total_requests: int
    total_tokens: int
    total_charge_usd: str

class UsageSummaryResponse(BaseModel):
    total_requests: int
    total_tokens: int
    total_charge_usd: str
    active_keys: int
    by_action: list[ActionBreakdown]
    daily: list[DailyUsage]
    by_key: list[KeySummary]


# --- User-level extended analytics ---

class UserChatStats(BaseModel):
    total_sessions: int = 0
    total_messages: int = 0
    avg_messages_per_session: float | None = None
    feedback_positive: int = 0
    feedback_negative: int = 0
    feedback_total: int = 0
    positive_rate: float | None = None
    query_types: list[dict] = []
    avg_response_ms: float | None = None
    avg_tokens_per_sec: float | None = None
    response_daily: list[dict] = []

class UserDocStats(BaseModel):
    total_documents: int = 0
    documents_indexed: int = 0
    documents_pending: int = 0
    documents_error: int = 0
    total_chunks: int = 0
    total_size_bytes: int = 0
    ocr_prompt_tokens: int = 0
    ocr_completion_tokens: int = 0
    ocr_total_tokens: int = 0
    ocr_documents: int = 0
    embedding_tokens: int = 0
    extract_tokens: int = 0
    product_keys_tokens: int = 0
    ingestion_cost_usd: str = "0"
    formats: list[dict] = []
    products: list[dict] = []
    uploads_daily: list[dict] = []

class UserSearchStats(BaseModel):
    total_searches: int = 0
    avg_similarity: float | None = None
    avg_duration_ms: float | None = None
    zero_result_count: int = 0
    top_queries: list[dict] = []
    daily: list[dict] = []

class UserMcpStats(BaseModel):
    total_requests: int = 0
    total_tokens: int = 0
    total_charge_usd: str = "0"
    avg_duration_ms: float | None = None
    error_count: int = 0
    by_tool: list[dict] = []
    top_queries: list[dict] = []
    daily: list[dict] = []

class UserCostStats(BaseModel):
    total_charge_usd: str = "0"
    avg_per_day: str = "0"
    forecast_month_usd: str = "0"
    ocr_total_tokens: int = 0
    ocr_cost_usd: str = "0"
    ingestion_cost_usd: str = "0"
    ingestion_breakdown: list[dict] = []
    daily: list[dict] = []
    by_model: list[dict] = []
    by_channel: list[dict] = []
