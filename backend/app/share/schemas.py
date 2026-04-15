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
    expires_at: datetime | None = None


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


class SharedDebugContentResponse(BaseModel):
    share_type: str
    title: str
    data: dict
    created_at: datetime
    view_count: int
    expires_at: datetime | None = None


class SharedDocumentPreviewResponse(BaseModel):
    share_type: str
    title: str
    markdown: str
    source: str
    size_bytes: int
    created_at: datetime
    view_count: int


class SharedLifecycleContentResponse(BaseModel):
    share_type: str
    title: str
    product_name: str
    merged: dict | None = None
    document_lifecycles: list[dict] = []
    doc_issues: list[dict] = []
    created_at: datetime
    view_count: int


class AdminSharedLinkResponse(BaseModel):
    id: int
    token: str
    url: str
    share_type: str
    title: str
    view_count: int
    is_active: bool
    tenant_email: str | None = None
    tenant_name: str | None = None
    created_at: datetime
    expires_at: datetime | None = None


class AdminSharedLinksListResponse(BaseModel):
    items: list[AdminSharedLinkResponse]
    total: int
    page: int
    page_size: int
