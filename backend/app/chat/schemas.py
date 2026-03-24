"""Pydantic schemas for Chat API."""

from datetime import datetime

from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    title: str | None = None
    product_filter: str | None = None
    version_filter: str | None = None


class UpdateSessionRequest(BaseModel):
    product_filter: str | None = None
    version_filter: str | None = None


class SessionResponse(BaseModel):
    id: int
    title: str | None
    product_filter: str | None
    version_filter: str | None
    doc_context: str | None = None
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class SessionListItem(BaseModel):
    id: int
    title: str | None
    product_filter: str | None
    version_filter: str | None
    doc_context: str | None = None
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
    last_message_preview: str | None = None


class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)


class SourceInfo(BaseModel):
    doc_title: str
    heading_path: str
    similarity: float
    content_preview: str
    product_name: str = ""
    firmware_version: str = ""


class ChatMessageResponse(BaseModel):
    id: int
    session_id: int
    role: str
    content: str
    sources: list[SourceInfo] | None = None
    duration_ms: float | None = None
    debug: dict | None = None
    created_at: datetime


class SessionDetailResponse(BaseModel):
    id: int
    title: str | None
    product_filter: str | None
    version_filter: str | None
    doc_context: str | None = None
    created_at: datetime
    updated_at: datetime
    messages: list[ChatMessageResponse]
