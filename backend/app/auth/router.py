"""Auth REST endpoints: register, login, refresh, me, OAuth, API keys."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_tenant
from app.auth.schemas import (
    ApiKeyCreatedResponse,
    ApiKeyResponse,
    CreateApiKeyRequest,
    LoginRequest,
    MeResponse,
    OAuthCallbackResponse,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
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
    tenant, raw_key = await register_tenant(body.email, body.password, session)
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
async def me(tenant: Tenant = Depends(get_current_tenant)):
    return MeResponse(
        id=tenant.id,
        email=tenant.email,
        name=tenant.name,
        slug=tenant.slug,
        tier=tenant.tier,
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
    import logging
    _log = logging.getLogger("app.auth.oauth")
    stored_state = request.cookies.get("oauth_state")
    _log.warning("OAuth callback: cookies=%s, stored_state=%s, expected_state=%s, secure=%s",
                 dict(request.cookies), stored_state, state, _COOKIE_SECURE)
    if not stored_state or stored_state != state:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid OAuth state")

    import httpx

    if provider == "google":
        async with httpx.AsyncClient() as client:
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

    elif provider == "github":
        async with httpx.AsyncClient() as client:
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

    tenant, is_new = await find_or_create_oauth_tenant(provider, oauth_id, email, session)
    access, refresh = await create_token_pair(tenant.id, session)

    from starlette.responses import RedirectResponse
    redirect_path = "/" if not is_new else "/?onboarding=true"
    resp = RedirectResponse(redirect_path, status_code=302)
    _set_tokens(resp, access, refresh)
    resp.delete_cookie("oauth_state", path="/")
    return resp
