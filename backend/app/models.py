"""SQLAlchemy ORM models for Lexiro."""

from datetime import datetime, timedelta, timezone

from pgvector.sqlalchemy import Vector
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    manufacturer: Mapped[str] = mapped_column(Text, default="")
    model: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(Text, default="")
    slug: Mapped[str] = mapped_column(Text, nullable=False, default="")
    manufacturer_slug: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    firmware_versions: Mapped[list["FirmwareVersion"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("manufacturer", "model"),
        UniqueConstraint("manufacturer_slug", "slug"),
        Index("idx_products_slug", "manufacturer_slug", "slug"),
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


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
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
    detected_language: Mapped[str | None] = mapped_column(Text, nullable=True)

    source_container: Mapped[str | None] = mapped_column(Text, nullable=True)

    converted_s3_key: Mapped[str | None] = mapped_column(Text, nullable=True)

    extract_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    extract_prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    extract_completion_tokens: Mapped[int] = mapped_column(Integer, default=0)

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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    document: Mapped["Document"] = relationship(back_populates="chunks")

    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index"),
        Index("idx_chunks_document", "document_id"),
        Index("idx_chunks_doc_type", "doc_type"),
    )


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
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
    ) -> dict:
        """Convert to the debug_info dict expected by the frontend."""
        return {
            "session_id": self.session_id,
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
            "history_messages": self.history_messages,
            "prompt_messages": self.prompt_messages,
            "embedding_model": self.embedding_model,
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
        }


class DocumentUsageLog(Base):
    """Per-document usage attribution for author remuneration.

    Each row represents one chunk from a specific document that was included
    in a RAG response context. Enables proportional revenue sharing based on
    context_tokens contributed by each document.
    """
    __tablename__ = "document_usage_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
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
    )


class SharedLink(Base):
    __tablename__ = "shared_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token: Mapped[str] = mapped_column(Text, unique=True, index=True, nullable=False)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
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

    session: Mapped["ChatSession"] = relationship()

    __table_args__ = (
        Index("idx_shared_links_token", "token"),
        Index("idx_shared_links_session", "session_id"),
    )


class SearchAnalytics(Base):
    __tablename__ = "search_analytics"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
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

    __table_args__ = (
        Index("idx_usage_log_channel", "channel", "created_at"),
        Index("idx_usage_log_action", "action", "created_at"),
        Index("idx_usage_log_request", "request_id"),
    )
