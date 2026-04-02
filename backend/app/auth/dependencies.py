"""FastAPI dependencies for authentication (JWT cookie + API Key header)."""

from __future__ import annotations

import logging
import uuid

import jwt as pyjwt
from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.jwt import decode_access_token, hash_refresh_token
from app.auth.permissions import has_permission, merge_permissions
from app.database import get_session
from app.models import ApiKey, Role, Tenant, TenantRole

logger = logging.getLogger(__name__)

_BEARER = "Bearer "


async def _resolve_api_key(raw_key: str, session: AsyncSession) -> tuple[Tenant, uuid.UUID]:
    """Look up tenant by raw API key (ipx_...). Returns (tenant, api_key_id)."""
    from app.auth.service import hash_api_key
    key_hash = hash_api_key(raw_key)
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
    return tenant, api_key.id


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


async def _load_tenant_roles(tenant_id: uuid.UUID, session: AsyncSession) -> list[Role]:
    """Load roles for a tenant, sorted by priority descending."""
    result = await session.execute(
        select(Role)
        .join(TenantRole, TenantRole.role_id == Role.id)
        .where(TenantRole.tenant_id == tenant_id)
        .order_by(Role.priority.desc())
    )
    return list(result.scalars().all())


async def _enrich_with_roles(
    tenant: Tenant, request: Request, session: AsyncSession,
) -> Tenant:
    """Load tenant roles and compute effective permissions into request.state."""
    from app.logging_config import tenant_id_ctx, tenant_name_ctx

    roles = await _load_tenant_roles(tenant.id, session)
    request.state.tenant = tenant
    request.state.tenant_roles = roles
    request.state.permissions = merge_permissions(roles)
    tenant_id_ctx.set(str(tenant.id))
    tenant_name_ctx.set(tenant.name or "-")
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
            tenant, api_key_id = await _resolve_api_key(token, session)
            request.state.api_key_id = api_key_id
            return await _enrich_with_roles(tenant, request, session)
        request.state.api_key_id = None
        tenant = await _resolve_jwt(token, session)
        return await _enrich_with_roles(tenant, request, session)

    if access_token:
        request.state.api_key_id = None
        tenant = await _resolve_jwt(access_token, session)
        return await _enrich_with_roles(tenant, request, session)

    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")


def require_permission(key: str):
    """Factory: return a FastAPI dependency that checks a feature permission."""
    async def _dep(
        request: Request,
        tenant: Tenant = Depends(get_current_tenant),
    ) -> Tenant:
        if not has_permission(request.state.permissions, key):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Permission '{key}' required",
            )
        return tenant
    _dep.__doc__ = f"Require permission '{key}'."
    return _dep


async def require_email_verified(
    tenant: Tenant = Depends(get_current_tenant),
) -> Tenant:
    """Raise 403 if the tenant has not verified their email address."""
    if not tenant.email_verified:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={"code": "EMAIL_NOT_VERIFIED", "message": "Email not verified"},
        )
    return tenant


async def require_admin(
    request: Request,
    tenant: Tenant = Depends(require_email_verified),
) -> Tenant:
    """Raise 403 unless the tenant has the 'admin' feature permission."""
    if not has_permission(request.state.permissions, "admin"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
    return tenant


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
