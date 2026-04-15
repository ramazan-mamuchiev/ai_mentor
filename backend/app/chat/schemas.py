"""Pydantic schemas for Chat API."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    title: str | None = None
    product_id: int | None = None
    product_filter: str | None = None
    product_filter_source: str | None = None
    version_filter: str | None = None


class UpdateSessionRequest(BaseModel):
    product_id: int | None = None
    product_filter: str | None = None
    product_filter_source: str | None = None
    version_filter: str | None = None


class SessionResponse(BaseModel):
    id: str
    title: str | None
    product_id: int | None = None
    product_filter: str | None
    product_filter_source: str | None = None
    version_filter: str | None
    doc_context: str | None = None
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class SessionListItem(BaseModel):
    id: str
    title: str | None
    product_id: int | None = None
    product_filter: str | None
    product_filter_source: str | None = None
    version_filter: str | None
    doc_context: str | None = None
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
    last_message_preview: str | None = None


class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)


class FeedbackRequest(BaseModel):
    feedback: str = Field(..., pattern=r"^(up|down)$")
    comment: str | None = Field(None, max_length=2000)


class SourceInfo(BaseModel):
    document_id: int | None = None
    doc_title: str
    heading_path: str
    similarity: float
    content_preview: str
    product_name: str = ""
    firmware_version: str = ""


class ChatMessageResponse(BaseModel):
    id: int
    session_id: str
    role: str
    content: str
    sources: list[SourceInfo] | None = None
    duration_ms: float | None = None
    feedback: str | None = None
    feedback_comment: str | None = None
    debug: dict | None = None
    created_at: datetime


class SessionDetailResponse(BaseModel):
    id: str
    title: str | None
    product_id: int | None = None
    product_filter: str | None
    product_filter_source: str | None = None
    version_filter: str | None
    doc_context: str | None = None
    created_at: datetime
    updated_at: datetime
    messages: list[ChatMessageResponse]
