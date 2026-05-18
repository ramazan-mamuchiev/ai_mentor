"""Symmetric encryption helpers for storing sensitive credentials in the DB."""

from __future__ import annotations

import json
import logging

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


def _get_fernet() -> Fernet | None:
    from app.config import settings

    key = settings.confluence_credentials_key
    if not key:
        return None
    try:
        return Fernet(key.encode())
    except Exception:
        logger.warning("Invalid CONFLUENCE_CREDENTIALS_KEY — credentials will not be persisted")
        return None


def encrypt_credentials(username: str, password: str) -> str | None:
    """Encrypt a username/password pair into a Fernet token string.

    Returns None if the encryption key is not configured.
    """
    f = _get_fernet()
    if f is None:
        return None
    payload = json.dumps({"u": username, "p": password})
    return f.encrypt(payload.encode()).decode()


def decrypt_credentials(token: str) -> tuple[str, str] | None:
    """Decrypt a Fernet token back into (username, password).

    Returns None if decryption fails or the key is not configured.
    """
    f = _get_fernet()
    if f is None:
        return None
    try:
        payload = json.loads(f.decrypt(token.encode()).decode())
        return payload["u"], payload["p"]
    except (InvalidToken, KeyError, json.JSONDecodeError):
        logger.warning("Failed to decrypt Confluence credentials")
        return None
