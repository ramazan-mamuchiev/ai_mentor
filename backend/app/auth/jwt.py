"""JWT access / refresh token creation and verification."""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt

from app.config import settings


def create_access_token(tenant_id: uuid.UUID) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(tenant_id),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """Decode and validate access token. Raises jwt.PyJWTError on failure."""
    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Not an access token")
    return payload


def create_refresh_token() -> tuple[str, str]:
    """Return (raw_token, sha256_hash) for storage."""
    raw = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    return raw, token_hash


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Email verification tokens
# ---------------------------------------------------------------------------

def create_email_verify_token(tenant_id: uuid.UUID) -> str:
    """Create a JWT for email verification (24h expiry)."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(tenant_id),
        "purpose": "email_verify",
        "iat": now,
        "exp": now + timedelta(hours=24),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_email_verify_token(token: str) -> uuid.UUID:
    """Decode email verification JWT. Returns tenant_id. Raises on failure."""
    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
    if payload.get("purpose") != "email_verify":
        raise jwt.InvalidTokenError("Not an email verification token")
    return uuid.UUID(payload["sub"])
