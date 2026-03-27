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


# --- Me ---

class MeResponse(BaseModel):
    id: uuid.UUID
    email: str
    name: str | None
    slug: str
    tier: str
    email_verified: bool
    created_at: datetime


# --- Update profile ---

class UpdateMeRequest(BaseModel):
    name: str | None = Field(default=None, max_length=128)


# --- API Keys ---

class CreateApiKeyRequest(BaseModel):
    name: str = Field(default="", max_length=128)
    scopes: str = "search,list"


class ApiKeyResponse(BaseModel):
    id: uuid.UUID
    key_prefix: str
    name: str
    scopes: str
    is_active: bool
    last_used_at: datetime | None
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
