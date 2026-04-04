"""SQLAlchemy ORM models for Lexiro."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from pgvector.sqlalchemy import Vector
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Auth models
# ---------------------------------------------------------------------------

class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    tier: Mapped[str] = mapped_column(Text, default="free")
    role: Mapped[str] = mapped_column(Text, default="user")  # "user" | "admin"
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    api_keys: Mapped[list["ApiKey"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan",
    )
    oauth_links: Mapped[list["TenantOAuthLink"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan",
    )
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan",
    )


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False,
    )
    key_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    key_prefix: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, default="")
    scopes: Mapped[str] = mapped_column(Text, default="search,list")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="api_keys")

    __table_args__ = (
        Index("idx_api_keys_hash", "key_hash"),
        Index("idx_api_keys_tenant", "tenant_id"),
    )


class TenantOAuthLink(Base):
    __tablename__ = "tenant_oauth_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False,
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    oauth_id: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="oauth_links")

    __table_args__ = (
        UniqueConstraint("provider", "oauth_id"),
        Index("idx_oauth_links_tenant", "tenant_id"),
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="refresh_tokens")

    __table_args__ = (
        Index("idx_refresh_tokens_hash", "token_hash"),
        Index("idx_refresh_tokens_tenant", "tenant_id"),
        Index("idx_refresh_tokens_expires", "expires_at"),
    )


# ---------------------------------------------------------------------------
# Product catalog models
# ---------------------------------------------------------------------------

class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    manufacturer: Mapped[str] = mapped_column(Text, default="")
    model: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(Text, default="")
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    sync_status: Mapped[str] = mapped_column(Text, default="idle")

    firmware_versions: Mapped[list["FirmwareVersion"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("manufacturer", "model"),
        Index("idx_products_tenant", "tenant_id"),
    )


class FirmwareVersion(Base):
    __tablename__ = "firmware_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    product: Mapped["Product"] = relationship(back_populates="firmware_versions")

    __table_args__ = (UniqueConstraint("product_id", "version"),)


class ProductSearchKey(Base):
    __tablename__ = "product_search_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=True)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, default="llm")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (UniqueConstraint("product_id", "document_id", "key"),)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    firmware_version_id: Mapped[int] = mapped_column(ForeignKey("firmware_versions.id", ondelete="CASCADE"), nullable=False)
    format: Mapped[str] = mapped_column(Text, default="markdown")
    source_path: Mapped[str] = mapped_column(Text, default="")
    s3_key: Mapped[str] = mapped_column(Text, default="")
    original_filename: Mapped[str] = mapped_column(Text, default="")
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    source_hash: Mapped[str] = mapped_column(Text, default="")
    title: Mapped[str] = mapped_column(Text, default="")
    total_chunks: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(Text, default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    ingest_duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    read_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    convert_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    parse_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    embed_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    db_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    min_chunk_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_chunk_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_chunk_tokens: Mapped[float | None] = mapped_column(Float, nullable=True)

    embedding_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_dims: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding_tokens: Mapped[int] = mapped_column(Integer, default=0)

    rag_hit_count: Mapped[int] = mapped_column(Integer, default=0)
    rag_avg_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    rag_last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    progress_stage: Mapped[str] = mapped_column(Text, default="")

    celery_task_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    ocr_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    ocr_images_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ocr_images_success: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ocr_images_empty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ocr_images_failed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ocr_prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    ocr_completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    ocr_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_language: Mapped[str | None] = mapped_column(Text, nullable=True)

    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    source_container: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_folder: Mapped[str] = mapped_column(Text, default="")

    converted_s3_key: Mapped[str | None] = mapped_column(Text, nullable=True)

    extract_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    extract_prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    extract_completion_tokens: Mapped[int] = mapped_column(Integer, default=0)

    product_keys_prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    product_keys_completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    product_keys_ms: Mapped[float] = mapped_column(Float, default=0)

    crawl_checkpoint: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    lifecycle_prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    lifecycle_completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    lifecycle_ms: Mapped[float] = mapped_column(Float, default=0)
    lifecycle_status: Mapped[str] = mapped_column(Text, default="")

    chunks: Mapped[list["Chunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    heading_path: Mapped[str] = mapped_column(Text, nullable=False)
    heading_level: Mapped[int] = mapped_column(Integer, default=1)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_clean: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    embedding = mapped_column(Vector(1024))
    doc_type: Mapped[str] = mapped_column(Text, default="other")
    entities: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)

    layer: Mapped[str | None] = mapped_column(Text, nullable=True)
    topic: Mapped[str | None] = mapped_column(Text, nullable=True)
    doc_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    related_docs: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    document: Mapped["Document"] = relationship(back_populates="chunks")

    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index"),
        Index("idx_chunks_document", "document_id"),
        Index("idx_chunks_doc_type", "doc_type"),
        Index("idx_chunks_layer", "layer"),
    )


class ApiLifecycle(Base):
    __tablename__ = "api_lifecycles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=True,
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False,
    )
    phases: Mapped[list] = mapped_column(JSONB, default=list)
    unique_patterns: Mapped[list] = mapped_column(JSONB, default=list)
    dependency_chains: Mapped[list] = mapped_column(JSONB, default=list)
    code_skeleton: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_models: Mapped[list] = mapped_column(JSONB, default=list)
    error_catalog: Mapped[list] = mapped_column(JSONB, default=list)
    prerequisites: Mapped[list] = mapped_column(JSONB, default=list)
    data_access_patterns: Mapped[list] = mapped_column(JSONB, default=list)
    endpoint_coverage: Mapped[list] = mapped_column(JSONB, default=list)
    validation_issues: Mapped[list] = mapped_column(JSONB, default=list)
    validation_retries: Mapped[int] = mapped_column(Integer, default=0)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    analysis_ms: Mapped[float] = mapped_column(Float, default=0)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class DocIssueAnnotation(Base):
    __tablename__ = "doc_issue_annotations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False,
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False,
    )
    chunk_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("chunks.id", ondelete="SET NULL"), nullable=True,
    )
    issue_type: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, default="warning")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    affected_entity: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_by: Mapped[str] = mapped_column(Text, default="lifecycle_analysis")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uuid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4,
    )
    tenant_id = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True)
    api_key_id = mapped_column(UUID(as_uuid=True), nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    product_filter: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_filter_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    version_filter: Mapped[str | None] = mapped_column(Text, nullable=True)
    doc_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    history_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_up_to_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    product: Mapped["Product | None"] = relationship()
    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="ChatMessage.created_at"
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sources: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    session: Mapped["ChatSession"] = relationship(back_populates="messages")
    analytics: Mapped["ChatMessageAnalytics | None"] = relationship(
        back_populates="message", uselist=False, cascade="all, delete-orphan",
        foreign_keys="ChatMessageAnalytics.message_id",
    )

    __table_args__ = (Index("idx_chat_messages_session", "session_id"),)


class ChatMessageAnalytics(Base):
    __tablename__ = "chat_message_analytics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_id: Mapped[int] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    session_id: Mapped[int] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    user_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="SET NULL"), nullable=True
    )

    llm_provider: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    temperature: Mapped[float] = mapped_column(Float, default=0)
    max_tokens: Mapped[int] = mapped_column(Integer, default=0)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    tokens_per_sec: Mapped[float] = mapped_column(Float, default=0)
    response_length: Mapped[int] = mapped_column(Integer, default=0)

    total_ms: Mapped[float] = mapped_column(Float, default=0)
    rag_ms: Mapped[float] = mapped_column(Float, default=0)
    llm_ms: Mapped[float] = mapped_column(Float, default=0)
    search_ms: Mapped[float] = mapped_column(Float, default=0)
    first_token_ms: Mapped[float] = mapped_column(Float, default=0)
    rag_build_ms: Mapped[float] = mapped_column(Float, default=0)

    chunks_found: Mapped[int] = mapped_column(Integer, default=0)
    top_similarity: Mapped[float] = mapped_column(Float, default=0)
    min_similarity: Mapped[float] = mapped_column(Float, default=0)
    context_tokens: Mapped[int] = mapped_column(Integer, default=0)
    history_messages: Mapped[int] = mapped_column(Integer, default=0)
    prompt_messages: Mapped[int] = mapped_column(Integer, default=0)
    embedding_model: Mapped[str] = mapped_column(Text, default="")

    doc_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    auto_product: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_doc_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    query_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_hash: Mapped[str | None] = mapped_column(Text, nullable=True)

    user_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    user_output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    llm_prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    llm_completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    llm_total_tokens: Mapped[int] = mapped_column(Integer, default=0)

    finish_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    continuations: Mapped[int] = mapped_column(Integer, default=0)

    query_tokens: Mapped[int] = mapped_column(Integer, default=0)
    history_tokens: Mapped[int] = mapped_column(Integer, default=0)
    system_prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    effective_top_k: Mapped[int | None] = mapped_column(Integer, nullable=True)

    classify_input: Mapped[str | None] = mapped_column(Text, nullable=True)
    classify_product: Mapped[str | None] = mapped_column(Text, nullable=True)
    classify_prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    classify_completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    classify_total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    classify_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    classify_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    resolve_prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    resolve_completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    resolve_total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    resolve_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolve_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    rerank_prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    rerank_completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    rerank_total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    rerank_model: Mapped[str | None] = mapped_column(Text, nullable=True)

    decompose_used: Mapped[bool] = mapped_column(Boolean, default=False)
    decompose_sub_queries: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    decompose_sub_products: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    decompose_prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    decompose_completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    decompose_total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    decompose_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    decompose_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    web_search_used: Mapped[bool] = mapped_column(Boolean, default=False)
    web_search_queries: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    web_search_sources_count: Mapped[int] = mapped_column(Integer, default=0)
    web_search_prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    web_search_completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    web_search_total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    web_search_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    web_search_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    web_search_context_length: Mapped[int] = mapped_column(Integer, default=0)

    rewrite_prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    rewrite_completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    rewrite_total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    rewrite_model: Mapped[str | None] = mapped_column(Text, nullable=True)

    retry_used: Mapped[bool] = mapped_column(Boolean, default=False)
    rephrase_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    rephrase_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    rephrase_prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    rephrase_completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    rephrase_total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    rephrase_model: Mapped[str | None] = mapped_column(Text, nullable=True)

    embedding_api_tokens: Mapped[int] = mapped_column(Integer, default=0)

    summary_prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    summary_completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    summary_total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    summary_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    message: Mapped["ChatMessage"] = relationship(
        back_populates="analytics", foreign_keys=[message_id]
    )

    __table_args__ = (
        Index("idx_cma_session", "session_id"),
        Index("idx_cma_model", "model"),
        Index("idx_cma_provider", "llm_provider"),
        Index("idx_cma_created", "created_at"),
        Index("idx_cma_similarity", "top_similarity"),
    )

    def to_debug_dict(
        self,
        product_filter: str | None = None,
        version_filter: str | None = None,
        session_uuid: str | None = None,
    ) -> dict:
        """Convert to the debug_info dict expected by the frontend."""
        return {
            "session_id": session_uuid or self.session_id,
            "message_id": self.message_id,
            "user_message_id": self.user_message_id,
            "timestamp": self.created_at.isoformat() if self.created_at else None,
            "model": self.model,
            "llm_provider": self.llm_provider,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "first_token_ms": self.first_token_ms,
            "rag_ms": self.rag_ms,
            "llm_ms": self.llm_ms,
            "total_ms": self.total_ms,
            "search_ms": self.search_ms,
            "rag_build_ms": self.rag_build_ms,
            "token_count": self.token_count,
            "tokens_per_sec": self.tokens_per_sec,
            "response_length": self.response_length,
            "chunks_found": self.chunks_found,
            "top_similarity": self.top_similarity,
            "min_similarity": self.min_similarity,
            "context_tokens": self.context_tokens,
            "query_tokens": self.query_tokens,
            "history_tokens": self.history_tokens,
            "system_prompt_tokens": self.system_prompt_tokens,
            "effective_top_k": self.effective_top_k,
            "history_messages": self.history_messages,
            "prompt_messages": self.prompt_messages,
            "embedding_model": self.embedding_model,
            "embedding_api_tokens": self.embedding_api_tokens,
            "product_filter": product_filter,
            "version_filter": version_filter,
            "doc_context": self.doc_context,
            "auto_product": self.auto_product,
            "detected_doc_context": self.detected_doc_context,
            "search_query": self.search_query,
            "query_type": self.query_type,
            "prompt_hash": self.prompt_hash,
            "user_input_tokens": self.user_input_tokens,
            "user_output_tokens": self.user_output_tokens,
            "llm_prompt_tokens": self.llm_prompt_tokens,
            "llm_completion_tokens": self.llm_completion_tokens,
            "llm_total_tokens": self.llm_total_tokens,
            "finish_reason": self.finish_reason,
            "continuations": self.continuations,
            "classify_input": self.classify_input,
            "classify_product": self.classify_product,
            "classify_prompt_tokens": self.classify_prompt_tokens,
            "classify_completion_tokens": self.classify_completion_tokens,
            "classify_total_tokens": self.classify_total_tokens,
            "classify_model": self.classify_model,
            "classify_ms": self.classify_ms,
            "rerank_prompt_tokens": self.rerank_prompt_tokens,
            "rerank_completion_tokens": self.rerank_completion_tokens,
            "rerank_total_tokens": self.rerank_total_tokens,
            "rerank_model": self.rerank_model,
            "decompose_used": self.decompose_used,
            "decompose_sub_queries": self.decompose_sub_queries,
            "decompose_sub_products": self.decompose_sub_products,
            "decompose_prompt_tokens": self.decompose_prompt_tokens,
            "decompose_completion_tokens": self.decompose_completion_tokens,
            "decompose_total_tokens": self.decompose_total_tokens,
            "decompose_model": self.decompose_model,
            "decompose_ms": self.decompose_ms,
            "web_search_used": self.web_search_used,
            "web_search_queries": self.web_search_queries,
            "web_search_sources_count": self.web_search_sources_count,
            "web_search_prompt_tokens": self.web_search_prompt_tokens,
            "web_search_completion_tokens": self.web_search_completion_tokens,
            "web_search_total_tokens": self.web_search_total_tokens,
            "web_search_model": self.web_search_model,
            "web_search_ms": self.web_search_ms,
            "web_search_context_length": self.web_search_context_length,
            "rewrite_prompt_tokens": self.rewrite_prompt_tokens,
            "rewrite_completion_tokens": self.rewrite_completion_tokens,
            "rewrite_total_tokens": self.rewrite_total_tokens,
            "rewrite_model": self.rewrite_model,
            "retry_used": self.retry_used,
            "rephrase_ms": self.rephrase_ms,
            "rephrase_query": self.rephrase_query,
            "rephrase_prompt_tokens": self.rephrase_prompt_tokens,
            "rephrase_completion_tokens": self.rephrase_completion_tokens,
            "rephrase_total_tokens": self.rephrase_total_tokens,
            "rephrase_model": self.rephrase_model,
            "summary_prompt_tokens": self.summary_prompt_tokens,
            "summary_completion_tokens": self.summary_completion_tokens,
            "summary_total_tokens": self.summary_total_tokens,
            "summary_model": self.summary_model,
            "summary_ms": self.summary_ms,
        }


class DocumentUsageLog(Base):
    """Per-document usage attribution for author remuneration.

    Each row represents one chunk from a specific document that was included
    in a RAG response context. Enables proportional revenue sharing based on
    context_tokens contributed by each document.
    """
    __tablename__ = "document_usage_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id = mapped_column(UUID(as_uuid=True), nullable=True)
    api_key_id = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )

    request_id: Mapped[str] = mapped_column(Text, nullable=False)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    message_id: Mapped[int] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )

    chunk_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    heading_path: Mapped[str] = mapped_column(Text, default="")
    similarity: Mapped[float] = mapped_column(Float, default=0)
    context_tokens: Mapped[int] = mapped_column(Integer, default=0)

    query_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    query_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    sub_query: Mapped[str | None] = mapped_column(Text, nullable=True)

    charge_usd: Mapped[Decimal] = mapped_column(Numeric(12, 8), default=Decimal("0"))

    __table_args__ = (
        Index("idx_dul_request", "request_id"),
        Index("idx_dul_document", "document_id", "created_at"),
        Index("idx_dul_product", "product_id", "created_at"),
        Index("idx_dul_session", "session_id"),
        Index("idx_dul_created", "created_at"),
        Index("idx_dul_api_key", "api_key_id"),
    )


class SharedLink(Base):
    __tablename__ = "shared_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True)
    token: Mapped[str] = mapped_column(Text, unique=True, index=True, nullable=False)
    session_id: Mapped[int | None] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=True
    )
    message_id: Mapped[int | None] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=True
    )
    share_type: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, default="")
    snapshot_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    session: Mapped["ChatSession"] = relationship()

    __table_args__ = (
        Index("idx_shared_links_token", "token"),
        Index("idx_shared_links_session", "session_id"),
    )


class SearchAnalytics(Base):
    __tablename__ = "search_analytics"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id = mapped_column(UUID(as_uuid=True), nullable=True)
    api_key_id = mapped_column(UUID(as_uuid=True), nullable=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    tool_name: Mapped[str] = mapped_column(Text, nullable=False)
    query: Mapped[str] = mapped_column(Text, default="")
    product_filter: Mapped[str | None] = mapped_column(Text, nullable=True)
    version_filter: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    top_similarity: Mapped[float] = mapped_column(Float, default=0)
    duration_ms: Mapped[float] = mapped_column(Float, default=0)
    embedding_model: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("idx_sa_source", "source"),
        Index("idx_sa_tool", "tool_name"),
        Index("idx_sa_created", "created_at"),
    )


class ReindexJob(Base):
    """Tracks a background reindexing operation (reingest or re-embed).

    Lifecycle: pending → running → completed | failed | cancelled | stale
    The Celery orchestrator updates heartbeat_at periodically so the API can
    detect hung jobs (heartbeat_at older than the stale threshold).
    """
    __tablename__ = "reindex_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True)
    mode: Mapped[str] = mapped_column(Text, nullable=False)  # "reingest" | "reembed"
    status: Mapped[str] = mapped_column(Text, default="pending")
    product_filter: Mapped[str | None] = mapped_column(Text, nullable=True)
    format_filter: Mapped[str | None] = mapped_column(Text, nullable=True)

    total_documents: Mapped[int] = mapped_column(Integer, default=0)
    processed_documents: Mapped[int] = mapped_column(Integer, default=0)
    failed_documents: Mapped[int] = mapped_column(Integer, default=0)
    skipped_documents: Mapped[int] = mapped_column(Integer, default=0)
    total_chunks: Mapped[int] = mapped_column(Integer, default=0)

    celery_task_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    errors_json: Mapped[str] = mapped_column(Text, default="[]")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_reindex_jobs_status", "status"),
    )


def _default_upload_expires():
    from app.config import settings
    return datetime.now(timezone.utc) + timedelta(hours=settings.tus_upload_ttl_hours)


class UploadSession(Base):
    __tablename__ = "upload_sessions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    tenant_id = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    offset: Mapped[int] = mapped_column(BigInteger, default=0)
    content_type: Mapped[str] = mapped_column(Text, default="application/octet-stream")
    product_name: Mapped[str] = mapped_column(Text, nullable=False)
    firmware_version: Mapped[str] = mapped_column(Text, default="1.0")
    manufacturer: Mapped[str] = mapped_column(Text, default="")
    is_archive: Mapped[bool] = mapped_column(Boolean, default=False)
    force: Mapped[bool] = mapped_column(Boolean, default=False)
    s3_upload_id: Mapped[str] = mapped_column(Text, default="")
    s3_key: Mapped[str] = mapped_column(Text, default="")
    parts_json: Mapped[str] = mapped_column(Text, default="[]")
    sha256_state: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(Text, default="uploading")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_default_upload_expires
    )

    __table_args__ = (
        Index("idx_upload_sessions_status", "status"),
        Index("idx_upload_sessions_expires", "expires_at"),
    )


class SuggestionTemplate(Base):
    """Question templates with {product} placeholder for empty-state suggestion chips."""
    __tablename__ = "suggestion_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str] = mapped_column(Text, nullable=False, default="default")
    lang: Mapped[str] = mapped_column(Text, nullable=False, default="en")
    template: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint("role", "lang", "template"),
        Index("idx_st_role_lang", "role", "lang", "is_active"),
    )


class UsageLog(Base):
    """Append-only billing audit log. Partitioned by month on created_at.

    Every billable event (chat completion, MCP search) writes exactly one row.
    This table is immutable — no UPDATE or DELETE in application code.
    """
    __tablename__ = "usage_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True,
        default=lambda: datetime.now(timezone.utc),
    )

    channel: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    request_id: Mapped[str] = mapped_column(Text, nullable=False)

    llm_provider: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)

    context_chunks: Mapped[int] = mapped_column(Integer, default=0)
    context_tokens: Mapped[int] = mapped_column(Integer, default=0)
    history_messages: Mapped[int] = mapped_column(Integer, default=0)
    query_tokens: Mapped[int] = mapped_column(Integer, default=0)
    history_tokens: Mapped[int] = mapped_column(Integer, default=0)
    system_prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)

    query_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    response_tokens: Mapped[int] = mapped_column(Integer, default=0)
    response_length: Mapped[int] = mapped_column(Integer, default=0)
    top_similarity: Mapped[float] = mapped_column(Float, default=0)

    product_filter: Mapped[str | None] = mapped_column(Text, nullable=True)
    version_filter: Mapped[str | None] = mapped_column(Text, nullable=True)

    duration_ms: Mapped[float] = mapped_column(Float, default=0)
    embedding_ms: Mapped[float] = mapped_column(Float, default=0)
    search_ms: Mapped[float] = mapped_column(Float, default=0)
    llm_ms: Mapped[float] = mapped_column(Float, default=0)

    cogs_usd: Mapped[Decimal] = mapped_column(Numeric(12, 8), default=Decimal("0"))
    charge_usd: Mapped[Decimal] = mapped_column(Numeric(12, 8), default=Decimal("0"))

    tenant_id = mapped_column(UUID(as_uuid=True), nullable=True)
    api_key_id = mapped_column(UUID(as_uuid=True), nullable=True)
    chat_session_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        Index("idx_usage_log_channel", "channel", "created_at"),
        Index("idx_usage_log_action", "action", "created_at"),
        Index("idx_usage_log_request", "request_id"),
        Index("idx_usage_log_api_key", "api_key_id", "created_at"),
        Index("idx_usage_log_chat_session", "chat_session_id", "created_at",
              postgresql_where=text("chat_session_id IS NOT NULL")),
    )


class McpRequestLog(Base):
    """Per-tool-call audit log for MCP requests. One row per MCP tool invocation."""
    __tablename__ = "mcp_request_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )

    tenant_id = mapped_column(UUID(as_uuid=True), nullable=False)
    api_key_id = mapped_column(UUID(as_uuid=True), nullable=False)
    request_id: Mapped[str] = mapped_column(Text, nullable=False)
    tool_name: Mapped[str] = mapped_column(Text, nullable=False)

    query_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_filter: Mapped[str | None] = mapped_column(Text, nullable=True)
    version_filter: Mapped[str | None] = mapped_column(Text, nullable=True)
    doc_type_filter: Mapped[str | None] = mapped_column(Text, nullable=True)

    result_count: Mapped[int] = mapped_column(Integer, default=0)
    top_similarity: Mapped[float] = mapped_column(Float, default=0)
    response_length: Mapped[int] = mapped_column(Integer, default=0)

    query_tokens: Mapped[int] = mapped_column(Integer, default=0)
    response_tokens: Mapped[int] = mapped_column(Integer, default=0)
    embedding_tokens: Mapped[int] = mapped_column(Integer, default=0)
    rerank_prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    rerank_completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    rerank_total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    rerank_model: Mapped[str | None] = mapped_column(Text, nullable=True)

    duration_ms: Mapped[float] = mapped_column(Float, default=0)
    embed_ms: Mapped[float] = mapped_column(Float, default=0)
    search_ms: Mapped[float] = mapped_column(Float, default=0)
    rerank_ms: Mapped[float] = mapped_column(Float, default=0)

    resolve_prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    resolve_completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    resolve_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolve_ms: Mapped[float] = mapped_column(Float, default=0)

    sources: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    cogs_usd: Mapped[Decimal] = mapped_column(Numeric(12, 8), default=Decimal("0"))
    charge_usd: Mapped[Decimal] = mapped_column(Numeric(12, 8), default=Decimal("0"))

    client_ip: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, default="ok")

    __table_args__ = (
        Index("idx_mcp_req_log_tenant", "tenant_id", "created_at"),
        Index("idx_mcp_req_log_api_key", "api_key_id", "created_at"),
        Index("idx_mcp_req_log_tool", "tool_name", "created_at"),
        Index("idx_mcp_req_log_request", "request_id"),
    )


# ---------------------------------------------------------------------------
# RBAC models
# ---------------------------------------------------------------------------

class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    permissions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    tenant_links: Mapped[list["TenantRole"]] = relationship(
        back_populates="role", cascade="all, delete-orphan",
    )
    prompt_overrides: Mapped[list["PromptTemplate"]] = relationship(
        back_populates="role", cascade="all, delete-orphan",
    )


class TenantRole(Base):
    __tablename__ = "tenant_roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), nullable=False,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )

    tenant: Mapped["Tenant"] = relationship()
    role: Mapped["Role"] = relationship(back_populates="tenant_links")

    __table_args__ = (
        UniqueConstraint("tenant_id", "role_id"),
        Index("idx_tenant_roles_tenant", "tenant_id"),
    )


class RagEvalRun(Base):
    __tablename__ = "rag_eval_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(Text, default="running")
    triggered_by: Mapped[str] = mapped_column(Text, default="")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    progress_stage: Mapped[str] = mapped_column(Text, default="")

    sample_size: Mapped[int] = mapped_column(Integer, default=50)
    eval_model: Mapped[str] = mapped_column(Text, default="")

    context_precision: Mapped[float | None] = mapped_column(Float, nullable=True)
    mrr: Mapped[float | None] = mapped_column(Float, nullable=True)
    empty_retrieval_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    similarity_p50: Mapped[float | None] = mapped_column(Float, nullable=True)
    similarity_p75: Mapped[float | None] = mapped_column(Float, nullable=True)
    similarity_p90: Mapped[float | None] = mapped_column(Float, nullable=True)
    search_latency_p50_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    search_latency_p95_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    faithfulness: Mapped[float | None] = mapped_column(Float, nullable=True)
    answer_relevance: Mapped[float | None] = mapped_column(Float, nullable=True)
    feedback_positive_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    no_answer_rate: Mapped[float | None] = mapped_column(Float, nullable=True)

    vector_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vector_search_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    hnsw_index_size_mb: Mapped[float | None] = mapped_column(Float, nullable=True)
    e2e_latency_p50_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    e2e_latency_p95_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    metrics_by_query_type: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    metrics_by_product: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("idx_rag_eval_runs_status", "status"),
        Index("idx_rag_eval_runs_started", "started_at"),
    )


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    query_type: Mapped[str] = mapped_column(Text, nullable=False)
    role_id: Mapped[int | None] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), nullable=True,
    )
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("prompt_templates.id", ondelete="SET NULL"), nullable=True,
    )
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    is_customized: Mapped[bool] = mapped_column(Boolean, default=False)
    body: Mapped[str] = mapped_column(Text, default="")
    classifier_hint: Mapped[str] = mapped_column(Text, default="")
    max_response_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rag_top_k: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    role: Mapped["Role | None"] = relationship(back_populates="prompt_overrides")
    parent: Mapped["PromptTemplate | None"] = relationship(remote_side=[id])

    __table_args__ = (
        UniqueConstraint("query_type", "role_id"),
        Index("idx_prompt_templates_query_type", "query_type"),
    )
