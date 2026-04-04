"""Admin REST endpoints — platform management, moderation, audit, stats, logs."""

import uuid
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.auth.dependencies import require_admin
from app.models import Tenant
from app.admin import service
from app.admin.schemas import (
    AdminChatMessageSearchResponse,
    AdminChatSessionDetail,
    AdminChatSessionListResponse,
    AdminDocumentDetail,
    AdminDocumentListResponse,
    AdminDocumentPatchRequest,
    BulkCancelRequest,
    BulkDeleteRequest,
    ChatStats,
    CostStats,
    DocumentStats,
    ExtendedSearchStats,
    IngestionStat,
    LogsResponse,
    McpRequestDetail,
    McpRequestListResponse,
    McpStats,
    ModelUsageStat,
    PlatformOverview,
    PromptPreviewResponse,
    PromptTemplateCreateRequest,
    PromptTemplateDetail,
    PromptTemplateItem,
    PromptTemplatePatchRequest,
    RagEvalRunDetail,
    RagEvalRunItem,
    RagEvalRunListResponse,
    RagEvalRunRequest,
    RescueResult,
    RoleCreateRequest,
    RoleDetail,
    RoleListItem,
    RolePatchRequest,
    SearchStat,
    SystemInfo,
    TaskItem,
    TaskListResponse,
    TenantDetail,
    TenantListResponse,
    TenantPatchRequest,
    TenantRoleAssignRequest,
    TenantRoleItem,
    UsageStatsResponse,
    WorkersResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Tenants
# ---------------------------------------------------------------------------

@router.get("/tenants", response_model=TenantListResponse)
async def list_tenants(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    search: str | None = None,
    role: str | None = None,
    tier: str | None = None,
    is_active: bool | None = None,
    session: AsyncSession = Depends(get_session),
):
    items, total = await service.list_tenants(
        session, page=page, page_size=page_size,
        search=search, role=role, tier=tier, is_active=is_active,
    )
    return TenantListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/tenants/search/autocomplete")
async def search_tenants_autocomplete(
    q: str = Query("", min_length=1),
    limit: int = Query(10, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
):
    """Lightweight tenant search for autocomplete (by name or email)."""
    from sqlalchemy import select as sa_select
    from app.models import Tenant

    like = f"%{q}%"
    rows = (await session.execute(
        sa_select(Tenant.id, Tenant.name, Tenant.email)
        .where(Tenant.name.ilike(like) | Tenant.email.ilike(like))
        .order_by(Tenant.name)
        .limit(limit)
    )).all()
    return [{"id": str(r.id), "name": r.name, "email": r.email} for r in rows]


@router.get("/tenants/{tenant_id}", response_model=TenantDetail)
async def get_tenant(
    tenant_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    detail = await service.get_tenant_detail(session, tenant_id)
    if not detail:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")
    return detail


@router.patch("/tenants/{tenant_id}", response_model=TenantDetail)
async def patch_tenant(
    tenant_id: uuid.UUID,
    body: TenantPatchRequest,
    session: AsyncSession = Depends(get_session),
    current_tenant: Tenant = Depends(require_admin),
):
    if body.is_active is not None and tenant_id == current_tenant.id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Cannot change your own active status",
        )
    if body.role and body.role not in ("user", "admin"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid role")
    result = await service.patch_tenant(
        session, tenant_id,
        role=body.role, tier=body.tier, is_active=body.is_active,
    )
    if not result:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")
    return result


@router.delete("/tenants/{tenant_id}", status_code=204)
async def delete_tenant(
    tenant_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_tenant: Tenant = Depends(require_admin),
):
    if tenant_id == current_tenant.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot delete yourself")
    t = await session.get(Tenant, tenant_id)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")
    if t.email_verified:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only unverified tenants can be deleted",
        )
    if not await service.delete_unverified_tenant(session, tenant_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

@router.get("/documents", response_model=AdminDocumentListResponse)
async def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    status_filter: str | None = Query(None, alias="status"),
    tenant_id: uuid.UUID | None = None,
    search: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    items, total = await service.list_documents_admin(
        session, page=page, page_size=page_size,
        status_filter=status_filter, tenant_id=tenant_id, search=search,
    )
    return AdminDocumentListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/documents/{doc_id}", response_model=AdminDocumentDetail)
async def get_document(
    doc_id: int,
    session: AsyncSession = Depends(get_session),
):
    detail = await service.get_document_admin(session, doc_id)
    if not detail:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return detail


@router.patch("/documents/{doc_id}", response_model=AdminDocumentDetail)
async def patch_document(
    doc_id: int,
    body: AdminDocumentPatchRequest,
    session: AsyncSession = Depends(get_session),
):
    result = await service.patch_document_admin(session, doc_id, status=body.status)
    if not result:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return result


@router.delete("/documents/{doc_id}", status_code=204)
async def delete_document(
    doc_id: int,
    session: AsyncSession = Depends(get_session),
):
    if not await service.delete_document_admin(session, doc_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")


# ---------------------------------------------------------------------------
# Chat Audit
# ---------------------------------------------------------------------------

@router.get("/chat/sessions", response_model=AdminChatSessionListResponse)
async def list_chat_sessions(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    tenant_id: uuid.UUID | None = None,
    search: str | None = None,
    created_after: str | None = None,
    created_before: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    from datetime import datetime
    ca = datetime.fromisoformat(created_after) if created_after else None
    cb = datetime.fromisoformat(created_before) if created_before else None
    items, total = await service.list_chat_sessions_admin(
        session, page=page, page_size=page_size,
        tenant_id=tenant_id, search=search,
        created_after=ca, created_before=cb,
    )
    return AdminChatSessionListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/chat/sessions/{session_uuid}", response_model=AdminChatSessionDetail)
async def get_chat_session(
    session_uuid: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    detail = await service.get_chat_session_admin(session, session_uuid)
    if not detail:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chat session not found")
    return detail


@router.get("/chat/messages", response_model=AdminChatMessageSearchResponse)
async def search_messages(
    query: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
):
    items, total = await service.search_chat_messages(session, query=query, limit=limit)
    return AdminChatMessageSearchResponse(items=items, total=total)


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@router.get("/stats/overview", response_model=PlatformOverview)
async def stats_overview(session: AsyncSession = Depends(get_session)):
    return await service.get_platform_overview(session)


@router.get("/stats/usage", response_model=UsageStatsResponse)
async def stats_usage(
    days: int = Query(30, ge=1, le=365),
    tenant_id: uuid.UUID | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    return await service.get_usage_stats(session, days=days, tenant_id=tenant_id)


@router.get("/stats/models", response_model=list[ModelUsageStat])
async def stats_models(
    days: int = Query(30, ge=1, le=365),
    tenant_id: uuid.UUID | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    return await service.get_model_stats(session, days=days, tenant_id=tenant_id)


@router.get("/stats/ingestion", response_model=IngestionStat)
async def stats_ingestion(session: AsyncSession = Depends(get_session)):
    return await service.get_ingestion_stats(session)


@router.get("/stats/search", response_model=SearchStat)
async def stats_search(
    days: int = Query(30, ge=1, le=365),
    tenant_id: uuid.UUID | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    return await service.get_search_stats(session, days=days, tenant_id=tenant_id)


@router.get("/stats/chat", response_model=ChatStats)
async def stats_chat(
    days: int = Query(30, ge=1, le=365),
    tenant_id: uuid.UUID | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    return await service.get_chat_stats(session, days=days, tenant_id=tenant_id)


@router.get("/stats/documents", response_model=DocumentStats)
async def stats_documents(
    days: int = Query(30, ge=1, le=365),
    tenant_id: uuid.UUID | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    return await service.get_document_stats(session, days=days, tenant_id=tenant_id)


@router.get("/stats/search-extended", response_model=ExtendedSearchStats)
async def stats_search_extended(
    days: int = Query(30, ge=1, le=365),
    tenant_id: uuid.UUID | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    return await service.get_extended_search_stats(session, days=days, tenant_id=tenant_id)


@router.get("/stats/costs", response_model=CostStats)
async def stats_costs(
    days: int = Query(30, ge=1, le=365),
    tenant_id: uuid.UUID | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    return await service.get_cost_stats(session, days=days, tenant_id=tenant_id)


# ---------------------------------------------------------------------------
# MCP Audit
# ---------------------------------------------------------------------------

@router.get("/mcp/requests", response_model=McpRequestListResponse)
async def list_mcp_requests(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    tenant_id: uuid.UUID | None = None,
    api_key_id: uuid.UUID | None = None,
    tool_name: str | None = None,
    status: str | None = None,
    search: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    from datetime import datetime as dt
    df = dt.fromisoformat(date_from) if date_from else None
    dto = dt.fromisoformat(date_to) if date_to else None
    items, total = await service.list_mcp_requests(
        session, page=page, page_size=page_size,
        tenant_id=str(tenant_id) if tenant_id else None,
        api_key_id=str(api_key_id) if api_key_id else None,
        tool_name=tool_name, status=status, search=search, date_from=df, date_to=dto,
    )
    return McpRequestListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/mcp/requests/{request_id}", response_model=McpRequestDetail)
async def get_mcp_request(
    request_id: str,
    session: AsyncSession = Depends(get_session),
):
    detail = await service.get_mcp_request_detail(session, request_id)
    if not detail:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "MCP request not found")
    return detail


@router.get("/mcp/stats", response_model=McpStats)
async def mcp_stats(
    days: int = Query(30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
):
    return await service.get_mcp_stats(session, days=days)


# ---------------------------------------------------------------------------
# Logs (Loki proxy)
# ---------------------------------------------------------------------------

LOKI_URL = "http://loki:3100"
_SERVICE_TO_CONTAINER = {
    "api": "/lexiro-api-1",
    "worker": "/lexiro-worker-1",
    "beat": "/lexiro-beat-1",
    "web": "/lexiro-web-1",
    "postgres": "/lexiro-postgres-1",
    "redis": "/lexiro-redis-1",
    "minio": "/lexiro-minio-1",
    "nginx": "/lexiro-web-1",
}

_CONTAINER_TO_SERVICE = {v: k for k, v in _SERVICE_TO_CONTAINER.items()}

_APP_CONTAINERS = [
    _SERVICE_TO_CONTAINER[s] for s in ("api", "worker", "beat")
]

@router.get("/logs", response_model=LogsResponse)
async def get_logs(
    service_name: str = Query("", alias="service"),
    level: str | None = None,
    search: str | None = None,
    tenant_name: str | None = Query(None, alias="tenant"),
    start: str | None = None,
    end: str | None = None,
    limit: int = Query(200, ge=1, le=5000),
):
    label_parts: list[str] = []
    if service_name:
        container = _SERVICE_TO_CONTAINER.get(service_name, f"/lexiro-{service_name}-1")
        label_parts.append(f'container="{container}"')
    else:
        regex = "|".join(_APP_CONTAINERS)
        label_parts.append(f'container=~"{regex}"')
    if level:
        label_parts.append(f'level="{level}"')
    label_selector = "{" + ",".join(label_parts) + "}"

    pipeline_stages: list[str] = []
    if tenant_name:
        safe = tenant_name.replace('"', '\\"')
        pipeline_stages.append(f'|~ "tenant_name.*{safe}"')
    if search:
        pipeline_stages.append(f'|~ "{search}"')

    if pipeline_stages:
        query = label_selector + " " + " ".join(pipeline_stages)
    else:
        query = label_selector

    params: dict = {"query": query, "limit": str(limit), "direction": "backward"}
    if start:
        params["start"] = start
    if end:
        params["end"] = end

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{LOKI_URL}/loki/api/v1/query_range", params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning("Loki query failed", extra={"error": str(e)})
        return LogsResponse(entries=[], total=0)

    entries = []
    for stream in data.get("data", {}).get("result", []):
        stream_labels = stream.get("stream", {})
        svc = service_name
        if not svc:
            svc = _CONTAINER_TO_SERVICE.get(stream_labels.get("container", ""), "")
        for ts, line in stream.get("values", []):
            entries.append({
                "timestamp": ts,
                "level": stream_labels.get("level", ""),
                "message": line,
                "service": svc,
                "extra": {k: v for k, v in stream_labels.items() if k not in ("container", "level", "service_name", "stream")},
            })

    entries.sort(key=lambda e: e["timestamp"], reverse=True)

    return LogsResponse(entries=entries[:limit], total=len(entries))


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------

@router.get("/roles", response_model=list[RoleListItem])
async def list_roles(session: AsyncSession = Depends(get_session)):
    return await service.list_roles(session)


@router.get("/roles/{role_id}", response_model=RoleDetail)
async def get_role(role_id: int, session: AsyncSession = Depends(get_session)):
    detail = await service.get_role_detail(session, role_id)
    if not detail:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found")
    return detail


@router.post("/roles", response_model=RoleDetail, status_code=201)
async def create_role(body: RoleCreateRequest, session: AsyncSession = Depends(get_session)):
    try:
        role = await service.create_role(
            session,
            slug=body.slug, name=body.name, description=body.description,
            priority=body.priority, permissions=body.permissions,
        )
    except Exception as e:
        if "unique" in str(e).lower():
            raise HTTPException(status.HTTP_409_CONFLICT, "Role slug already exists")
        raise
    return await service.get_role_detail(session, role.id)


@router.patch("/roles/{role_id}", response_model=RoleDetail)
async def patch_role(
    role_id: int,
    body: RolePatchRequest,
    session: AsyncSession = Depends(get_session),
):
    result = await service.patch_role(
        session, role_id,
        name=body.name, description=body.description,
        priority=body.priority, permissions=body.permissions,
    )
    if not result:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found")
    return result


@router.delete("/roles/{role_id}", status_code=204)
async def delete_role(role_id: int, session: AsyncSession = Depends(get_session)):
    try:
        if not await service.delete_role(session, role_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found")
    except ValueError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))


# ---------------------------------------------------------------------------
# Tenant Roles
# ---------------------------------------------------------------------------

@router.get("/tenants/{tenant_id}/roles", response_model=list[TenantRoleItem])
async def get_tenant_roles(
    tenant_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    return await service.get_tenant_roles(session, tenant_id)


@router.post("/tenants/{tenant_id}/roles", response_model=TenantRoleItem, status_code=201)
async def assign_tenant_role(
    tenant_id: uuid.UUID,
    body: TenantRoleAssignRequest,
    session: AsyncSession = Depends(get_session),
):
    try:
        return await service.assign_role_to_tenant(session, tenant_id, body.role_id)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


@router.delete("/tenants/{tenant_id}/roles/{role_id}", status_code=204)
async def unassign_tenant_role(
    tenant_id: uuid.UUID,
    role_id: int,
    session: AsyncSession = Depends(get_session),
):
    if not await service.unassign_role_from_tenant(session, tenant_id, role_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role assignment not found")


# ---------------------------------------------------------------------------
# Prompt Templates
# ---------------------------------------------------------------------------

@router.get("/prompts", response_model=list[PromptTemplateItem])
async def list_prompts(session: AsyncSession = Depends(get_session)):
    return await service.list_prompt_templates(session)


@router.get("/prompts/{prompt_id}", response_model=PromptTemplateDetail)
async def get_prompt(prompt_id: int, session: AsyncSession = Depends(get_session)):
    detail = await service.get_prompt_template(session, prompt_id)
    if not detail:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Prompt template not found")
    return detail


@router.post("/prompts", response_model=PromptTemplateDetail, status_code=201)
async def create_prompt(
    body: PromptTemplateCreateRequest,
    session: AsyncSession = Depends(get_session),
):
    try:
        pt = await service.create_prompt_template(
            session,
            query_type=body.query_type, role_id=body.role_id,
            body=body.body, classifier_hint=body.classifier_hint,
            max_response_tokens=body.max_response_tokens,
            rag_top_k=body.rag_top_k,
        )
    except Exception as e:
        if "unique" in str(e).lower():
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Prompt template for this query_type + role already exists",
            )
        raise
    return await service.get_prompt_template(session, pt.id)


@router.patch("/prompts/{prompt_id}", response_model=PromptTemplateDetail)
async def patch_prompt(
    prompt_id: int,
    body: PromptTemplatePatchRequest,
    session: AsyncSession = Depends(get_session),
):
    kwargs: dict = {}
    if body.body is not None:
        kwargs["body"] = body.body
    if body.classifier_hint is not None:
        kwargs["classifier_hint"] = body.classifier_hint
    kwargs["max_response_tokens"] = body.max_response_tokens
    kwargs["rag_top_k"] = body.rag_top_k
    result = await service.patch_prompt_template(session, prompt_id, **kwargs)
    if not result:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Prompt template not found")
    return result


@router.delete("/prompts/{prompt_id}", status_code=204)
async def delete_prompt(prompt_id: int, session: AsyncSession = Depends(get_session)):
    try:
        if not await service.delete_prompt_template(session, prompt_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Prompt template not found")
    except ValueError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))


@router.post("/prompts/{prompt_id}/preview", response_model=PromptPreviewResponse)
async def preview_prompt(prompt_id: int, session: AsyncSession = Depends(get_session)):
    result = await service.preview_prompt_template(session, prompt_id)
    if not result:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Prompt template not found")
    return result


@router.post("/prompts/seed")
async def seed_prompts_from_files(session: AsyncSession = Depends(get_session)):
    from app.admin.seed_prompts import seed_prompts
    count = await seed_prompts(session)
    return {"seeded": count}


# ---------------------------------------------------------------------------
# System Monitor
# ---------------------------------------------------------------------------

@router.get("/system/info", response_model=SystemInfo)
async def system_info(session: AsyncSession = Depends(get_session)):
    return await service.get_system_info(session)


# ---------------------------------------------------------------------------
# Task Queue
# ---------------------------------------------------------------------------

_TASK_NAME_MAP = {
    "ingest_document": "Document",
    "ingest_archive": "Archive",
    "ingest_archive_from_s3": "Archive (S3)",
    "ingest_single_url": "URL",
    "ingest_confluence": "Confluence",
    "ingest_site": "Site Crawl",
    "ingest_github": "GitHub",
    "reingest_confluence_page": "Confluence Page",
    "run_reindex_job": "Reindex",
    "analyze_api_lifecycle": "Lifecycle",
    "merge_product_lifecycle": "Lifecycle Merge",
    "delete_product": "Delete Product",
    "run_rag_evaluation": "RAG Eval",
    "backfill_chunk_languages": "Backfill Languages",
}


import time as _time
import threading as _threading

_inspect_cache: dict[str, tuple[float, dict]] = {}
_inspect_lock = _threading.Lock()
_INSPECT_TTL = 5.0


def _inspect_with_timeout(method: str, timeout: float = 2.0):
    """Call Celery inspect method with a short TTL cache to avoid repeated slow round-trips."""
    from app.celery_app import celery

    now = _time.monotonic()
    with _inspect_lock:
        cached = _inspect_cache.get(method)
        if cached and (now - cached[0]) < _INSPECT_TTL:
            return cached[1]

    inspector = celery.control.inspect(timeout=timeout)
    fn = getattr(inspector, method, None)
    if fn is None:
        return {}
    try:
        result = fn()
    except Exception:
        result = None
    data = result or {}

    with _inspect_lock:
        _inspect_cache[method] = (now, data)

    return data


@router.get("/tasks", response_model=TaskListResponse)
async def list_tasks(
    status_filter: str | None = Query(None, alias="status"),
    task_name: str | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
):
    """List active, pending, stale and error tasks from Celery + DB."""
    import asyncio
    from datetime import datetime, timezone
    from sqlalchemy import select as sa_select, func
    from app.models import Document, ReindexJob, Product, Tenant

    items: list[TaskItem] = []

    loop = asyncio.get_running_loop()
    active_data, reserved_data = await asyncio.gather(
        loop.run_in_executor(None, _inspect_with_timeout, "active"),
        loop.run_in_executor(None, _inspect_with_timeout, "reserved"),
    )

    celery_active_ids: set[str] = set()
    now = datetime.now(timezone.utc)

    for worker_name, task_list in active_data.items():
        for t in (task_list or []):
            tid = t.get("id", "")
            celery_active_ids.add(tid)
            tname = t.get("name", "unknown")
            args = t.get("args", [])
            started = t.get("time_start")
            runtime = (now.timestamp() - started) if started else None
            doc_id = args[0] if args and isinstance(args[0], int) else None
            items.append(TaskItem(
                task_id=tid,
                task_name=_TASK_NAME_MAP.get(tname, tname),
                status="active",
                source="celery",
                worker=worker_name.split("@")[-1],
                started_at=datetime.fromtimestamp(started, tz=timezone.utc).isoformat() if started else None,
                runtime_sec=round(runtime, 1) if runtime else None,
                args_summary=f"doc_id={doc_id}" if doc_id else str(args)[:80] if args else None,
            ))

    for worker_name, task_list in reserved_data.items():
        for t in (task_list or []):
            tid = t.get("id", "")
            tname = t.get("name", "unknown")
            args = t.get("args", [])
            doc_id = args[0] if args and isinstance(args[0], int) else None
            items.append(TaskItem(
                task_id=tid,
                task_name=_TASK_NAME_MAP.get(tname, tname),
                status="reserved",
                source="celery",
                worker=worker_name.split("@")[-1],
                args_summary=f"doc_id={doc_id}" if doc_id else str(args)[:80] if args else None,
            ))

    doc_q = (
        sa_select(
            Document.id,
            Document.title,
            Document.original_filename,
            Document.status,
            Document.celery_task_id,
            Document.progress_percent,
            Document.progress_stage,
            Document.error_message,
            Document.format,
            Document.uploaded_at,
            Document.processing_started_at,
            Document.product_id,
            Product.name.label("product_name"),
            Tenant.email.label("tenant_email"),
        )
        .outerjoin(Product, Document.product_id == Product.id)
        .outerjoin(Tenant, Document.tenant_id == Tenant.id)
        .where(Document.status.in_(["pending", "processing", "error"]))
        .order_by(Document.uploaded_at.desc())
    )
    doc_rows = (await session.execute(doc_q)).all()

    _FORMAT_TASK = {
        "site": "Site Crawl", "confluence": "Confluence", "url": "URL",
        "github": "GitHub",
    }

    for row in doc_rows:
        tid = row.celery_task_id
        if tid and tid in celery_active_ids:
            for item in items:
                if item.task_id == tid:
                    item.document_id = row.id
                    item.document_title = row.title or row.original_filename
                    item.product_name = row.product_name
                    item.tenant_email = row.tenant_email
                    item.progress_percent = row.progress_percent
                    item.progress_stage = row.progress_stage
                    break
            continue

        started = row.processing_started_at or row.uploaded_at
        runtime = (now - started).total_seconds() if started else None
        task_display = _FORMAT_TASK.get(row.format, "Document")

        db_status = row.status
        if db_status == "processing" and (not tid or tid not in celery_active_ids):
            db_status = "stale"

        items.append(TaskItem(
            task_id=tid,
            task_name=task_display,
            status=db_status,
            source="db_document",
            created_at=row.uploaded_at.isoformat() if row.uploaded_at else None,
            started_at=started.isoformat() if started else None,
            runtime_sec=round(runtime, 1) if runtime else None,
            progress_percent=row.progress_percent,
            progress_stage=row.progress_stage,
            document_id=row.id,
            document_title=row.title or row.original_filename,
            product_id=row.product_id,
            product_name=row.product_name,
            tenant_email=row.tenant_email,
            error_message=row.error_message,
        ))

    rj_q = (
        sa_select(ReindexJob)
        .where(ReindexJob.status.in_(["pending", "running", "stale"]))
        .order_by(ReindexJob.created_at.desc())
    )
    rj_rows = (await session.execute(rj_q)).scalars().all()
    for job in rj_rows:
        tid = job.celery_task_id
        if tid and tid in celery_active_ids:
            for item in items:
                if item.task_id == tid:
                    item.document_title = f"Reindex: {job.product_filter or 'all'}"
                    pct = round(job.processed_documents / max(job.total_documents, 1) * 100)
                    item.progress_percent = pct
                    item.progress_stage = f"{job.processed_documents}/{job.total_documents} docs"
                    break
            continue

        started = job.started_at or job.created_at
        runtime = (now - started).total_seconds() if started else None
        pct = round(job.processed_documents / max(job.total_documents, 1) * 100)
        items.append(TaskItem(
            task_id=tid,
            task_name="Reindex",
            status=job.status,
            source="db_reindex",
            created_at=job.created_at.isoformat() if job.created_at else None,
            started_at=started.isoformat() if started else None,
            runtime_sec=round(runtime, 1) if runtime else None,
            progress_percent=pct,
            progress_stage=f"{job.processed_documents}/{job.total_documents} docs",
            document_title=f"Reindex: {job.product_filter or 'all'} ({job.mode})",
            error_message=job.error_message,
        ))

    if status_filter:
        items = [i for i in items if i.status == status_filter]
    if task_name:
        items = [i for i in items if task_name.lower() in i.task_name.lower()]
    if search:
        q = search.lower()
        items = [
            i for i in items
            if (i.document_title and q in i.document_title.lower())
            or (i.product_name and q in i.product_name.lower())
            or (i.tenant_email and q in i.tenant_email.lower())
            or (i.args_summary and q in i.args_summary.lower())
        ]

    _STATUS_ORDER = {"stale": 0, "error": 1, "active": 2, "processing": 3, "reserved": 4, "pending": 5}
    items.sort(key=lambda i: (
        _STATUS_ORDER.get(i.status, 9),
        -(i.runtime_sec or 0),
    ))

    active_count = sum(1 for i in items if i.status == "active")
    pending_count = sum(1 for i in items if i.status in ("pending", "reserved"))
    stale_count = sum(1 for i in items if i.status == "stale")
    error_count = sum(1 for i in items if i.status == "error")
    total = len(items)

    start = (page - 1) * page_size
    page_items = items[start:start + page_size]

    return TaskListResponse(
        items=page_items,
        total=total,
        active_count=active_count,
        pending_count=pending_count,
        stale_count=stale_count,
        error_count=error_count,
    )


@router.get("/tasks/workers", response_model=WorkersResponse)
async def list_workers():
    """Get status of all Celery workers."""
    import asyncio
    from app.admin.schemas import WorkerInfo

    loop = asyncio.get_running_loop()
    ping_data, stats_data, queue_data = await asyncio.gather(
        loop.run_in_executor(None, _inspect_with_timeout, "ping"),
        loop.run_in_executor(None, _inspect_with_timeout, "stats"),
        loop.run_in_executor(None, _inspect_with_timeout, "active_queues"),
    )

    workers: list[WorkerInfo] = []
    all_names = set(ping_data.keys()) | set(stats_data.keys())

    for name in sorted(all_names):
        short = name.split("@")[-1]
        st = stats_data.get(name, {})
        queues = [q.get("name", "") for q in (queue_data.get(name) or [])]
        workers.append(WorkerInfo(
            name=short,
            status="online" if name in ping_data else "offline",
            pid=st.get("pid"),
            queues=queues,
            active_tasks=len(st.get("active", [] if not isinstance(st.get("total"), dict) else [])),
            processed_total=sum(st.get("total", {}).values()) if isinstance(st.get("total"), dict) else 0,
        ))

    return WorkersResponse(workers=workers)


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Cancel a task by revoking it in Celery and updating DB status."""
    from app.celery_app import celery
    from sqlalchemy import select as sa_select
    from app.models import Document, ReindexJob, Chunk

    try:
        celery.control.revoke(task_id, terminate=True)
    except Exception:
        logger.warning("Failed to revoke task", extra={"task_id": task_id})

    doc = (await session.execute(
        sa_select(Document).where(Document.celery_task_id == task_id)
    )).scalar_one_or_none()

    if doc and doc.status in ("pending", "processing"):
        doc.status = "cancelled"
        doc.progress_percent = 0
        doc.progress_stage = ""
        doc.error_message = None
        chunks = (await session.execute(
            sa_select(Chunk).where(Chunk.document_id == doc.id)
        )).scalars().all()
        for chunk in chunks:
            await session.delete(chunk)
        doc.total_chunks = 0
        await session.commit()
        logger.info("Task cancelled (document)", extra={"task_id": task_id, "document_id": doc.id})
        return {"status": "cancelled", "type": "document", "document_id": doc.id}

    job = (await session.execute(
        sa_select(ReindexJob).where(ReindexJob.celery_task_id == task_id)
    )).scalar_one_or_none()

    if job and job.status in ("pending", "running"):
        from datetime import datetime, timezone
        job.status = "cancelled"
        job.finished_at = datetime.now(timezone.utc)
        await session.commit()
        logger.info("Task cancelled (reindex)", extra={"task_id": task_id, "job_id": job.id})
        return {"status": "cancelled", "type": "reindex", "job_id": job.id}

    return {"status": "revoked", "type": "unknown"}


@router.post("/tasks/{document_id_int}/retry")
async def retry_task(
    document_id_int: int,
    session: AsyncSession = Depends(get_session),
):
    """Retry a failed/stale document by resetting and re-dispatching."""
    from app.models import Document
    from app.celery_app import _redispatch_document, _get_sync_engine
    from sqlalchemy.orm import Session as SyncSession

    doc = await session.get(Document, document_id_int)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc.status not in ("error", "cancelled", "processing", "pending"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot retry document with status '{doc.status}'",
        )

    doc.status = "pending"
    doc.error_message = None
    doc.progress_percent = 0
    doc.progress_stage = ""
    await session.commit()
    await session.refresh(doc)

    engine = _get_sync_engine()
    with SyncSession(engine) as sync_session:
        sync_doc = sync_session.get(Document, doc.id)
        new_task_id = _redispatch_document(sync_doc)
        if new_task_id:
            sync_doc.celery_task_id = new_task_id
            sync_session.commit()

    logger.info("Task retried", extra={"document_id": doc.id, "new_task_id": new_task_id})
    return {"status": "retried", "document_id": doc.id, "new_task_id": new_task_id}


@router.post("/tasks/rescue-stale", response_model=RescueResult)
async def rescue_stale_tasks(
    session: AsyncSession = Depends(get_session),
):
    """Manually trigger rescue for orphaned/stale/error documents and reindex jobs."""
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import select as sa_select
    from app.models import Document, ReindexJob
    from app.celery_app import _redispatch_document, _get_sync_engine
    from sqlalchemy.orm import Session as SyncSession
    from celery.result import AsyncResult
    from app.celery_app import celery

    engine = _get_sync_engine()
    threshold = datetime.now(timezone.utc) - timedelta(minutes=5)
    rescued_docs = 0
    rescued_jobs = 0

    pending_docs = (await session.execute(
        sa_select(Document).where(
            Document.status == "pending",
            Document.uploaded_at < threshold,
        ).limit(200)
    )).scalars().all()

    processing_docs = (await session.execute(
        sa_select(Document).where(
            Document.status == "processing",
        ).limit(200)
    )).scalars().all()

    error_docs = (await session.execute(
        sa_select(Document).where(
            Document.status == "error",
        ).limit(200)
    )).scalars().all()

    orphaned = list(pending_docs) + list(error_docs)
    for doc in processing_docs:
        if not doc.celery_task_id:
            orphaned.append(doc)
            continue
        try:
            result = AsyncResult(doc.celery_task_id, app=celery)
            if result.state in ("PENDING", "REVOKED"):
                orphaned.append(doc)
        except Exception:
            orphaned.append(doc)

    if orphaned:
        with SyncSession(engine) as sync_session:
            for doc in orphaned:
                sync_doc = sync_session.get(Document, doc.id)
                if sync_doc is None:
                    continue
                sync_doc.status = "pending"
                sync_doc.error_message = None
                sync_doc.progress_percent = 0
                sync_doc.progress_stage = ""
                new_tid = _redispatch_document(sync_doc)
                if new_tid:
                    sync_doc.celery_task_id = new_tid
                    rescued_docs += 1
            sync_session.commit()

    from app.config import settings as _settings
    stale_threshold = datetime.now(timezone.utc) - timedelta(seconds=_settings.reindex_stale_timeout_sec)
    stale_jobs = (await session.execute(
        sa_select(ReindexJob).where(
            ReindexJob.status == "running",
            ReindexJob.heartbeat_at < stale_threshold,
        )
    )).scalars().all()

    for job in stale_jobs:
        job.status = "stale"
        job.finished_at = datetime.now(timezone.utc)
        job.error_message = f"Manually marked stale (heartbeat stopped at {job.heartbeat_at})"
        rescued_jobs += 1

    await session.commit()

    logger.info("Manual rescue completed", extra={
        "rescued_documents": rescued_docs,
        "rescued_reindex_jobs": rescued_jobs,
    })
    return RescueResult(rescued_documents=rescued_docs, rescued_reindex_jobs=rescued_jobs)


@router.post("/tasks/bulk-cancel")
async def bulk_cancel_tasks(
    body: BulkCancelRequest,
    session: AsyncSession = Depends(get_session),
):
    """Cancel multiple tasks by IDs or by filter."""
    from app.celery_app import celery
    from sqlalchemy import select as sa_select
    from app.models import Document, Chunk

    cancelled = 0

    if body.task_ids:
        for tid in body.task_ids:
            try:
                celery.control.revoke(tid, terminate=True)
            except Exception:
                pass

            doc = (await session.execute(
                sa_select(Document).where(Document.celery_task_id == tid)
            )).scalar_one_or_none()
            if doc and doc.status in ("pending", "processing"):
                doc.status = "cancelled"
                doc.progress_percent = 0
                doc.progress_stage = ""
                chunks = (await session.execute(
                    sa_select(Chunk).where(Chunk.document_id == doc.id)
                )).scalars().all()
                for chunk in chunks:
                    await session.delete(chunk)
                doc.total_chunks = 0
                cancelled += 1

        await session.commit()
        return {"status": "ok", "cancelled": cancelled}

    if body.filter_status:
        target_statuses = []
        if body.filter_status == "stale":
            target_statuses = ["processing"]
        elif body.filter_status in ("pending", "error"):
            target_statuses = [body.filter_status]
        else:
            target_statuses = ["pending", "processing"]

        q = sa_select(Document).where(Document.status.in_(target_statuses))
        docs = (await session.execute(q.limit(500))).scalars().all()
        for doc in docs:
            if doc.celery_task_id:
                try:
                    celery.control.revoke(doc.celery_task_id, terminate=True)
                except Exception:
                    pass
            doc.status = "cancelled"
            doc.progress_percent = 0
            doc.progress_stage = ""
            cancelled += 1

        await session.commit()
        return {"status": "ok", "cancelled": cancelled}

    raise HTTPException(status_code=400, detail="Provide task_ids or filter_status")


@router.delete("/tasks/{document_id_int}/delete")
async def delete_task(
    document_id_int: int,
    session: AsyncSession = Depends(get_session),
):
    """Permanently delete a document (any status): revoke celery, remove chunks, S3 file, DB row."""
    from app.celery_app import celery
    from sqlalchemy import select as sa_select
    from app.models import Document, Chunk
    from app.s3 import delete_file

    doc = await session.get(Document, document_id_int)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc.celery_task_id:
        try:
            celery.control.revoke(doc.celery_task_id, terminate=True)
        except Exception:
            logger.warning("Failed to revoke task during delete", extra={
                "task_id": doc.celery_task_id, "document_id": doc.id,
            })

    if doc.s3_key:
        try:
            delete_file(doc.s3_key)
        except Exception as e:
            logger.warning("Failed to delete S3 file", extra={
                "s3_key": doc.s3_key, "error": str(e),
            })

    chunks = (await session.execute(
        sa_select(Chunk).where(Chunk.document_id == doc.id)
    )).scalars().all()
    chunk_count = len(chunks)
    for chunk in chunks:
        await session.delete(chunk)

    doc_id = doc.id
    doc_title = doc.title or doc.original_filename
    doc_status = doc.status
    await session.delete(doc)
    await session.commit()

    logger.info("Task permanently deleted", extra={
        "document_id": doc_id,
        "document_title": doc_title,
        "previous_status": doc_status,
        "chunks_deleted": chunk_count,
    })
    return {"status": "deleted", "document_id": doc_id, "chunks_deleted": chunk_count}


@router.post("/tasks/bulk-delete")
async def bulk_delete_tasks(
    body: BulkDeleteRequest,
    session: AsyncSession = Depends(get_session),
):
    """Permanently delete multiple documents by IDs or by status filter."""
    from app.celery_app import celery
    from sqlalchemy import select as sa_select, delete as sa_delete
    from app.models import Document, Chunk
    from app.s3 import delete_file

    deleted = 0

    if body.document_ids:
        docs = (await session.execute(
            sa_select(Document).where(Document.id.in_(body.document_ids))
        )).scalars().all()
    elif body.filter_status:
        target = [body.filter_status]
        if body.filter_status == "stale":
            target = ["processing"]
        docs = (await session.execute(
            sa_select(Document).where(Document.status.in_(target)).limit(500)
        )).scalars().all()
    else:
        raise HTTPException(status_code=400, detail="Provide document_ids or filter_status")

    for doc in docs:
        if doc.celery_task_id:
            try:
                celery.control.revoke(doc.celery_task_id, terminate=True)
            except Exception:
                pass
        if doc.s3_key:
            try:
                delete_file(doc.s3_key)
            except Exception:
                pass

        await session.execute(
            sa_delete(Chunk).where(Chunk.document_id == doc.id)
        )
        await session.delete(doc)
        deleted += 1

    await session.commit()
    logger.info("Bulk delete completed", extra={"deleted": deleted})
    return {"status": "ok", "deleted": deleted}


# ---------------------------------------------------------------------------
# RAG Evaluation
# ---------------------------------------------------------------------------

@router.post("/rag-eval/run", response_model=RagEvalRunItem, status_code=201)
async def start_rag_eval(
    body: RagEvalRunRequest,
    tenant: Tenant = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    from sqlalchemy import select as sa_select
    from app.models import RagEvalRun

    running = (await session.execute(
        sa_select(RagEvalRun).where(RagEvalRun.status == "running").limit(1)
    )).scalar_one_or_none()
    if running:
        raise HTTPException(status.HTTP_409_CONFLICT, "An evaluation is already running")

    run = RagEvalRun(
        sample_size=body.sample_size,
        triggered_by=tenant.email,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)

    from app.celery_app import run_rag_evaluation_task
    run_rag_evaluation_task.delay(run.id)

    return run


@router.post("/rag-eval/runs/{run_id}/cancel")
async def cancel_rag_eval_run(
    run_id: int,
    session: AsyncSession = Depends(get_session),
    _: Tenant = Depends(require_admin),
):
    from app.models import RagEvalRun
    from datetime import datetime, timezone

    run = await session.get(RagEvalRun, run_id)
    if not run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Eval run not found")
    if run.status != "running":
        raise HTTPException(status.HTTP_409_CONFLICT, "Run is not active")

    run.status = "cancelled"
    run.finished_at = datetime.now(timezone.utc)
    run.error_message = "Cancelled by user"
    await session.commit()

    return {"status": "cancelled"}


@router.get("/rag-eval/runs", response_model=RagEvalRunListResponse)
async def list_rag_eval_runs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    from sqlalchemy import select as sa_select, func
    from app.models import RagEvalRun

    total = (await session.execute(
        sa_select(func.count()).select_from(RagEvalRun)
    )).scalar() or 0

    rows = (await session.execute(
        sa_select(RagEvalRun)
        .order_by(RagEvalRun.started_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )).scalars().all()

    return RagEvalRunListResponse(items=rows, total=total)


@router.get("/rag-eval/runs/{run_id}", response_model=RagEvalRunDetail)
async def get_rag_eval_run(
    run_id: int,
    session: AsyncSession = Depends(get_session),
):
    from app.models import RagEvalRun

    run = await session.get(RagEvalRun, run_id)
    if not run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Eval run not found")
    return run


@router.get("/rag-eval/latest", response_model=RagEvalRunDetail | None)
async def get_latest_rag_eval(session: AsyncSession = Depends(get_session)):
    from sqlalchemy import select as sa_select
    from app.models import RagEvalRun

    run = (await session.execute(
        sa_select(RagEvalRun)
        .where(RagEvalRun.status == "completed")
        .order_by(RagEvalRun.started_at.desc())
        .limit(1)
    )).scalar_one_or_none()

    return run
