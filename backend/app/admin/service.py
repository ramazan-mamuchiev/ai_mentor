"""Admin business logic — SQL queries for platform management."""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ChatMessage,
    ChatMessageAnalytics,
    ChatSession,
    Document,
    Product,
    SearchAnalytics,
    Tenant,
    UsageLog,
)


# ---------------------------------------------------------------------------
# Tenants
# ---------------------------------------------------------------------------

async def list_tenants(
    session: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 50,
    search: str | None = None,
    role: str | None = None,
    tier: str | None = None,
    is_active: bool | None = None,
) -> tuple[list[dict], int]:
    base = select(Tenant)
    count_q = select(func.count()).select_from(Tenant)

    if search:
        like = f"%{search}%"
        base = base.where(Tenant.email.ilike(like) | Tenant.name.ilike(like))
        count_q = count_q.where(Tenant.email.ilike(like) | Tenant.name.ilike(like))
    if role:
        base = base.where(Tenant.role == role)
        count_q = count_q.where(Tenant.role == role)
    if tier:
        base = base.where(Tenant.tier == tier)
        count_q = count_q.where(Tenant.tier == tier)
    if is_active is not None:
        base = base.where(Tenant.is_active == is_active)
        count_q = count_q.where(Tenant.is_active == is_active)

    total = await session.scalar(count_q) or 0

    rows = (await session.execute(
        base.order_by(Tenant.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )).scalars().all()

    items = []
    for t in rows:
        doc_count = await session.scalar(
            select(func.count()).select_from(Document).where(Document.tenant_id == t.id)
        ) or 0
        sess_count = await session.scalar(
            select(func.count()).select_from(ChatSession).where(ChatSession.tenant_id == t.id)
        ) or 0
        items.append({
            "id": t.id, "email": t.email, "name": t.name, "slug": t.slug,
            "tier": t.tier, "role": t.role, "is_active": t.is_active,
            "email_verified": t.email_verified,
            "created_at": t.created_at, "updated_at": t.updated_at,
            "documents_count": doc_count, "sessions_count": sess_count,
        })

    return items, total


async def get_tenant_detail(
    session: AsyncSession, tenant_id: uuid.UUID,
) -> dict | None:
    t = await session.get(Tenant, tenant_id)
    if not t:
        return None

    doc_count = await session.scalar(
        select(func.count()).select_from(Document).where(Document.tenant_id == t.id)
    ) or 0
    sess_count = await session.scalar(
        select(func.count()).select_from(ChatSession).where(ChatSession.tenant_id == t.id)
    ) or 0

    from app.models import ApiKey
    keys_count = await session.scalar(
        select(func.count()).select_from(ApiKey).where(ApiKey.tenant_id == t.id)
    ) or 0

    since = datetime.now(timezone.utc) - timedelta(days=30)
    usage = (await session.execute(text(
        "SELECT COUNT(*) AS cnt, COALESCE(SUM(total_tokens),0) AS tokens, "
        "COALESCE(SUM(charge_usd),0) AS charge "
        "FROM usage_log WHERE tenant_id = :tid AND created_at >= :since"
    ), {"tid": t.id, "since": since})).mappings().one()

    return {
        "id": t.id, "email": t.email, "name": t.name, "slug": t.slug,
        "tier": t.tier, "role": t.role, "is_active": t.is_active,
        "email_verified": t.email_verified,
        "created_at": t.created_at, "updated_at": t.updated_at,
        "documents_count": doc_count, "sessions_count": sess_count,
        "api_keys_count": keys_count,
        "total_tokens": int(usage["tokens"]),
        "total_requests": int(usage["cnt"]),
        "total_charge_usd": str(usage["charge"]),
    }


async def patch_tenant(
    session: AsyncSession, tenant_id: uuid.UUID,
    *, role: str | None = None, tier: str | None = None, is_active: bool | None = None,
) -> dict | None:
    t = await session.get(Tenant, tenant_id)
    if not t:
        return None
    if role is not None:
        t.role = role
    if tier is not None:
        t.tier = tier
    if is_active is not None:
        t.is_active = is_active
    session.add(t)
    await session.commit()
    await session.refresh(t)
    return await get_tenant_detail(session, tenant_id)


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

async def list_documents_admin(
    session: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 50,
    status_filter: str | None = None,
    tenant_id: uuid.UUID | None = None,
    search: str | None = None,
) -> tuple[list[dict], int]:
    base = (
        select(
            Document,
            Tenant.email.label("tenant_email"),
            Product.name.label("product_name"),
            Product.manufacturer.label("manufacturer"),
        )
        .outerjoin(Tenant, Document.tenant_id == Tenant.id)
        .outerjoin(Product, Document.product_id == Product.id)
    )
    count_q = select(func.count()).select_from(Document)

    if status_filter:
        base = base.where(Document.status == status_filter)
        count_q = count_q.where(Document.status == status_filter)
    if tenant_id:
        base = base.where(Document.tenant_id == tenant_id)
        count_q = count_q.where(Document.tenant_id == tenant_id)
    if search:
        like = f"%{search}%"
        base = base.where(Document.title.ilike(like) | Document.original_filename.ilike(like))
        count_q = count_q.where(Document.title.ilike(like) | Document.original_filename.ilike(like))

    total = await session.scalar(count_q) or 0

    rows = (await session.execute(
        base.order_by(Document.uploaded_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )).all()

    items = []
    for row in rows:
        doc = row[0]
        items.append({
            "id": doc.id, "tenant_id": doc.tenant_id,
            "tenant_email": row.tenant_email,
            "product_name": row.product_name,
            "manufacturer": row.manufacturer,
            "title": doc.title, "original_filename": doc.original_filename,
            "format": doc.format, "status": doc.status,
            "file_size_bytes": doc.file_size_bytes,
            "total_chunks": doc.total_chunks,
            "error_message": doc.error_message,
            "uploaded_at": doc.uploaded_at, "indexed_at": doc.indexed_at,
        })

    return items, total


async def get_document_admin(session: AsyncSession, doc_id: int) -> dict | None:
    row = (await session.execute(
        select(
            Document,
            Tenant.email.label("tenant_email"),
            Product.name.label("product_name"),
            Product.manufacturer.label("manufacturer"),
        )
        .outerjoin(Tenant, Document.tenant_id == Tenant.id)
        .outerjoin(Product, Document.product_id == Product.id)
        .where(Document.id == doc_id)
    )).one_or_none()

    if not row:
        return None

    doc = row[0]
    return {
        "id": doc.id, "tenant_id": doc.tenant_id,
        "tenant_email": row.tenant_email,
        "product_name": row.product_name,
        "manufacturer": row.manufacturer,
        "title": doc.title, "original_filename": doc.original_filename,
        "format": doc.format, "status": doc.status,
        "file_size_bytes": doc.file_size_bytes,
        "total_chunks": doc.total_chunks,
        "error_message": doc.error_message,
        "uploaded_at": doc.uploaded_at, "indexed_at": doc.indexed_at,
        "s3_key": doc.s3_key,
        "source_hash": doc.source_hash,
        "embedding_model": doc.embedding_model,
        "embedding_dims": doc.embedding_dims,
        "ingest_duration_ms": doc.ingest_duration_ms,
        "total_tokens": doc.total_tokens,
        "rag_hit_count": doc.rag_hit_count,
        "rag_avg_similarity": doc.rag_avg_similarity,
    }


async def patch_document_admin(
    session: AsyncSession, doc_id: int, *, status: str | None = None,
) -> dict | None:
    doc = await session.get(Document, doc_id)
    if not doc:
        return None
    if status is not None:
        doc.status = status
    session.add(doc)
    await session.commit()
    return await get_document_admin(session, doc_id)


async def delete_document_admin(session: AsyncSession, doc_id: int) -> bool:
    doc = await session.get(Document, doc_id)
    if not doc:
        return False
    await session.delete(doc)
    await session.commit()
    return True


# ---------------------------------------------------------------------------
# Chat Audit
# ---------------------------------------------------------------------------

async def list_chat_sessions_admin(
    session: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 50,
    tenant_id: uuid.UUID | None = None,
    search: str | None = None,
) -> tuple[list[dict], int]:
    base = (
        select(
            ChatSession,
            Tenant.email.label("tenant_email"),
            func.count(ChatMessage.id).label("messages_count"),
        )
        .outerjoin(Tenant, ChatSession.tenant_id == Tenant.id)
        .outerjoin(ChatMessage, ChatMessage.session_id == ChatSession.id)
        .group_by(ChatSession.id, Tenant.email)
    )
    count_q = select(func.count()).select_from(ChatSession)

    if tenant_id:
        base = base.where(ChatSession.tenant_id == tenant_id)
        count_q = count_q.where(ChatSession.tenant_id == tenant_id)
    if search:
        like = f"%{search}%"
        base = base.where(ChatSession.title.ilike(like))
        count_q = count_q.where(ChatSession.title.ilike(like))

    total = await session.scalar(count_q) or 0

    rows = (await session.execute(
        base.order_by(ChatSession.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )).all()

    items = []
    for row in rows:
        cs = row[0]
        items.append({
            "id": cs.id, "tenant_id": cs.tenant_id,
            "tenant_email": row.tenant_email,
            "title": cs.title,
            "product_filter": cs.product_filter,
            "messages_count": row.messages_count,
            "created_at": cs.created_at, "updated_at": cs.updated_at,
        })

    return items, total


async def get_chat_session_admin(session: AsyncSession, session_id: int) -> dict | None:
    row = (await session.execute(
        select(
            ChatSession,
            Tenant.email.label("tenant_email"),
        )
        .outerjoin(Tenant, ChatSession.tenant_id == Tenant.id)
        .where(ChatSession.id == session_id)
    )).one_or_none()

    if not row:
        return None

    cs = row[0]
    msgs = (await session.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
    )).scalars().all()

    msg_count = len(msgs)

    return {
        "id": cs.id, "tenant_id": cs.tenant_id,
        "tenant_email": row.tenant_email,
        "title": cs.title,
        "product_filter": cs.product_filter,
        "messages_count": msg_count,
        "created_at": cs.created_at, "updated_at": cs.updated_at,
        "messages": [
            {
                "id": m.id, "role": m.role, "content": m.content,
                "sources": m.sources, "duration_ms": m.duration_ms,
                "feedback": m.feedback, "created_at": m.created_at,
            }
            for m in msgs
        ],
    }


async def search_chat_messages(
    session: AsyncSession,
    *,
    query: str,
    limit: int = 50,
) -> tuple[list[dict], int]:
    like = f"%{query}%"

    count_q = (
        select(func.count())
        .select_from(ChatMessage)
        .where(ChatMessage.content.ilike(like))
    )
    total = await session.scalar(count_q) or 0

    rows = (await session.execute(
        select(
            ChatMessage,
            Tenant.email.label("tenant_email"),
        )
        .join(ChatSession, ChatMessage.session_id == ChatSession.id)
        .outerjoin(Tenant, ChatSession.tenant_id == Tenant.id)
        .where(ChatMessage.content.ilike(like))
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    )).all()

    items = [
        {
            "message_id": row[0].id,
            "session_id": row[0].session_id,
            "role": row[0].role,
            "content": row[0].content[:500],
            "tenant_email": row.tenant_email,
            "created_at": row[0].created_at,
        }
        for row in rows
    ]
    return items, total


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

async def get_platform_overview(session: AsyncSession) -> dict:
    total_tenants = await session.scalar(select(func.count()).select_from(Tenant)) or 0
    active_tenants = await session.scalar(
        select(func.count()).select_from(Tenant).where(Tenant.is_active.is_(True))
    ) or 0

    total_docs = await session.scalar(select(func.count()).select_from(Document)) or 0
    docs_indexed = await session.scalar(
        select(func.count()).select_from(Document).where(Document.status == "ready")
    ) or 0
    docs_pending = await session.scalar(
        select(func.count()).select_from(Document).where(Document.status.in_(["pending", "processing"]))
    ) or 0
    docs_error = await session.scalar(
        select(func.count()).select_from(Document).where(Document.status == "error")
    ) or 0

    total_sessions = await session.scalar(select(func.count()).select_from(ChatSession)) or 0
    total_messages = await session.scalar(select(func.count()).select_from(ChatMessage)) or 0

    since = datetime.now(timezone.utc) - timedelta(days=30)
    usage = (await session.execute(text(
        "SELECT COUNT(*) AS cnt, COALESCE(SUM(total_tokens),0) AS tokens, "
        "COALESCE(SUM(charge_usd),0) AS charge "
        "FROM usage_log WHERE created_at >= :since"
    ), {"since": since})).mappings().one()

    return {
        "total_tenants": total_tenants,
        "active_tenants": active_tenants,
        "total_documents": total_docs,
        "documents_indexed": docs_indexed,
        "documents_pending": docs_pending,
        "documents_error": docs_error,
        "total_sessions": total_sessions,
        "total_messages": total_messages,
        "total_tokens_30d": int(usage["tokens"]),
        "total_requests_30d": int(usage["cnt"]),
        "total_charge_usd_30d": str(usage["charge"]),
    }


async def get_usage_stats(session: AsyncSession, days: int = 30) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (await session.execute(text(
        "SELECT DATE(created_at) AS d, COUNT(*) AS cnt, "
        "COALESCE(SUM(total_tokens),0) AS tokens, "
        "COALESCE(SUM(charge_usd),0) AS charge "
        "FROM usage_log WHERE created_at >= :since "
        "GROUP BY DATE(created_at) ORDER BY d"
    ), {"since": since})).mappings().all()

    return [
        {"date": str(r["d"]), "requests": int(r["cnt"]),
         "tokens": int(r["tokens"]), "charge_usd": str(r["charge"])}
        for r in rows
    ]


async def get_model_stats(session: AsyncSession, days: int = 30) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (await session.execute(
        select(
            ChatMessageAnalytics.model,
            ChatMessageAnalytics.llm_provider,
            func.count().label("request_count"),
            func.sum(ChatMessageAnalytics.llm_total_tokens).label("total_tokens"),
            func.avg(ChatMessageAnalytics.total_ms).label("avg_total_ms"),
        )
        .where(ChatMessageAnalytics.created_at >= since)
        .group_by(ChatMessageAnalytics.model, ChatMessageAnalytics.llm_provider)
        .order_by(func.count().desc())
    )).all()

    return [
        {
            "model": r.model, "provider": r.llm_provider,
            "request_count": r.request_count,
            "total_tokens": int(r.total_tokens or 0),
            "avg_total_ms": round(float(r.avg_total_ms or 0), 1),
        }
        for r in rows
    ]


async def get_ingestion_stats(session: AsyncSession) -> dict:
    total = await session.scalar(
        select(func.count()).select_from(Document).where(Document.status == "ready")
    ) or 0
    avg_dur = await session.scalar(
        select(func.avg(Document.ingest_duration_ms)).where(Document.status == "ready")
    )
    total_chunks = await session.scalar(
        select(func.sum(Document.total_chunks)).where(Document.status == "ready")
    ) or 0
    pending = await session.scalar(
        select(func.count()).select_from(Document).where(Document.status.in_(["pending", "processing"]))
    ) or 0
    errors = await session.scalar(
        select(func.count()).select_from(Document).where(Document.status == "error")
    ) or 0

    error_rows = (await session.execute(
        select(Document.error_message, func.count().label("cnt"))
        .where(Document.status == "error", Document.error_message.isnot(None))
        .group_by(Document.error_message)
        .order_by(func.count().desc())
        .limit(10)
    )).all()

    return {
        "total_ingested": total,
        "avg_duration_ms": round(float(avg_dur), 1) if avg_dur else None,
        "total_chunks": int(total_chunks),
        "pending_count": pending,
        "error_count": errors,
        "top_errors": [
            {"message": r.error_message[:200], "count": r.cnt}
            for r in error_rows
        ],
    }


async def get_search_stats(session: AsyncSession, days: int = 30) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=days)

    total = await session.scalar(
        select(func.count()).select_from(SearchAnalytics).where(SearchAnalytics.created_at >= since)
    ) or 0
    avg_sim = await session.scalar(
        select(func.avg(SearchAnalytics.top_similarity)).where(SearchAnalytics.created_at >= since)
    )
    avg_dur = await session.scalar(
        select(func.avg(SearchAnalytics.duration_ms)).where(SearchAnalytics.created_at >= since)
    )
    zero_results = await session.scalar(
        select(func.count()).select_from(SearchAnalytics)
        .where(SearchAnalytics.created_at >= since, SearchAnalytics.result_count == 0)
    ) or 0

    top_queries = (await session.execute(
        select(SearchAnalytics.query, func.count().label("cnt"))
        .where(SearchAnalytics.created_at >= since)
        .group_by(SearchAnalytics.query)
        .order_by(func.count().desc())
        .limit(20)
    )).all()

    return {
        "total_searches": total,
        "avg_similarity": round(float(avg_sim), 4) if avg_sim else None,
        "avg_duration_ms": round(float(avg_dur), 1) if avg_dur else None,
        "top_queries": [{"query": r.query[:200], "count": r.cnt} for r in top_queries],
        "zero_result_count": zero_results,
    }
