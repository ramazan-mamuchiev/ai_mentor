"""Core auth business logic: register, login, token management, OAuth."""

import hashlib
import hmac
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import create_access_token, create_refresh_token, hash_refresh_token
from app.auth.password import hash_password, verify_password
from app.config import settings
from app.models import ApiKey, RefreshToken, Tenant, TenantOAuthLink


def _slug_from_email(email: str) -> str:
    """Derive a URL-safe slug from the email domain (or username if generic domain)."""
    local, domain = email.split("@", 1)
    generic = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "mail.ru", "yandex.ru", "icloud.com"}
    base = local if domain.lower() in generic else domain.split(".")[0]
    slug = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")
    return slug or "user"


async def _ensure_unique_slug(slug: str, session: AsyncSession) -> str:
    """Append a random suffix if the slug already exists."""
    result = await session.execute(select(Tenant.id).where(Tenant.slug == slug))
    if result.scalar_one_or_none() is None:
        return slug
    return f"{slug}-{secrets.token_hex(3)}"


def hash_api_key(raw: str) -> str:
    """Hash a raw API key. Uses HMAC-SHA256 when secret is configured, plain SHA-256 otherwise."""
    secret = settings.api_key_hmac_secret
    if secret:
        return hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()
    return hashlib.sha256(raw.encode()).hexdigest()


def _generate_api_key() -> tuple[str, str, str]:
    """Return (raw_key, hash, prefix 'ipx_...')."""
    raw = f"ipx_{secrets.token_urlsafe(32)}"
    key_hash = hash_api_key(raw)
    prefix = raw[:12] + "..."
    return raw, key_hash, prefix


def _validate_email_domain(email: str) -> None:
    """Raise 403 if email domain is not in the allow-list."""
    domain = settings.allowed_email_domain
    if domain and not email.lower().endswith(f"@{domain.lower()}"):
        from fastapi import HTTPException, status
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Registration is restricted to @{domain} email addresses",
        )


async def register_tenant(
    email: str,
    password: str,
    session: AsyncSession,
    name: str | None = None,
) -> tuple[Tenant, str]:
    """Create tenant + first API key. Returns (tenant, raw_api_key)."""
    _validate_email_domain(email)

    existing = await session.execute(select(Tenant.id).where(Tenant.email == email))
    if existing.scalar_one_or_none():
        from fastapi import HTTPException, status
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    slug = await _ensure_unique_slug(_slug_from_email(email), session)
    tenant = Tenant(
        email=email,
        password_hash=hash_password(password),
        slug=slug,
        name=name,
    )
    session.add(tenant)
    await session.flush()

    raw_key, key_hash, prefix = _generate_api_key()
    api_key = ApiKey(
        tenant_id=tenant.id,
        key_hash=key_hash,
        key_prefix=prefix,
        name="Default",
    )
    session.add(api_key)
    await session.commit()
    await session.refresh(tenant)

    try:
        from app.email.service import send_welcome_email
        send_welcome_email(email, slug)
    except Exception:
        pass  # non-critical

    return tenant, raw_key


async def authenticate_tenant(
    email: str,
    password: str,
    session: AsyncSession,
) -> Tenant:
    """Verify email+password. Raises HTTPException on failure."""
    result = await session.execute(
        select(Tenant).where(Tenant.email == email, Tenant.is_active.is_(True))
    )
    tenant = result.scalar_one_or_none()
    if not tenant or not tenant.password_hash:
        from fastapi import HTTPException, status
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    if not verify_password(password, tenant.password_hash):
        from fastapi import HTTPException, status
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    return tenant


async def create_token_pair(
    tenant_id: uuid.UUID,
    session: AsyncSession,
) -> tuple[str, str]:
    """Create (access_token, refresh_token) and persist refresh hash."""
    access = create_access_token(tenant_id)
    raw_refresh, refresh_hash = create_refresh_token()
    rt = RefreshToken(
        tenant_id=tenant_id,
        token_hash=refresh_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_days),
    )
    session.add(rt)
    await session.commit()
    return access, raw_refresh


async def rotate_refresh_token(
    raw_refresh: str,
    session: AsyncSession,
) -> tuple[str, str, uuid.UUID]:
    """Consume old refresh token, issue new pair. Returns (access, new_refresh, tenant_id)."""
    from fastapi import HTTPException, status as http_status

    old_hash = hash_refresh_token(raw_refresh)
    result = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == old_hash)
    )
    rt = result.scalar_one_or_none()
    if not rt or rt.expires_at < datetime.now(timezone.utc):
        raise HTTPException(http_status.HTTP_401_UNAUTHORIZED, "Invalid or expired refresh token")

    tenant_id = rt.tenant_id
    await session.delete(rt)
    access, new_refresh = await create_token_pair(tenant_id, session)
    return access, new_refresh, tenant_id


async def revoke_all_refresh_tokens(
    tenant_id: uuid.UUID,
    session: AsyncSession,
) -> None:
    from sqlalchemy import delete
    await session.execute(
        delete(RefreshToken).where(RefreshToken.tenant_id == tenant_id)
    )
    await session.commit()


# ---------------------------------------------------------------------------
# OAuth helpers
# ---------------------------------------------------------------------------

async def find_or_create_oauth_tenant(
    provider: str,
    oauth_id: str,
    email: str,
    session: AsyncSession,
    name: str | None = None,
) -> tuple[Tenant, bool]:
    """Find existing tenant by OAuth link, or link to existing email, or create new.
    Returns (tenant, is_new_account).
    """
    result = await session.execute(
        select(TenantOAuthLink).where(
            TenantOAuthLink.provider == provider,
            TenantOAuthLink.oauth_id == oauth_id,
        )
    )
    link = result.scalar_one_or_none()
    if link:
        result = await session.execute(select(Tenant).where(Tenant.id == link.tenant_id))
        tenant = result.scalar_one()
        if not tenant.name and name:
            tenant.name = name
        return tenant, False

    result = await session.execute(select(Tenant).where(Tenant.email == email))
    tenant = result.scalar_one_or_none()
    is_new = False

    if not tenant:
        slug = await _ensure_unique_slug(_slug_from_email(email), session)
        tenant = Tenant(email=email, slug=slug, email_verified=True, name=name)
        session.add(tenant)
        await session.flush()

        raw_key, key_hash, prefix = _generate_api_key()
        api_key = ApiKey(tenant_id=tenant.id, key_hash=key_hash, key_prefix=prefix, name="Default")
        session.add(api_key)
        is_new = True
    elif not tenant.name and name:
        tenant.name = name

    oauth_link = TenantOAuthLink(
        tenant_id=tenant.id,
        provider=provider,
        oauth_id=oauth_id,
        email=email,
    )
    session.add(oauth_link)
    await session.commit()
    await session.refresh(tenant)
    return tenant, is_new


# ---------------------------------------------------------------------------
# API Key management
# ---------------------------------------------------------------------------

async def create_api_key(
    tenant_id: uuid.UUID,
    name: str,
    scopes: str,
    session: AsyncSession,
) -> tuple[ApiKey, str]:
    """Create a new API key for tenant. Returns (ApiKey, raw_key_shown_once)."""
    raw_key, key_hash, prefix = _generate_api_key()
    api_key = ApiKey(
        tenant_id=tenant_id,
        key_hash=key_hash,
        key_prefix=prefix,
        name=name,
        scopes=scopes,
    )
    session.add(api_key)
    await session.commit()
    await session.refresh(api_key)
    return api_key, raw_key


async def list_api_keys(
    tenant_id: uuid.UUID,
    session: AsyncSession,
    include_revoked: bool = False,
) -> list[ApiKey]:
    query = select(ApiKey).where(ApiKey.tenant_id == tenant_id)
    if not include_revoked:
        query = query.where(ApiKey.is_active.is_(True))
    query = query.order_by(ApiKey.created_at)
    result = await session.execute(query)
    return list(result.scalars().all())


async def revoke_api_key(
    tenant_id: uuid.UUID,
    key_id: uuid.UUID,
    session: AsyncSession,
    reason: str | None = None,
) -> bool:
    result = await session.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.tenant_id == tenant_id)
    )
    api_key = result.scalar_one_or_none()
    if not api_key or not api_key.is_active:
        return False
    api_key.is_active = False
    api_key.revoked_at = datetime.now(timezone.utc)
    api_key.revoke_reason = reason
    await session.commit()
    return True
