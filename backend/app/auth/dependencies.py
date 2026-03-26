"""FastAPI dependencies for authentication (JWT cookie + API Key header)."""

import uuid

import jwt as pyjwt
from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import decode_access_token, hash_refresh_token
from app.database import get_session
from app.models import ApiKey, Tenant

_BEARER = "Bearer "


async def _resolve_api_key(raw_key: str, session: AsyncSession) -> Tenant:
    """Look up tenant by raw API key (ipx_...)."""
    import hashlib
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    result = await session.execute(
        select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active.is_(True))
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")

    result = await session.execute(
        select(Tenant).where(Tenant.id == api_key.tenant_id, Tenant.is_active.is_(True))
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Tenant not found or disabled")

    from datetime import datetime, timezone
    api_key.last_used_at = datetime.now(timezone.utc)
    await session.commit()
    return tenant


async def _resolve_jwt(token: str, session: AsyncSession) -> Tenant:
    """Look up tenant from JWT access token."""
    try:
        payload = decode_access_token(token)
    except pyjwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    tenant_id = uuid.UUID(payload["sub"])
    result = await session.execute(
        select(Tenant).where(Tenant.id == tenant_id, Tenant.is_active.is_(True))
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Tenant not found or disabled")
    return tenant


async def get_current_tenant(
    request: Request,
    session: AsyncSession = Depends(get_session),
    access_token: str | None = Cookie(default=None),
) -> Tenant:
    """Extract tenant from JWT cookie, Authorization header (Bearer JWT or API key).

    Priority:
      1. Authorization: Bearer ipx_...  (API key)
      2. Authorization: Bearer <jwt>     (JWT from programmatic clients)
      3. access_token cookie             (JWT from browser)
    """
    auth_header: str | None = request.headers.get("authorization")

    if auth_header and auth_header.startswith(_BEARER):
        token = auth_header[len(_BEARER):]
        if token.startswith("ipx_"):
            return await _resolve_api_key(token, session)
        return await _resolve_jwt(token, session)

    if access_token:
        return await _resolve_jwt(access_token, session)

    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")


async def get_current_tenant_optional(
    request: Request,
    session: AsyncSession = Depends(get_session),
    access_token: str | None = Cookie(default=None),
) -> Tenant | None:
    """Like get_current_tenant, but returns None instead of 401 for unauthenticated."""
    try:
        return await get_current_tenant(request, session, access_token)
    except HTTPException:
        return None
