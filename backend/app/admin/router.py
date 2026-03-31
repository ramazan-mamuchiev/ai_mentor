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
    RoleCreateRequest,
    RoleDetail,
    RoleListItem,
    RolePatchRequest,
    SearchStat,
    SystemInfo,
    TenantDetail,
    TenantListResponse,
    TenantPatchRequest,
    TenantRoleAssignRequest,
    TenantRoleItem,
    UsageStatsResponse,
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
):
    result = await service.patch_tenant(session, tenant_id, is_active=False)
    if not result:
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
    session: AsyncSession = Depends(get_session),
):
    daily = await service.get_usage_stats(session, days=days)
    return UsageStatsResponse(daily=daily)


@router.get("/stats/models", response_model=list[ModelUsageStat])
async def stats_models(
    days: int = Query(30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
):
    return await service.get_model_stats(session, days=days)


@router.get("/stats/ingestion", response_model=IngestionStat)
async def stats_ingestion(session: AsyncSession = Depends(get_session)):
    return await service.get_ingestion_stats(session)


@router.get("/stats/search", response_model=SearchStat)
async def stats_search(
    days: int = Query(30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
):
    return await service.get_search_stats(session, days=days)


@router.get("/stats/chat", response_model=ChatStats)
async def stats_chat(
    days: int = Query(30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
):
    return await service.get_chat_stats(session, days=days)


@router.get("/stats/documents", response_model=DocumentStats)
async def stats_documents(
    days: int = Query(30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
):
    return await service.get_document_stats(session, days=days)


@router.get("/stats/search-extended", response_model=ExtendedSearchStats)
async def stats_search_extended(
    days: int = Query(30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
):
    return await service.get_extended_search_stats(session, days=days)


@router.get("/stats/costs", response_model=CostStats)
async def stats_costs(
    days: int = Query(30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
):
    return await service.get_cost_stats(session, days=days)


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
