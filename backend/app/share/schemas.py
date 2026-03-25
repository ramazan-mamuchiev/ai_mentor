"""Pydantic schemas for Share API."""

from datetime import datetime

from pydantic import BaseModel


class SharedLinkResponse(BaseModel):
    token: str
    url: str
    share_type: str
    title: str
    view_count: int
    is_active: bool
    created_at: datetime


class SharedMessageSnapshot(BaseModel):
    role: str
    content: str
    sources: list[dict] | None = None
    created_at: str


class SharedContentResponse(BaseModel):
    share_type: str
    title: str
    product_filter: str | None = None
    version_filter: str | None = None
    messages: list[SharedMessageSnapshot]
    created_at: datetime
    view_count: int
