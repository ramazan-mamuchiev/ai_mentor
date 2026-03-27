"""Auth REST endpoints: register, login, refresh, me, OAuth, API keys."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
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

    from sqlalchemy import text

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
