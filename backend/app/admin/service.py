"""Admin business logic — SQL queries for platform management."""

import asyncio
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone

import psutil
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import (
    ApiKey,
    ChatMessage,
    ChatMessageAnalytics,
    ChatSession,
    Chunk,
    Document,
    DocumentUsageLog,
    FirmwareVersion,
    Product,
    PromptTemplate,
    Role,
    SearchAnalytics,
    SharedLink,
    Tenant,
    TenantRole,
    UsageLog,
)

_logger = logging.getLogger(__name__)

_s3_cache: dict = {"ts": 0.0, "size": 0, "count": 0}
_S3_CACHE_TTL = 60.0
_process_start = time.time()


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
            FirmwareVersion.version.label("firmware_version"),
        )
        .outerjoin(Tenant, Document.tenant_id == Tenant.id)
        .outerjoin(Product, Document.product_id == Product.id)
        .outerjoin(FirmwareVersion, Document.firmware_version_id == FirmwareVersion.id)
    )
    count_base = (
        select(func.count())
        .select_from(Document)
        .outerjoin(Tenant, Document.tenant_id == Tenant.id)
        .outerjoin(Product, Document.product_id == Product.id)
    )

    if status_filter:
        base = base.where(Document.status == status_filter)
        count_base = count_base.where(Document.status == status_filter)
    if tenant_id:
        base = base.where(Document.tenant_id == tenant_id)
        count_base = count_base.where(Document.tenant_id == tenant_id)
    if search:
        like = f"%{search}%"
        search_cond = (
            Document.title.ilike(like)
            | Document.original_filename.ilike(like)
            | Tenant.email.ilike(like)
            | Product.name.ilike(like)
            | Product.manufacturer.ilike(like)
        )
        base = base.where(search_cond)
        count_base = count_base.where(search_cond)

    total = await session.scalar(count_base) or 0

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
            "firmware_version": row.firmware_version,
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
    created_after: datetime | None = None,
    created_before: datetime | None = None,
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
    if created_after:
        base = base.where(ChatSession.created_at >= created_after)
        count_q = count_q.where(ChatSession.created_at >= created_after)
    if created_before:
        base = base.where(ChatSession.created_at <= created_before)
        count_q = count_q.where(ChatSession.created_at <= created_before)

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
            "id": str(cs.uuid), "tenant_id": cs.tenant_id,
            "tenant_email": row.tenant_email,
            "title": cs.title,
            "product_filter": cs.product_filter,
            "messages_count": row.messages_count,
            "created_at": cs.created_at, "updated_at": cs.updated_at,
        })

    return items, total


async def get_chat_session_admin(session: AsyncSession, session_uuid) -> dict | None:
    import uuid as _uuid
    row = (await session.execute(
        select(
            ChatSession,
            Tenant.email.label("tenant_email"),
        )
        .outerjoin(Tenant, ChatSession.tenant_id == Tenant.id)
        .where(ChatSession.uuid == session_uuid)
    )).one_or_none()

    if not row:
        return None

    cs = row[0]
    msgs = (await session.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == cs.id)
        .order_by(ChatMessage.created_at)
    )).scalars().all()

    msg_ids = [m.id for m in msgs if m.role == "assistant"]
    analytics_map: dict[int, ChatMessageAnalytics] = {}
    if msg_ids:
        analytics_rows = (await session.execute(
            select(ChatMessageAnalytics)
            .where(ChatMessageAnalytics.message_id.in_(msg_ids))
        )).scalars().all()
        analytics_map = {a.message_id: a for a in analytics_rows}

    msg_count = len(msgs)

    return {
        "id": str(cs.uuid), "tenant_id": cs.tenant_id,
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
                "debug": analytics_map[m.id].to_debug_dict(
                    product_filter=cs.product_filter,
                    session_uuid=str(cs.uuid),
                ) if m.id in analytics_map else None,
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
            ChatSession.uuid.label("session_uuid"),
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
            "session_id": str(row.session_uuid),
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

    total_chunks = await session.scalar(select(func.count()).select_from(Chunk)) or 0
    total_api_keys = await session.scalar(select(func.count()).select_from(ApiKey)) or 0
    total_shared_links = await session.scalar(select(func.count()).select_from(SharedLink)) or 0
    total_prompts = await session.scalar(select(func.count()).select_from(PromptTemplate)) or 0
    customized_prompts = await session.scalar(
        select(func.count()).select_from(PromptTemplate).where(PromptTemplate.is_customized.is_(True))
    ) or 0

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
        "total_chunks": total_chunks,
        "total_api_keys": total_api_keys,
        "total_shared_links": total_shared_links,
        "total_prompts": total_prompts,
        "customized_prompts": customized_prompts,
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


# ---------------------------------------------------------------------------
# Extended Stats
# ---------------------------------------------------------------------------

async def get_chat_stats(session: AsyncSession, days: int = 30) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=days)

    total_msgs = await session.scalar(
        select(func.count()).select_from(ChatMessage)
        .where(ChatMessage.role == "assistant", ChatMessage.created_at >= since)
    ) or 0

    positive = await session.scalar(
        select(func.count()).select_from(ChatMessage)
        .where(ChatMessage.created_at >= since, ChatMessage.feedback == "positive")
    ) or 0
    negative = await session.scalar(
        select(func.count()).select_from(ChatMessage)
        .where(ChatMessage.created_at >= since, ChatMessage.feedback == "negative")
    ) or 0
    rated = positive + negative

    qt_rows = (await session.execute(
        select(
            ChatMessageAnalytics.query_type,
            func.count().label("cnt"),
        )
        .where(ChatMessageAnalytics.created_at >= since, ChatMessageAnalytics.query_type.isnot(None))
        .group_by(ChatMessageAnalytics.query_type)
        .order_by(func.count().desc())
    )).all()
    qt_total = sum(r.cnt for r in qt_rows) or 1

    timing = (await session.execute(
        select(
            func.avg(ChatMessageAnalytics.total_ms),
            func.avg(ChatMessageAnalytics.rag_ms),
            func.avg(ChatMessageAnalytics.llm_ms),
            func.avg(ChatMessageAnalytics.search_ms),
            func.avg(ChatMessageAnalytics.first_token_ms),
            func.avg(ChatMessageAnalytics.tokens_per_sec),
        ).where(ChatMessageAnalytics.created_at >= since)
    )).one()

    timing_daily = (await session.execute(text(
        "SELECT DATE(created_at) AS d, "
        "AVG(total_ms) AS avg_total, AVG(llm_ms) AS avg_llm, AVG(rag_ms) AS avg_rag "
        "FROM chat_message_analytics WHERE created_at >= :since "
        "GROUP BY DATE(created_at) ORDER BY d"
    ), {"since": since})).mappings().all()

    models = await get_model_stats(session, days=days)

    avg_msgs = await session.scalar(text(
        "SELECT AVG(cnt) FROM ("
        "  SELECT COUNT(*) AS cnt FROM chat_messages cm "
        "  JOIN chat_sessions cs ON cm.session_id = cs.id "
        "  WHERE cs.created_at >= :since GROUP BY cs.id"
        ") sub"
    ), {"since": since})

    return {
        "feedback": {
            "total_messages": total_msgs,
            "rated_count": rated,
            "positive": positive,
            "negative": negative,
            "positive_rate": round(positive / rated * 100, 1) if rated > 0 else None,
        },
        "query_types": [
            {"query_type": r.query_type, "count": r.cnt, "pct": round(r.cnt / qt_total * 100, 1)}
            for r in qt_rows
        ],
        "response_time": {
            "avg_total_ms": round(float(timing[0]), 1) if timing[0] else None,
            "avg_rag_ms": round(float(timing[1]), 1) if timing[1] else None,
            "avg_llm_ms": round(float(timing[2]), 1) if timing[2] else None,
            "avg_search_ms": round(float(timing[3]), 1) if timing[3] else None,
            "avg_first_token_ms": round(float(timing[4]), 1) if timing[4] else None,
            "avg_tokens_per_sec": round(float(timing[5]), 1) if timing[5] else None,
            "daily": [
                {"date": str(r["d"]), "avg_total": round(float(r["avg_total"] or 0), 1),
                 "avg_llm": round(float(r["avg_llm"] or 0), 1),
                 "avg_rag": round(float(r["avg_rag"] or 0), 1)}
                for r in timing_daily
            ],
        },
        "models": models,
        "avg_messages_per_session": round(float(avg_msgs), 1) if avg_msgs else None,
        "error_rate": await _get_error_rate(session, since),
    }


async def _get_error_rate(session: AsyncSession, since: datetime) -> dict:
    total = await session.scalar(
        select(func.count()).select_from(ChatMessageAnalytics)
        .where(ChatMessageAnalytics.created_at >= since)
    ) or 0
    errors = await session.scalar(
        select(func.count()).select_from(ChatMessageAnalytics)
        .where(
            ChatMessageAnalytics.created_at >= since,
            ChatMessageAnalytics.finish_reason.notin_(["stop", "STOP", None, ""]),
        )
    ) or 0
    return {
        "total": total,
        "errors": errors,
        "rate": round(errors / total * 100, 1) if total > 0 else 0.0,
    }


async def get_document_stats(session: AsyncSession, days: int = 30) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=days)

    total = await session.scalar(select(func.count()).select_from(Document)) or 0
    avg_size = await session.scalar(select(func.avg(Document.file_size_bytes)))
    avg_chunks = await session.scalar(
        select(func.avg(Document.total_chunks)).where(Document.status == "ready")
    )

    uploads_daily = (await session.execute(text(
        "SELECT DATE(uploaded_at) AS d, COUNT(*) AS cnt "
        "FROM documents WHERE uploaded_at >= :since "
        "GROUP BY DATE(uploaded_at) ORDER BY d"
    ), {"since": since})).mappings().all()

    top_products = (await session.execute(
        select(Product.name, Product.manufacturer, func.count(Document.id).label("cnt"))
        .join(Document, Document.product_id == Product.id)
        .group_by(Product.id, Product.name, Product.manufacturer)
        .order_by(func.count(Document.id).desc())
        .limit(10)
    )).all()

    format_rows = (await session.execute(
        select(Document.format, func.count().label("cnt"))
        .group_by(Document.format)
        .order_by(func.count().desc())
    )).all()
    fmt_total = sum(r.cnt for r in format_rows) or 1

    top_docs = (await session.execute(
        select(
            DocumentUsageLog.document_id,
            Document.title,
            Product.name.label("product_name"),
            func.count(DocumentUsageLog.id).label("usage_count"),
            func.sum(DocumentUsageLog.context_tokens).label("ctx_tokens"),
            func.sum(DocumentUsageLog.charge_usd).label("charge"),
        )
        .join(Document, Document.id == DocumentUsageLog.document_id)
        .outerjoin(Product, Product.id == Document.product_id)
        .where(DocumentUsageLog.created_at >= since)
        .group_by(DocumentUsageLog.document_id, Document.title, Product.name)
        .order_by(func.count(DocumentUsageLog.id).desc())
        .limit(10)
    )).all()

    used_ids_subq = select(DocumentUsageLog.document_id).distinct().subquery()
    unused = await session.scalar(
        select(func.count()).select_from(Document)
        .where(Document.status == "ready", ~Document.id.in_(select(used_ids_subq)))
    ) or 0

    return {
        "total": total,
        "avg_size_bytes": round(float(avg_size), 0) if avg_size else None,
        "avg_chunks": round(float(avg_chunks), 1) if avg_chunks else None,
        "uploads_daily": [{"date": str(r["d"]), "count": r["cnt"]} for r in uploads_daily],
        "top_products": [
            {"name": f"{r.manufacturer} / {r.name}" if r.manufacturer else r.name, "count": r.cnt}
            for r in top_products
        ],
        "top_documents": [
            {
                "document_id": r.document_id, "title": r.title or "—",
                "product_name": r.product_name,
                "usage_count": r.usage_count,
                "context_tokens": int(r.ctx_tokens or 0),
                "charge_usd": str(r.charge or 0),
            }
            for r in top_docs
        ],
        "formats": [
            {"format": r.format, "count": r.cnt, "pct": round(r.cnt / fmt_total * 100, 1)}
            for r in format_rows
        ],
        "unused_count": unused,
        "total_chunks": await session.scalar(select(func.count()).select_from(Chunk)) or 0,
        "total_size_bytes": await session.scalar(select(func.sum(Document.file_size_bytes))) or 0,
        "used_chunks_count": await session.scalar(
            select(func.count(func.distinct(DocumentUsageLog.chunk_id)))
            .where(DocumentUsageLog.chunk_id.isnot(None))
        ) or 0,
    }


async def get_extended_search_stats(session: AsyncSession, days: int = 30) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    base = await get_search_stats(session, days=days)

    source_rows = (await session.execute(
        select(SearchAnalytics.source, func.count().label("cnt"))
        .where(SearchAnalytics.created_at >= since)
        .group_by(SearchAnalytics.source)
        .order_by(func.count().desc())
    )).all()
    src_total = sum(r.cnt for r in source_rows) or 1

    daily = (await session.execute(text(
        "SELECT DATE(created_at) AS d, COUNT(*) AS cnt, "
        "AVG(top_similarity) AS avg_sim, "
        "SUM(CASE WHEN result_count = 0 THEN 1 ELSE 0 END) AS zero_cnt "
        "FROM search_analytics WHERE created_at >= :since "
        "GROUP BY DATE(created_at) ORDER BY d"
    ), {"since": since})).mappings().all()

    return {
        **base,
        "sources": [
            {"source": r.source, "count": r.cnt, "pct": round(r.cnt / src_total * 100, 1)}
            for r in source_rows
        ],
        "daily": [
            {"date": str(r["d"]), "count": r["cnt"],
             "avg_similarity": round(float(r["avg_sim"] or 0), 4),
             "zero_count": int(r["zero_cnt"] or 0)}
            for r in daily
        ],
    }


async def get_cost_stats(session: AsyncSession, days: int = 30) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=days)

    totals = (await session.execute(text(
        "SELECT COUNT(*) AS cnt, COALESCE(SUM(charge_usd),0) AS charge, "
        "COALESCE(SUM(cogs_usd),0) AS cogs "
        "FROM usage_log WHERE created_at >= :since"
    ), {"since": since})).mappings().one()

    active_tenants = await session.scalar(
        select(func.count(func.distinct(UsageLog.tenant_id)))
        .where(UsageLog.created_at >= since, UsageLog.tenant_id.isnot(None))
    ) or 1

    daily = (await session.execute(text(
        "SELECT DATE(created_at) AS d, "
        "COALESCE(SUM(charge_usd),0) AS charge, "
        "COALESCE(SUM(cogs_usd),0) AS cogs, "
        "COUNT(*) AS cnt "
        "FROM usage_log WHERE created_at >= :since "
        "GROUP BY DATE(created_at) ORDER BY d"
    ), {"since": since})).mappings().all()

    by_model = (await session.execute(text(
        "SELECT llm_model, llm_provider, "
        "COALESCE(SUM(charge_usd),0) AS charge, "
        "COALESCE(SUM(total_tokens),0) AS tokens, "
        "COUNT(*) AS cnt "
        "FROM usage_log WHERE created_at >= :since AND llm_model IS NOT NULL "
        "GROUP BY llm_model, llm_provider ORDER BY charge DESC"
    ), {"since": since})).mappings().all()

    by_channel = (await session.execute(text(
        "SELECT channel, "
        "COALESCE(SUM(charge_usd),0) AS charge, "
        "COUNT(*) AS cnt "
        "FROM usage_log WHERE created_at >= :since "
        "GROUP BY channel ORDER BY charge DESC"
    ), {"since": since})).mappings().all()

    total_charge = float(totals["charge"])
    total_cogs = float(totals["cogs"])
    day_count = max(len(daily), 1)
    avg_day = total_charge / day_count
    forecast = avg_day * 30

    return {
        "total_charge_usd": f"{total_charge:.8f}",
        "total_cogs_usd": f"{total_cogs:.8f}",
        "avg_per_day": f"{avg_day:.8f}",
        "avg_per_user": f"{total_charge / active_tenants:.8f}",
        "forecast_month_usd": f"{forecast:.8f}",
        "daily": [
            {"date": str(r["d"]), "charge_usd": str(r["charge"]),
             "cogs_usd": str(r["cogs"]), "requests": int(r["cnt"])}
            for r in daily
        ],
        "by_model": [
            {"model": r["llm_model"] or "—", "provider": r["llm_provider"],
             "total_charge_usd": str(r["charge"]),
             "total_tokens": int(r["tokens"]), "request_count": int(r["cnt"])}
            for r in by_model
        ],
        "by_channel": [
            {"channel": r["channel"], "total_charge_usd": str(r["charge"]),
             "request_count": int(r["cnt"])}
            for r in by_channel
        ],
        "top_api_keys": await _get_top_api_keys(session, since),
    }


async def _get_top_api_keys(session: AsyncSession, since: datetime) -> list[dict]:
    rows = (await session.execute(text(
        "SELECT ul.api_key_id, ak.key_prefix, t.email, "
        "COUNT(*) AS cnt, COALESCE(SUM(ul.charge_usd),0) AS charge "
        "FROM usage_log ul "
        "JOIN api_keys ak ON ak.id = ul.api_key_id "
        "JOIN tenants t ON t.id = ak.tenant_id "
        "WHERE ul.created_at >= :since AND ul.api_key_id IS NOT NULL "
        "GROUP BY ul.api_key_id, ak.key_prefix, t.email "
        "ORDER BY cnt DESC LIMIT 10"
    ), {"since": since})).mappings().all()
    return [
        {"key_prefix": r["key_prefix"], "email": r["email"],
         "request_count": int(r["cnt"]), "charge_usd": str(r["charge"])}
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------

async def list_roles(session: AsyncSession) -> list[dict]:
    result = await session.execute(
        select(
            Role,
            func.count(TenantRole.id).label("tenants_count"),
        )
        .outerjoin(TenantRole, TenantRole.role_id == Role.id)
        .group_by(Role.id)
        .order_by(Role.priority.desc(), Role.name)
    )
    rows = result.all()
    return [
        {
            "id": role.id,
            "slug": role.slug,
            "name": role.name,
            "description": role.description,
            "is_system": role.is_system,
            "priority": role.priority,
            "tenants_count": cnt,
            "created_at": role.created_at,
        }
        for role, cnt in rows
    ]


async def get_role_detail(session: AsyncSession, role_id: int) -> dict | None:
    result = await session.execute(
        select(
            Role,
            func.count(TenantRole.id).label("tenants_count"),
        )
        .outerjoin(TenantRole, TenantRole.role_id == Role.id)
        .where(Role.id == role_id)
        .group_by(Role.id)
    )
    row = result.one_or_none()
    if not row:
        return None
    role, cnt = row
    return {
        "id": role.id,
        "slug": role.slug,
        "name": role.name,
        "description": role.description,
        "is_system": role.is_system,
        "priority": role.priority,
        "permissions": role.permissions,
        "tenants_count": cnt,
        "created_at": role.created_at,
        "updated_at": role.updated_at,
    }


async def create_role(
    session: AsyncSession,
    *,
    slug: str,
    name: str,
    description: str = "",
    priority: int = 0,
    permissions: dict | None = None,
) -> Role:
    role = Role(
        slug=slug,
        name=name,
        description=description,
        is_system=False,
        priority=priority,
        permissions=permissions or {},
    )
    session.add(role)
    await session.commit()
    await session.refresh(role)
    return role


async def patch_role(
    session: AsyncSession,
    role_id: int,
    *,
    name: str | None = None,
    description: str | None = None,
    priority: int | None = None,
    permissions: dict | None = None,
) -> dict | None:
    result = await session.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()
    if not role:
        return None
    if name is not None:
        role.name = name
    if description is not None:
        role.description = description
    if priority is not None:
        role.priority = priority
    if permissions is not None:
        role.permissions = permissions
    session.add(role)
    await session.commit()
    return await get_role_detail(session, role_id)


async def delete_role(session: AsyncSession, role_id: int) -> bool:
    result = await session.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()
    if not role:
        return False
    if role.is_system:
        raise ValueError("Cannot delete system role")
    await session.delete(role)
    await session.commit()
    return True


async def get_tenant_roles(
    session: AsyncSession, tenant_id: uuid.UUID,
) -> list[dict]:
    result = await session.execute(
        select(TenantRole, Role)
        .join(Role, TenantRole.role_id == Role.id)
        .where(TenantRole.tenant_id == tenant_id)
        .order_by(Role.priority.desc())
    )
    return [
        {
            "id": tr.id,
            "role_id": role.id,
            "role_slug": role.slug,
            "role_name": role.name,
            "assigned_at": tr.assigned_at,
        }
        for tr, role in result.all()
    ]


async def assign_role_to_tenant(
    session: AsyncSession, tenant_id: uuid.UUID, role_id: int,
) -> dict:
    tenant_exists = await session.execute(
        select(Tenant.id).where(Tenant.id == tenant_id)
    )
    if not tenant_exists.scalar_one_or_none():
        raise ValueError("Tenant not found")

    role_exists = await session.execute(select(Role).where(Role.id == role_id))
    if not role_exists.scalar_one_or_none():
        raise ValueError("Role not found")

    existing = await session.execute(
        select(TenantRole).where(
            TenantRole.tenant_id == tenant_id,
            TenantRole.role_id == role_id,
        )
    )
    if existing.scalar_one_or_none():
        raise ValueError("Role already assigned")

    tr = TenantRole(tenant_id=tenant_id, role_id=role_id)
    session.add(tr)
    await session.commit()
    await session.refresh(tr)

    role = (await session.execute(select(Role).where(Role.id == role_id))).scalar_one()
    return {
        "id": tr.id,
        "role_id": role.id,
        "role_slug": role.slug,
        "role_name": role.name,
        "assigned_at": tr.assigned_at,
    }


async def unassign_role_from_tenant(
    session: AsyncSession, tenant_id: uuid.UUID, role_id: int,
) -> bool:
    result = await session.execute(
        select(TenantRole).where(
            TenantRole.tenant_id == tenant_id,
            TenantRole.role_id == role_id,
        )
    )
    tr = result.scalar_one_or_none()
    if not tr:
        return False
    await session.delete(tr)
    await session.commit()
    return True


# ---------------------------------------------------------------------------
# Prompt Templates
# ---------------------------------------------------------------------------

async def list_prompt_templates(session: AsyncSession) -> list[dict]:
    result = await session.execute(
        select(PromptTemplate, Role.slug.label("role_slug"))
        .outerjoin(Role, PromptTemplate.role_id == Role.id)
        .order_by(PromptTemplate.query_type, PromptTemplate.role_id.is_(None).desc())
    )
    return [
        {
            "id": pt.id,
            "query_type": pt.query_type,
            "role_id": pt.role_id,
            "role_slug": role_slug,
            "parent_id": pt.parent_id,
            "is_system": pt.is_system,
            "is_customized": pt.is_customized,
            "classifier_hint": pt.classifier_hint,
            "max_response_tokens": pt.max_response_tokens,
            "rag_top_k": pt.rag_top_k,
            "created_at": pt.created_at,
            "updated_at": pt.updated_at,
        }
        for pt, role_slug in result.all()
    ]


async def get_prompt_template(session: AsyncSession, prompt_id: int) -> dict | None:
    result = await session.execute(
        select(PromptTemplate, Role.slug.label("role_slug"))
        .outerjoin(Role, PromptTemplate.role_id == Role.id)
        .where(PromptTemplate.id == prompt_id)
    )
    row = result.one_or_none()
    if not row:
        return None
    pt, role_slug = row
    return {
        "id": pt.id,
        "query_type": pt.query_type,
        "role_id": pt.role_id,
        "role_slug": role_slug,
        "parent_id": pt.parent_id,
        "is_system": pt.is_system,
        "is_customized": pt.is_customized,
        "body": pt.body,
        "classifier_hint": pt.classifier_hint,
        "max_response_tokens": pt.max_response_tokens,
        "rag_top_k": pt.rag_top_k,
        "created_at": pt.created_at,
        "updated_at": pt.updated_at,
    }


async def create_prompt_template(
    session: AsyncSession,
    *,
    query_type: str,
    role_id: int | None = None,
    body: str = "",
    classifier_hint: str = "",
    max_response_tokens: int | None = None,
    rag_top_k: int | None = None,
) -> PromptTemplate:
    parent_id = None
    if role_id is not None:
        base = await session.execute(
            select(PromptTemplate).where(
                PromptTemplate.query_type == query_type,
                PromptTemplate.role_id.is_(None),
            )
        )
        base_pt = base.scalar_one_or_none()
        if base_pt:
            parent_id = base_pt.id

    pt = PromptTemplate(
        query_type=query_type,
        role_id=role_id,
        parent_id=parent_id,
        is_system=False,
        is_customized=True,
        body=body,
        classifier_hint=classifier_hint,
        max_response_tokens=max_response_tokens,
        rag_top_k=rag_top_k,
    )
    session.add(pt)
    await session.commit()
    await session.refresh(pt)
    return pt


async def patch_prompt_template(
    session: AsyncSession,
    prompt_id: int,
    *,
    body: str | None = None,
    classifier_hint: str | None = None,
    max_response_tokens: int | None = ...,
    rag_top_k: int | None = ...,
) -> dict | None:
    result = await session.execute(
        select(PromptTemplate).where(PromptTemplate.id == prompt_id)
    )
    pt = result.scalar_one_or_none()
    if not pt:
        return None
    if body is not None:
        pt.body = body
    if classifier_hint is not None:
        pt.classifier_hint = classifier_hint
    if max_response_tokens is not ...:
        pt.max_response_tokens = max_response_tokens
    if rag_top_k is not ...:
        pt.rag_top_k = rag_top_k
    pt.is_customized = True
    session.add(pt)
    await session.commit()
    return await get_prompt_template(session, prompt_id)


async def delete_prompt_template(session: AsyncSession, prompt_id: int) -> bool:
    result = await session.execute(
        select(PromptTemplate).where(PromptTemplate.id == prompt_id)
    )
    pt = result.scalar_one_or_none()
    if not pt:
        return False
    if pt.is_system:
        raise ValueError("Cannot delete system prompt template")
    await session.delete(pt)
    await session.commit()
    return True


async def preview_prompt_template(
    session: AsyncSession, prompt_id: int,
) -> dict | None:
    result = await session.execute(
        select(PromptTemplate).where(PromptTemplate.id == prompt_id)
    )
    pt = result.scalar_one_or_none()
    if not pt:
        return None

    body = pt.body
    hint = pt.classifier_hint
    max_tok = pt.max_response_tokens
    top_k = pt.rag_top_k

    if pt.parent_id:
        parent_res = await session.execute(
            select(PromptTemplate).where(PromptTemplate.id == pt.parent_id)
        )
        parent = parent_res.scalar_one_or_none()
        if parent:
            body = body or parent.body
            hint = hint or parent.classifier_hint
            max_tok = max_tok or parent.max_response_tokens
            top_k = top_k or parent.rag_top_k

    return {
        "query_type": pt.query_type,
        "resolved_body": body,
        "resolved_classifier_hint": hint,
        "resolved_max_response_tokens": max_tok,
        "resolved_rag_top_k": top_k,
    }


# ---------------------------------------------------------------------------
# System Monitor
# ---------------------------------------------------------------------------

def _collect_server_metrics() -> dict:
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.3),
        "cpu_count": psutil.cpu_count(logical=True) or 1,
        "ram_used_bytes": mem.used,
        "ram_total_bytes": mem.total,
        "ram_percent": mem.percent,
        "disk_used_bytes": disk.used,
        "disk_total_bytes": disk.total,
        "disk_percent": disk.percent,
        "uptime_sec": round(time.time() - _process_start, 1),
    }


async def _collect_pg_metrics(session: AsyncSession) -> dict:
    from app.database import engine

    pool = engine.pool

    db_size = await session.scalar(text(
        "SELECT pg_database_size(current_database())"
    )) or 0

    active_conn = await session.scalar(text(
        "SELECT count(*) FROM pg_stat_activity WHERE state = 'active'"
    )) or 0

    top_tables_rows = (await session.execute(text(
        "SELECT relname, pg_total_relation_size(c.oid) AS size "
        "FROM pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind = 'r' "
        "ORDER BY size DESC LIMIT 5"
    ))).all()

    return {
        "db_size_bytes": db_size,
        "db_active_connections": active_conn,
        "db_pool_size": pool.size(),
        "db_pool_checked_out": pool.checkedout(),
        "db_pool_overflow": pool.overflow(),
        "db_top_tables": [
            {"name": r[0], "size_bytes": r[1]} for r in top_tables_rows
        ],
    }


async def _collect_redis_metrics() -> dict:
    import redis.asyncio as aioredis

    r = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        info = await r.info("memory")
        used_memory = info.get("used_memory", 0)

        total_keys = await r.dbsize()

        q_celery = await r.llen("celery")
        q_monitoring = await r.llen("monitoring")

        tus_count = 0
        cursor = "0"
        while True:
            cursor, keys = await r.scan(cursor=cursor, match="tus:offset:*", count=100)
            tus_count += len(keys)
            if cursor == 0 or cursor == "0":
                break

        return {
            "redis_used_memory_bytes": used_memory,
            "redis_total_keys": total_keys,
            "redis_queue_celery": q_celery,
            "redis_queue_monitoring": q_monitoring,
            "tus_uploads_active": tus_count,
        }
    finally:
        await r.aclose()


async def _collect_s3_metrics() -> dict:
    now = time.time()
    if now - _s3_cache["ts"] < _S3_CACHE_TTL and _s3_cache["ts"] > 0:
        return {
            "s3_bucket_size_bytes": _s3_cache["size"],
            "s3_objects_count": _s3_cache["count"],
            "s3_quota_bytes": settings.storage_quota_gb * 1024 * 1024 * 1024,
        }

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _s3_bucket_stats_sync)

    _s3_cache["ts"] = now
    _s3_cache["size"] = result["size"]
    _s3_cache["count"] = result["count"]

    return {
        "s3_bucket_size_bytes": result["size"],
        "s3_objects_count": result["count"],
        "s3_quota_bytes": settings.storage_quota_gb * 1024 * 1024 * 1024,
    }


def _s3_bucket_stats_sync() -> dict:
    from app.s3 import _get_client

    client = _get_client()
    total_size = 0
    total_count = 0
    paginator = client.get_paginator("list_objects_v2")
    try:
        for page in paginator.paginate(Bucket=settings.s3_bucket):
            for obj in page.get("Contents", []):
                total_size += obj.get("Size", 0)
                total_count += 1
    except Exception:
        _logger.warning("S3 bucket stats collection failed", exc_info=True)

    return {"size": total_size, "count": total_count}


async def _collect_ingestion_metrics(session: AsyncSession, tus_count: int) -> dict:
    rows = (await session.execute(text(
        "SELECT status, count(*) FROM documents "
        "WHERE status IN ('pending', 'processing', 'error') "
        "GROUP BY status"
    ))).all()
    counts = {r[0]: r[1] for r in rows}

    since_24h = datetime.now(timezone.utc) - timedelta(hours=24)
    indexed_24h = await session.scalar(text(
        "SELECT count(*) FROM documents "
        "WHERE status = 'indexed' AND indexed_at >= :since"
    ), {"since": since_24h}) or 0
    docs_per_hour = round(indexed_24h / 24.0, 1)

    stale_threshold = datetime.now(timezone.utc) - timedelta(
        seconds=settings.reindex_doc_timeout_sec
    )
    stale_count = await session.scalar(text(
        "SELECT count(*) FROM documents "
        "WHERE status = 'processing' AND uploaded_at < :threshold"
    ), {"threshold": stale_threshold}) or 0

    return {
        "pending": counts.get("pending", 0),
        "processing": counts.get("processing", 0),
        "error": counts.get("error", 0),
        "docs_per_hour_24h": docs_per_hour,
        "stale_count": stale_count,
        "tus_uploads_active": tus_count,
    }


async def _collect_llm_metrics(session: AsyncSession) -> dict:
    since = datetime.now(timezone.utc) - timedelta(hours=1)

    row = (await session.execute(text(
        "SELECT "
        "  AVG(llm_ms) AS avg_ms, "
        "  SUM(CASE WHEN finish_reason = 'error' THEN 1 ELSE 0 END) AS errors, "
        "  SUM(CASE WHEN finish_reason = 'timeout' THEN 1 ELSE 0 END) AS timeouts "
        "FROM chat_message_analytics "
        "WHERE created_at >= :since"
    ), {"since": since})).mappings().one()

    provider = settings.llm_provider
    model = settings.openai_llm_model if provider == "openai" else settings.llm_model

    return {
        "provider": provider,
        "model": model,
        "avg_response_ms": round(row["avg_ms"], 1) if row["avg_ms"] else None,
        "errors_last_hour": int(row["errors"] or 0),
        "timeouts_last_hour": int(row["timeouts"] or 0),
    }


async def _collect_activity(session: AsyncSession) -> dict:
    from app.logging_config import active_requests_count

    since_5m = datetime.now(timezone.utc) - timedelta(minutes=5)

    online_users = await session.scalar(text(
        "SELECT count(DISTINCT tenant_id) FROM usage_log "
        "WHERE created_at >= :since"
    ), {"since": since_5m}) or 0

    active_chats = await session.scalar(text(
        "SELECT count(DISTINCT session_id) FROM chat_messages "
        "WHERE created_at >= :since"
    ), {"since": since_5m}) or 0

    return {
        "active_requests": active_requests_count,
        "online_users_5min": online_users,
        "active_chat_sessions_5min": active_chats,
    }


async def _collect_services_health() -> list[dict]:
    services = []

    async def _ping_db():
        from app.database import engine
        t0 = time.perf_counter()
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            ms = round((time.perf_counter() - t0) * 1000, 1)
            return {"name": "PostgreSQL", "status": "ok", "latency_ms": ms, "detail": None}
        except Exception as e:
            ms = round((time.perf_counter() - t0) * 1000, 1)
            return {"name": "PostgreSQL", "status": "error", "latency_ms": ms, "detail": str(e)[:200]}

    async def _ping_redis():
        import redis.asyncio as aioredis
        t0 = time.perf_counter()
        try:
            r = aioredis.from_url(settings.redis_url)
            await r.ping()
            await r.aclose()
            ms = round((time.perf_counter() - t0) * 1000, 1)
            return {"name": "Redis", "status": "ok", "latency_ms": ms, "detail": None}
        except Exception as e:
            ms = round((time.perf_counter() - t0) * 1000, 1)
            return {"name": "Redis", "status": "error", "latency_ms": ms, "detail": str(e)[:200]}

    async def _ping_s3():
        loop = asyncio.get_event_loop()
        t0 = time.perf_counter()
        try:
            ok = await loop.run_in_executor(None, _s3_health_sync)
            ms = round((time.perf_counter() - t0) * 1000, 1)
            return {"name": "S3/MinIO", "status": "ok" if ok else "error", "latency_ms": ms, "detail": None}
        except Exception as e:
            ms = round((time.perf_counter() - t0) * 1000, 1)
            return {"name": "S3/MinIO", "status": "error", "latency_ms": ms, "detail": str(e)[:200]}

    async def _ping_llm():
        from app.llm.client import check_health
        t0 = time.perf_counter()
        try:
            ok = await check_health()
            ms = round((time.perf_counter() - t0) * 1000, 1)
            provider = settings.llm_provider
            model = settings.openai_llm_model if provider == "openai" else settings.llm_model
            return {
                "name": f"LLM ({model})",
                "status": "ok" if ok else "error",
                "latency_ms": ms,
                "detail": None,
            }
        except Exception as e:
            ms = round((time.perf_counter() - t0) * 1000, 1)
            return {"name": "LLM", "status": "error", "latency_ms": ms, "detail": str(e)[:200]}

    services = await asyncio.gather(
        _ping_db(), _ping_redis(), _ping_s3(), _ping_llm()
    )
    return list(services)


def _s3_health_sync() -> bool:
    from app.s3 import check_health
    return check_health()


async def get_system_info(session: AsyncSession) -> dict:
    loop = asyncio.get_event_loop()

    server_fut = loop.run_in_executor(None, _collect_server_metrics)
    pg_fut = _collect_pg_metrics(session)
    redis_fut = _collect_redis_metrics()
    s3_fut = _collect_s3_metrics()
    llm_fut = _collect_llm_metrics(session)
    activity_fut = _collect_activity(session)
    health_fut = _collect_services_health()

    server, pg, redis_m, s3, llm, activity, health = await asyncio.gather(
        server_fut, pg_fut, redis_fut, s3_fut, llm_fut, activity_fut, health_fut,
    )

    ingestion = await _collect_ingestion_metrics(
        session, tus_count=redis_m.pop("tus_uploads_active", 0)
    )

    return {
        **server,
        **pg,
        **redis_m,
        **s3,
        "ingestion": ingestion,
        "llm": llm,
        **activity,
        "services": health,
    }


# ---------------------------------------------------------------------------
# MCP Audit
# ---------------------------------------------------------------------------

async def list_mcp_requests(
    session: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 50,
    tenant_id: str | None = None,
    api_key_id: str | None = None,
    tool_name: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> tuple[list[dict], int]:
    where = ["1=1"]
    params: dict = {}
    if tenant_id:
        where.append("m.tenant_id = :tenant_id")
        params["tenant_id"] = tenant_id
    if api_key_id:
        where.append("m.api_key_id = :api_key_id")
        params["api_key_id"] = api_key_id
    if tool_name:
        where.append("m.tool_name = :tool_name")
        params["tool_name"] = tool_name
    if date_from:
        where.append("m.created_at >= :date_from")
        params["date_from"] = date_from
    if date_to:
        where.append("m.created_at <= :date_to")
        params["date_to"] = date_to
    where_sql = " AND ".join(where)

    count_row = (await session.execute(
        text(f"SELECT COUNT(*) FROM mcp_request_log m WHERE {where_sql}"), params,
    )).scalar() or 0

    offset = (page - 1) * page_size
    rows = (await session.execute(text(f"""
        SELECT m.*, t.email AS tenant_email, ak.key_prefix
        FROM mcp_request_log m
        LEFT JOIN tenants t ON t.id = m.tenant_id
        LEFT JOIN api_keys ak ON ak.id = m.api_key_id
        WHERE {where_sql}
        ORDER BY m.created_at DESC
        LIMIT :limit OFFSET :offset
    """), {**params, "limit": page_size, "offset": offset})).mappings().all()

    items = [
        {
            "id": r["id"],
            "created_at": r["created_at"],
            "tenant_email": r["tenant_email"],
            "key_prefix": r["key_prefix"],
            "request_id": r["request_id"],
            "tool_name": r["tool_name"],
            "query_text": r["query_text"],
            "result_count": r["result_count"],
            "top_similarity": round(float(r["top_similarity"]), 4),
            "duration_ms": round(float(r["duration_ms"]), 1),
            "query_tokens": r["query_tokens"],
            "response_tokens": r["response_tokens"],
            "embedding_tokens": r["embedding_tokens"],
            "charge_usd": str(r["charge_usd"]),
            "status": r["status"],
        }
        for r in rows
    ]
    return items, int(count_row)


async def get_mcp_request_detail(session: AsyncSession, request_id: str) -> dict | None:
    row = (await session.execute(text("""
        SELECT m.*, t.email AS tenant_email, ak.key_prefix
        FROM mcp_request_log m
        LEFT JOIN tenants t ON t.id = m.tenant_id
        LEFT JOIN api_keys ak ON ak.id = m.api_key_id
        WHERE m.request_id = :request_id
        LIMIT 1
    """), {"request_id": request_id})).mappings().first()
    if not row:
        return None
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "tenant_id": str(row["tenant_id"]) if row["tenant_id"] else None,
        "api_key_id": str(row["api_key_id"]) if row["api_key_id"] else None,
        "tenant_email": row["tenant_email"],
        "key_prefix": row["key_prefix"],
        "request_id": row["request_id"],
        "tool_name": row["tool_name"],
        "query_text": row["query_text"],
        "product_filter": row["product_filter"],
        "version_filter": row["version_filter"],
        "doc_type_filter": row["doc_type_filter"],
        "result_count": row["result_count"],
        "top_similarity": round(float(row["top_similarity"]), 4),
        "response_length": row["response_length"],
        "query_tokens": row["query_tokens"],
        "response_tokens": row["response_tokens"],
        "embedding_tokens": row["embedding_tokens"],
        "rerank_prompt_tokens": row["rerank_prompt_tokens"],
        "rerank_completion_tokens": row["rerank_completion_tokens"],
        "rerank_total_tokens": row["rerank_total_tokens"],
        "rerank_model": row["rerank_model"],
        "duration_ms": round(float(row["duration_ms"]), 1),
        "embed_ms": round(float(row["embed_ms"]), 1),
        "search_ms": round(float(row["search_ms"]), 1),
        "rerank_ms": round(float(row["rerank_ms"]), 1),
        "cogs_usd": str(row["cogs_usd"]),
        "charge_usd": str(row["charge_usd"]),
        "client_ip": row["client_ip"],
        "user_agent": row["user_agent"],
        "error": row["error"],
        "status": row["status"],
    }


async def get_mcp_stats(session: AsyncSession, days: int = 30) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    params = {"since": since}

    totals = (await session.execute(text("""
        SELECT
            COUNT(*) AS cnt,
            COALESCE(SUM(query_tokens), 0) AS q_tokens,
            COALESCE(SUM(response_tokens), 0) AS r_tokens,
            COALESCE(SUM(embedding_tokens), 0) AS e_tokens,
            COALESCE(SUM(charge_usd), 0) AS charge,
            AVG(duration_ms) AS avg_dur,
            COUNT(*) FILTER (WHERE status = 'error') AS errors
        FROM mcp_request_log
        WHERE created_at >= :since
    """), params)).mappings().one()

    total = int(totals["cnt"])

    daily = (await session.execute(text("""
        SELECT DATE(created_at) AS d,
            COUNT(*) AS cnt,
            COALESCE(SUM(query_tokens + response_tokens + embedding_tokens), 0) AS tokens,
            COALESCE(SUM(charge_usd), 0) AS charge,
            COUNT(*) FILTER (WHERE status = 'error') AS errors
        FROM mcp_request_log
        WHERE created_at >= :since
        GROUP BY DATE(created_at) ORDER BY d
    """), params)).mappings().all()

    by_tool = (await session.execute(text("""
        SELECT tool_name, COUNT(*) AS cnt
        FROM mcp_request_log
        WHERE created_at >= :since
        GROUP BY tool_name ORDER BY cnt DESC
    """), params)).mappings().all()

    top_queries = (await session.execute(text("""
        SELECT query_text, COUNT(*) AS cnt
        FROM mcp_request_log
        WHERE created_at >= :since AND query_text IS NOT NULL AND query_text != ''
        GROUP BY query_text ORDER BY cnt DESC LIMIT 20
    """), params)).mappings().all()

    top_tenants = (await session.execute(text("""
        SELECT m.tenant_id, t.email, COUNT(*) AS cnt,
            COALESCE(SUM(m.charge_usd), 0) AS charge
        FROM mcp_request_log m
        LEFT JOIN tenants t ON t.id = m.tenant_id
        WHERE m.created_at >= :since
        GROUP BY m.tenant_id, t.email ORDER BY cnt DESC LIMIT 10
    """), params)).mappings().all()

    tool_total = max(total, 1)
    return {
        "total_requests": total,
        "total_query_tokens": int(totals["q_tokens"]),
        "total_response_tokens": int(totals["r_tokens"]),
        "total_embedding_tokens": int(totals["e_tokens"]),
        "total_charge_usd": f"{float(totals['charge']):.8f}",
        "avg_duration_ms": round(float(totals["avg_dur"]), 1) if totals["avg_dur"] else None,
        "error_count": int(totals["errors"]),
        "error_rate": round(int(totals["errors"]) / tool_total * 100, 2),
        "daily": [
            {"date": str(r["d"]), "requests": int(r["cnt"]),
             "tokens": int(r["tokens"]), "charge_usd": str(r["charge"]),
             "errors": int(r["errors"])}
            for r in daily
        ],
        "by_tool": [
            {"tool_name": r["tool_name"], "count": int(r["cnt"]),
             "pct": round(int(r["cnt"]) / tool_total * 100, 1)}
            for r in by_tool
        ],
        "top_queries": [
            {"query": (r["query_text"] or "")[:200], "count": int(r["cnt"])}
            for r in top_queries
        ],
        "top_tenants": [
            {"email": r["email"] or "—", "count": int(r["cnt"]),
             "charge_usd": str(r["charge"])}
            for r in top_tenants
        ],
    }
