"""Auth REST endpoints: register, login, refresh, me, OAuth, API keys."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_tenant
from app.auth.schemas import (
    ApiKeyCreatedResponse,
    ApiKeyResponse,
    ApiKeyUsageResponse,
    CreateApiKeyRequest,
    LoginRequest,
    MeResponse,
    OAuthCallbackResponse,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
    UpdateMeRequest,
    UsageSummaryResponse,
)
from app.auth.service import (
    authenticate_tenant,
    create_api_key,
    create_token_pair,
    delete_api_key,
    find_or_create_oauth_tenant,
    list_api_keys,
    register_tenant,
    revoke_all_refresh_tokens,
    rotate_refresh_token,
)
from app.config import settings
from app.database import get_session
from app.models import Tenant

router = APIRouter(prefix="/api/v1", tags=["auth"])

_COOKIE_SECURE = settings.app_base_url.startswith("https")

_COOKIE_OPTS: dict = {
    "httponly": True,
    "secure": _COOKIE_SECURE,
    "samesite": "lax",
    "path": "/",
}


def _set_tokens(response: Response, access: str, refresh: str) -> None:
    response.set_cookie("access_token", access, max_age=settings.jwt_access_token_minutes * 60, **_COOKIE_OPTS)
    response.set_cookie("refresh_token", refresh, max_age=settings.jwt_refresh_token_days * 86400, **_COOKIE_OPTS)


# ---------------------------------------------------------------------------
# Register / Login / Refresh / Logout
# ---------------------------------------------------------------------------

@router.post("/register", response_model=RegisterResponse, status_code=201)
async def register(body: RegisterRequest, response: Response, session: AsyncSession = Depends(get_session)):
    tenant, raw_key = await register_tenant(body.email, body.password, session, name=body.name)
    access, refresh = await create_token_pair(tenant.id, session)
    _set_tokens(response, access, refresh)
    return RegisterResponse(id=tenant.id, email=tenant.email, slug=tenant.slug, api_key=raw_key)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, response: Response, session: AsyncSession = Depends(get_session)):
    tenant = await authenticate_tenant(body.email, body.password, session)
    access, refresh = await create_token_pair(tenant.id, session)
    _set_tokens(response, access, refresh)
    return TokenResponse(access_token=access)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: Request, response: Response, session: AsyncSession = Depends(get_session)):
    raw_refresh = request.cookies.get("refresh_token")
    if not raw_refresh:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No refresh token")
    access, new_refresh, _ = await rotate_refresh_token(raw_refresh, session)
    _set_tokens(response, access, new_refresh)
    return TokenResponse(access_token=access)


@router.post("/logout", status_code=204)
async def logout(
    response: Response,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    await revoke_all_refresh_tokens(tenant.id, session)
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")


# ---------------------------------------------------------------------------
# Current user
# ---------------------------------------------------------------------------

@router.get("/me", response_model=MeResponse)
async def me(request: Request, tenant: Tenant = Depends(get_current_tenant)):
    from app.auth.schemas import RoleBrief
    tenant_roles = getattr(request.state, "tenant_roles", [])
    permissions = getattr(request.state, "permissions", {})
    return MeResponse(
        id=tenant.id,
        email=tenant.email,
        name=tenant.name,
        slug=tenant.slug,
        tier=tenant.tier,
        role=tenant.role,
        roles=[
            RoleBrief(id=r.id, slug=r.slug, name=r.name, priority=r.priority)
            for r in tenant_roles
        ],
        permissions=permissions,
        email_verified=tenant.email_verified,
        created_at=tenant.created_at,
    )


@router.patch("/me", response_model=MeResponse)
async def update_me(
    request: Request,
    body: UpdateMeRequest,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    from app.auth.schemas import RoleBrief
    if body.name is not None:
        tenant.name = body.name
    session.add(tenant)
    await session.commit()
    await session.refresh(tenant)
    tenant_roles = getattr(request.state, "tenant_roles", [])
    permissions = getattr(request.state, "permissions", {})
    return MeResponse(
        id=tenant.id,
        email=tenant.email,
        name=tenant.name,
        slug=tenant.slug,
        tier=tenant.tier,
        role=tenant.role,
        roles=[
            RoleBrief(id=r.id, slug=r.slug, name=r.name, priority=r.priority)
            for r in tenant_roles
        ],
        permissions=permissions,
        email_verified=tenant.email_verified,
        created_at=tenant.created_at,
    )


# ---------------------------------------------------------------------------
# Auth providers info (public, no auth required)
# ---------------------------------------------------------------------------

@router.get("/auth/providers")
async def auth_providers():
    """Return which OAuth providers are configured."""
    return {
        "google": bool(settings.google_client_id),
        "github": bool(settings.github_client_id),
    }


# ---------------------------------------------------------------------------
# API Keys CRUD
# ---------------------------------------------------------------------------

@router.get("/api-keys", response_model=list[ApiKeyResponse])
async def get_api_keys(
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    keys = await list_api_keys(tenant.id, session)
    return [
        ApiKeyResponse(
            id=k.id, key_prefix=k.key_prefix, name=k.name, scopes=k.scopes,
            is_active=k.is_active, last_used_at=k.last_used_at, created_at=k.created_at,
        )
        for k in keys
    ]


@router.post("/api-keys", response_model=ApiKeyCreatedResponse, status_code=201)
async def create_key(
    body: CreateApiKeyRequest,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    api_key, raw = await create_api_key(tenant.id, body.name, body.scopes, session)
    return ApiKeyCreatedResponse(
        id=api_key.id, key_prefix=api_key.key_prefix, name=api_key.name,
        scopes=api_key.scopes, is_active=api_key.is_active,
        last_used_at=api_key.last_used_at, created_at=api_key.created_at,
        key=raw,
    )


@router.delete("/api-keys/{key_id}", status_code=204)
async def remove_key(
    key_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    import uuid as _uuid
    try:
        kid = _uuid.UUID(key_id)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid key id")
    if not await delete_api_key(tenant.id, kid, session):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "API key not found")


# ---------------------------------------------------------------------------
# Usage analytics
# ---------------------------------------------------------------------------

@router.get("/api-keys/{key_id}/usage", response_model=ApiKeyUsageResponse)
async def get_api_key_usage(
    key_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    """Usage statistics for a specific API key (last 30 days)."""
    import uuid as _uuid
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import func, text

    try:
        kid = _uuid.UUID(key_id)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid key id")

    from sqlalchemy import select as sa_select

    from app.models import ApiKey
    ak = await session.scalar(
        sa_select(ApiKey).where(ApiKey.id == kid, ApiKey.tenant_id == tenant.id)
    )
    if not ak:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "API key not found")

    since = datetime.now(timezone.utc) - timedelta(days=30)

    totals = (await session.execute(text(
        "SELECT COUNT(*) AS cnt, COALESCE(SUM(total_tokens),0) AS tokens, "
        "COALESCE(SUM(charge_usd),0) AS charge "
        "FROM usage_log WHERE api_key_id = :kid AND created_at >= :since"
    ), {"kid": kid, "since": since})).mappings().one()

    by_action_rows = (await session.execute(text(
        "SELECT action, COUNT(*) AS cnt, COALESCE(SUM(total_tokens),0) AS tokens "
        "FROM usage_log WHERE api_key_id = :kid AND created_at >= :since "
        "GROUP BY action ORDER BY cnt DESC"
    ), {"kid": kid, "since": since})).mappings().all()

    daily_rows = (await session.execute(text(
        "SELECT DATE(created_at) AS d, COUNT(*) AS cnt, COALESCE(SUM(total_tokens),0) AS tokens "
        "FROM usage_log WHERE api_key_id = :kid AND created_at >= :since "
        "GROUP BY DATE(created_at) ORDER BY d"
    ), {"kid": kid, "since": since})).mappings().all()

    from app.auth.schemas import ActionBreakdown, DailyUsage
    return ApiKeyUsageResponse(
        total_requests=int(totals["cnt"]),
        total_tokens=int(totals["tokens"]),
        total_charge_usd=str(totals["charge"]),
        by_action=[ActionBreakdown(action=r["action"], count=int(r["cnt"]), tokens=int(r["tokens"])) for r in by_action_rows],
        daily=[DailyUsage(date=str(r["d"]), requests=int(r["cnt"]), tokens=int(r["tokens"])) for r in daily_rows],
    )


@router.get("/usage/summary", response_model=UsageSummaryResponse)
async def get_usage_summary(
    days: int = 30,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    """Aggregated usage summary for the current tenant."""
    from datetime import datetime, timedelta, timezone

    days = max(1, min(days, 365))
    since = datetime.now(timezone.utc) - timedelta(days=days)
    tid = tenant.id

    totals = (await session.execute(text(
        "SELECT COUNT(*) AS cnt, COALESCE(SUM(total_tokens),0) AS tokens, "
        "COALESCE(SUM(charge_usd),0) AS charge "
        "FROM usage_log WHERE tenant_id = :tid AND created_at >= :since"
    ), {"tid": tid, "since": since})).mappings().one()

    by_action_rows = (await session.execute(text(
        "SELECT action, COUNT(*) AS cnt, COALESCE(SUM(total_tokens),0) AS tokens "
        "FROM usage_log WHERE tenant_id = :tid AND created_at >= :since "
        "GROUP BY action ORDER BY cnt DESC"
    ), {"tid": tid, "since": since})).mappings().all()

    daily_rows = (await session.execute(text(
        "SELECT DATE(created_at) AS d, COUNT(*) AS cnt, COALESCE(SUM(total_tokens),0) AS tokens "
        "FROM usage_log WHERE tenant_id = :tid AND created_at >= :since "
        "GROUP BY DATE(created_at) ORDER BY d"
    ), {"tid": tid, "since": since})).mappings().all()

    by_key_rows = (await session.execute(text(
        "SELECT u.api_key_id, k.name AS key_name, k.key_prefix, "
        "COUNT(*) AS cnt, COALESCE(SUM(u.total_tokens),0) AS tokens, "
        "COALESCE(SUM(u.charge_usd),0) AS charge "
        "FROM usage_log u "
        "LEFT JOIN api_keys k ON k.id = u.api_key_id "
        "WHERE u.tenant_id = :tid AND u.created_at >= :since AND u.api_key_id IS NOT NULL "
        "GROUP BY u.api_key_id, k.name, k.key_prefix "
        "ORDER BY cnt DESC LIMIT 50"
    ), {"tid": tid, "since": since})).mappings().all()

    from app.models import ApiKey
    active_keys = await session.scalar(text(
        "SELECT COUNT(*) FROM api_keys WHERE tenant_id = :tid AND is_active = true"
    ), {"tid": tid})

    from app.auth.schemas import ActionBreakdown, DailyUsage, KeySummary
    return UsageSummaryResponse(
        total_requests=int(totals["cnt"]),
        total_tokens=int(totals["tokens"]),
        total_charge_usd=str(totals["charge"]),
        active_keys=int(active_keys or 0),
        by_action=[ActionBreakdown(action=r["action"], count=int(r["cnt"]), tokens=int(r["tokens"])) for r in by_action_rows],
        daily=[DailyUsage(date=str(r["d"]), requests=int(r["cnt"]), tokens=int(r["tokens"])) for r in daily_rows],
        by_key=[KeySummary(
            key_id=str(r["api_key_id"]),
            key_name=r["key_name"] or "",
            key_prefix=r["key_prefix"] or "",
            total_requests=int(r["cnt"]),
            total_tokens=int(r["tokens"]),
            total_charge_usd=str(r["charge"]),
        ) for r in by_key_rows],
    )


# ---------------------------------------------------------------------------
# User-level extended analytics
# ---------------------------------------------------------------------------

@router.get("/analytics/chat")
async def user_chat_stats(
    days: int = 30,
    tenant: "Tenant" = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    from datetime import datetime, timedelta, timezone
    from app.auth.schemas import UserChatStats

    days = max(1, min(days, 365))
    since = datetime.now(timezone.utc) - timedelta(days=days)
    tid = tenant.id

    total_sessions = await session.scalar(text(
        "SELECT COUNT(*) FROM chat_sessions WHERE tenant_id = :tid AND created_at >= :since"
    ), {"tid": tid, "since": since}) or 0

    total_messages = await session.scalar(text(
        "SELECT COUNT(*) FROM chat_messages cm "
        "JOIN chat_sessions cs ON cs.id = cm.session_id "
        "WHERE cs.tenant_id = :tid AND cm.created_at >= :since AND cm.role = 'assistant'"
    ), {"tid": tid, "since": since}) or 0

    avg_msgs = await session.scalar(text(
        "SELECT AVG(mc) FROM ("
        "  SELECT COUNT(*) AS mc FROM chat_messages cm "
        "  JOIN chat_sessions cs ON cs.id = cm.session_id "
        "  WHERE cs.tenant_id = :tid AND cs.created_at >= :since "
        "  GROUP BY cs.id"
        ") sub"
    ), {"tid": tid, "since": since})

    fb_rows = (await session.execute(text(
        "SELECT cm.feedback, COUNT(*) AS cnt FROM chat_messages cm "
        "JOIN chat_sessions cs ON cs.id = cm.session_id "
        "WHERE cs.tenant_id = :tid AND cm.created_at >= :since AND cm.role = 'assistant' AND cm.feedback IS NOT NULL "
        "GROUP BY cm.feedback"
    ), {"tid": tid, "since": since})).mappings().all()
    fb_pos = sum(r["cnt"] for r in fb_rows if r["feedback"] == "positive")
    fb_neg = sum(r["cnt"] for r in fb_rows if r["feedback"] == "negative")
    fb_total = fb_pos + fb_neg

    qt_rows = (await session.execute(text(
        "SELECT cma.query_type, COUNT(*) AS cnt FROM chat_message_analytics cma "
        "JOIN chat_sessions cs ON cs.id = cma.session_id "
        "WHERE cs.tenant_id = :tid AND cma.created_at >= :since AND cma.query_type IS NOT NULL "
        "GROUP BY cma.query_type ORDER BY cnt DESC"
    ), {"tid": tid, "since": since})).mappings().all()
    qt_total = sum(r["cnt"] for r in qt_rows) or 1
    query_types = [{"query_type": r["query_type"], "count": int(r["cnt"]), "pct": round(int(r["cnt"]) / qt_total * 100, 1)} for r in qt_rows]

    timing = (await session.execute(text(
        "SELECT AVG(cma.total_ms) AS avg_total, AVG(cma.tokens_per_sec) AS avg_tps "
        "FROM chat_message_analytics cma "
        "JOIN chat_sessions cs ON cs.id = cma.session_id "
        "WHERE cs.tenant_id = :tid AND cma.created_at >= :since"
    ), {"tid": tid, "since": since})).mappings().one()

    resp_daily = (await session.execute(text(
        "SELECT DATE(cma.created_at) AS d, AVG(cma.total_ms) AS avg_total "
        "FROM chat_message_analytics cma "
        "JOIN chat_sessions cs ON cs.id = cma.session_id "
        "WHERE cs.tenant_id = :tid AND cma.created_at >= :since "
        "GROUP BY DATE(cma.created_at) ORDER BY d"
    ), {"tid": tid, "since": since})).mappings().all()

    return UserChatStats(
        total_sessions=int(total_sessions),
        total_messages=int(total_messages),
        avg_messages_per_session=round(float(avg_msgs), 1) if avg_msgs else None,
        feedback_positive=fb_pos,
        feedback_negative=fb_neg,
        feedback_total=fb_total,
        positive_rate=round(fb_pos / fb_total * 100, 1) if fb_total > 0 else None,
        query_types=query_types,
        avg_response_ms=round(float(timing["avg_total"]), 1) if timing["avg_total"] else None,
        avg_tokens_per_sec=round(float(timing["avg_tps"]), 1) if timing["avg_tps"] else None,
        response_daily=[{"date": str(r["d"]), "avg_total": round(float(r["avg_total"] or 0), 1)} for r in resp_daily],
    )


@router.get("/analytics/documents")
async def user_doc_stats(
    days: int = 30,
    tenant: "Tenant" = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    from datetime import datetime, timedelta, timezone
    from app.auth.schemas import UserDocStats

    days = max(1, min(days, 365))
    since = datetime.now(timezone.utc) - timedelta(days=days)
    tid = tenant.id

    totals = (await session.execute(text(
        "SELECT COUNT(*) AS total, "
        "COUNT(*) FILTER (WHERE status = 'ready') AS indexed, "
        "COUNT(*) FILTER (WHERE status IN ('pending','processing')) AS pending, "
        "COUNT(*) FILTER (WHERE status = 'error') AS errors, "
        "COALESCE(SUM(total_chunks),0) AS chunks, "
        "COALESCE(SUM(file_size_bytes),0) AS size_bytes, "
        "COALESCE(SUM(ocr_prompt_tokens),0) AS ocr_prompt, "
        "COALESCE(SUM(ocr_completion_tokens),0) AS ocr_completion, "
        "COUNT(*) FILTER (WHERE ocr_prompt_tokens > 0 OR ocr_completion_tokens > 0) AS ocr_docs "
        "FROM documents WHERE tenant_id = :tid"
    ), {"tid": tid})).mappings().one()

    fmt_rows = (await session.execute(text(
        "SELECT format, COUNT(*) AS cnt FROM documents WHERE tenant_id = :tid GROUP BY format ORDER BY cnt DESC"
    ), {"tid": tid})).mappings().all()
    fmt_total = sum(r["cnt"] for r in fmt_rows) or 1

    prod_rows = (await session.execute(text(
        "SELECT p.name, COUNT(*) AS cnt FROM documents d "
        "JOIN products p ON p.id = d.product_id "
        "WHERE d.tenant_id = :tid GROUP BY p.name ORDER BY cnt DESC LIMIT 10"
    ), {"tid": tid})).mappings().all()

    uploads = (await session.execute(text(
        "SELECT DATE(uploaded_at) AS d, COUNT(*) AS cnt FROM documents "
        "WHERE tenant_id = :tid AND uploaded_at >= :since "
        "GROUP BY DATE(uploaded_at) ORDER BY d"
    ), {"tid": tid, "since": since})).mappings().all()

    ocr_prompt = int(totals["ocr_prompt"])
    ocr_completion = int(totals["ocr_completion"])

    return UserDocStats(
        total_documents=int(totals["total"]),
        documents_indexed=int(totals["indexed"]),
        documents_pending=int(totals["pending"]),
        documents_error=int(totals["errors"]),
        total_chunks=int(totals["chunks"]),
        total_size_bytes=int(totals["size_bytes"]),
        ocr_prompt_tokens=ocr_prompt,
        ocr_completion_tokens=ocr_completion,
        ocr_total_tokens=ocr_prompt + ocr_completion,
        ocr_documents=int(totals["ocr_docs"]),
        formats=[{"format": r["format"], "count": int(r["cnt"]), "pct": round(int(r["cnt"]) / fmt_total * 100, 1)} for r in fmt_rows],
        products=[{"name": r["name"], "count": int(r["cnt"])} for r in prod_rows],
        uploads_daily=[{"date": str(r["d"]), "count": int(r["cnt"])} for r in uploads],
    )


@router.get("/analytics/search")
async def user_search_stats(
    days: int = 30,
    tenant: "Tenant" = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    from datetime import datetime, timedelta, timezone
    from app.auth.schemas import UserSearchStats

    days = max(1, min(days, 365))
    since = datetime.now(timezone.utc) - timedelta(days=days)
    tid = tenant.id

    totals = (await session.execute(text(
        "SELECT COUNT(*) AS cnt, AVG(top_similarity) AS avg_sim, AVG(duration_ms) AS avg_dur, "
        "COUNT(*) FILTER (WHERE result_count = 0) AS zero "
        "FROM search_analytics WHERE tenant_id = :tid AND created_at >= :since"
    ), {"tid": tid, "since": since})).mappings().one()

    top_q = (await session.execute(text(
        "SELECT query, COUNT(*) AS cnt FROM search_analytics "
        "WHERE tenant_id = :tid AND created_at >= :since "
        "GROUP BY query ORDER BY cnt DESC LIMIT 10"
    ), {"tid": tid, "since": since})).mappings().all()

    daily = (await session.execute(text(
        "SELECT DATE(created_at) AS d, COUNT(*) AS cnt, AVG(top_similarity) AS avg_sim "
        "FROM search_analytics WHERE tenant_id = :tid AND created_at >= :since "
        "GROUP BY DATE(created_at) ORDER BY d"
    ), {"tid": tid, "since": since})).mappings().all()

    return UserSearchStats(
        total_searches=int(totals["cnt"]),
        avg_similarity=round(float(totals["avg_sim"]), 4) if totals["avg_sim"] else None,
        avg_duration_ms=round(float(totals["avg_dur"]), 1) if totals["avg_dur"] else None,
        zero_result_count=int(totals["zero"]),
        top_queries=[{"query": r["query"][:100], "count": int(r["cnt"])} for r in top_q],
        daily=[{"date": str(r["d"]), "count": int(r["cnt"]), "avg_similarity": round(float(r["avg_sim"] or 0), 4)} for r in daily],
    )


@router.get("/analytics/costs")
async def user_cost_stats(
    days: int = 30,
    tenant: "Tenant" = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    from datetime import datetime, timedelta, timezone
    from decimal import Decimal
    from app.auth.schemas import UserCostStats

    days = max(1, min(days, 365))
    since = datetime.now(timezone.utc) - timedelta(days=days)
    tid = tenant.id

    totals = (await session.execute(text(
        "SELECT COALESCE(SUM(charge_usd),0) AS charge, COUNT(*) AS cnt "
        "FROM usage_log WHERE tenant_id = :tid AND created_at >= :since"
    ), {"tid": tid, "since": since})).mappings().one()
    total_charge = Decimal(str(totals["charge"]))
    avg_per_day = total_charge / days if days > 0 else Decimal("0")
    forecast = avg_per_day * 30

    ocr_totals = (await session.execute(text(
        "SELECT COALESCE(SUM(ocr_prompt_tokens),0) AS ocr_prompt, "
        "COALESCE(SUM(ocr_completion_tokens),0) AS ocr_completion "
        "FROM documents WHERE tenant_id = :tid AND uploaded_at >= :since"
    ), {"tid": tid, "since": since})).mappings().one()
    ocr_prompt = int(ocr_totals["ocr_prompt"])
    ocr_completion = int(ocr_totals["ocr_completion"])
    ocr_total_tokens = ocr_prompt + ocr_completion

    from app.billing.pricing import calculate_llm_charge
    ocr_cost = calculate_llm_charge("gemini-2.0-flash", ocr_prompt, ocr_completion)

    daily = (await session.execute(text(
        "SELECT DATE(created_at) AS d, COALESCE(SUM(charge_usd),0) AS charge, COUNT(*) AS cnt "
        "FROM usage_log WHERE tenant_id = :tid AND created_at >= :since "
        "GROUP BY DATE(created_at) ORDER BY d"
    ), {"tid": tid, "since": since})).mappings().all()

    by_model = (await session.execute(text(
        "SELECT llm_model AS model, llm_provider AS provider, COALESCE(SUM(charge_usd),0) AS charge, "
        "COALESCE(SUM(total_tokens),0) AS tokens, COUNT(*) AS cnt "
        "FROM usage_log WHERE tenant_id = :tid AND created_at >= :since "
        "GROUP BY llm_model, llm_provider ORDER BY charge DESC LIMIT 10"
    ), {"tid": tid, "since": since})).mappings().all()

    by_channel = (await session.execute(text(
        "SELECT channel, COALESCE(SUM(charge_usd),0) AS charge, COUNT(*) AS cnt "
        "FROM usage_log WHERE tenant_id = :tid AND created_at >= :since "
        "GROUP BY channel ORDER BY charge DESC"
    ), {"tid": tid, "since": since})).mappings().all()

    return UserCostStats(
        total_charge_usd=str(total_charge),
        avg_per_day=str(round(avg_per_day, 8)),
        forecast_month_usd=str(round(forecast, 8)),
        ocr_total_tokens=ocr_total_tokens,
        ocr_cost_usd=str(ocr_cost),
        daily=[{"date": str(r["d"]), "charge_usd": str(r["charge"]), "requests": int(r["cnt"])} for r in daily],
        by_model=[{"model": r["model"], "provider": r["provider"], "total_charge_usd": str(r["charge"]),
                   "total_tokens": int(r["tokens"]), "request_count": int(r["cnt"])} for r in by_model],
        by_channel=[{"channel": r["channel"], "total_charge_usd": str(r["charge"]),
                     "request_count": int(r["cnt"])} for r in by_channel],
    )


# ---------------------------------------------------------------------------
# OAuth endpoints
# ---------------------------------------------------------------------------

@router.get("/oauth/{provider}/authorize")
async def oauth_authorize(provider: str, request: Request):
    """Redirect to provider's authorization URL."""
    import secrets as _secrets
    state = _secrets.token_urlsafe(32)

    if provider == "google":
        if not settings.google_client_id:
            raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Google OAuth not configured")
        from urllib.parse import urlencode
        params = urlencode({
            "client_id": settings.google_client_id,
            "redirect_uri": f"{settings.app_base_url}/api/v1/oauth/google/callback",
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "offline",
        })
        url = f"https://accounts.google.com/o/oauth2/v2/auth?{params}"
    elif provider == "github":
        if not settings.github_client_id:
            raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "GitHub OAuth not configured")
        from urllib.parse import urlencode
        params = urlencode({
            "client_id": settings.github_client_id,
            "redirect_uri": f"{settings.app_base_url}/api/v1/oauth/github/callback",
            "scope": "read:user user:email",
            "state": state,
        })
        url = f"https://github.com/login/oauth/authorize?{params}"
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown provider: {provider}")

    from starlette.responses import RedirectResponse
    resp = RedirectResponse(url, status_code=302)
    resp.set_cookie("oauth_state", state, max_age=600, **_COOKIE_OPTS)
    return resp


@router.get("/oauth/{provider}/callback")
async def oauth_callback(
    provider: str,
    code: str,
    state: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Exchange code for tokens, find/create tenant, redirect to app."""
    stored_state = request.cookies.get("oauth_state")
    if not stored_state or stored_state != state:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid OAuth state")

    import httpx

    if provider == "google":
        async with httpx.AsyncClient(timeout=30) as client:
            token_resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "redirect_uri": f"{settings.app_base_url}/api/v1/oauth/google/callback",
                    "grant_type": "authorization_code",
                },
            )
            if token_resp.status_code != 200:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Google token exchange failed")
            tokens = token_resp.json()

            userinfo_resp = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
            )
            userinfo = userinfo_resp.json()
            oauth_id = userinfo["id"]
            email = userinfo["email"]
            oauth_name = userinfo.get("name")

    elif provider == "github":
        async with httpx.AsyncClient(timeout=30) as client:
            token_resp = await client.post(
                "https://github.com/login/oauth/access_token",
                json={
                    "client_id": settings.github_client_id,
                    "client_secret": settings.github_client_secret,
                    "code": code,
                    "redirect_uri": f"{settings.app_base_url}/api/v1/oauth/github/callback",
                },
                headers={"Accept": "application/json"},
            )
            if token_resp.status_code != 200:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "GitHub token exchange failed")
            tokens = token_resp.json()
            gh_token = tokens.get("access_token")
            if not gh_token:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "GitHub access_token missing")

            user_resp = await client.get(
                "https://api.github.com/user",
                headers={"Authorization": f"Bearer {gh_token}"},
            )
            user_data = user_resp.json()
            oauth_id = str(user_data["id"])
            oauth_name = user_data.get("name") or user_data.get("login")

            emails_resp = await client.get(
                "https://api.github.com/user/emails",
                headers={"Authorization": f"Bearer {gh_token}"},
            )
            emails = emails_resp.json()
            primary = next((e for e in emails if e.get("primary")), emails[0] if emails else None)
            if not primary:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "No email from GitHub")
            email = primary["email"]
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown provider: {provider}")

    tenant, is_new = await find_or_create_oauth_tenant(provider, oauth_id, email, session, name=oauth_name)
    access, refresh = await create_token_pair(tenant.id, session)

    from starlette.responses import RedirectResponse
    redirect_path = "/app" if not is_new else "/app?onboarding=true"
    resp = RedirectResponse(redirect_path, status_code=302)
    _set_tokens(resp, access, refresh)
    resp.delete_cookie("oauth_state", path="/")
    return resp
