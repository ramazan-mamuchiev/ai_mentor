"""ASGI middleware for MCP endpoint: authenticate via Bearer API key (ipx_...)."""

import hashlib
import json
import logging
from contextvars import ContextVar

from sqlalchemy import select

from app.database import async_session
from app.models import ApiKey, Tenant

logger = logging.getLogger(__name__)

current_tenant_id: ContextVar[str | None] = ContextVar("current_tenant_id", default=None)
current_api_key_id: ContextVar[str | None] = ContextVar("current_api_key_id", default=None)


class McpApiKeyAuthMiddleware:
    """ASGI middleware that wraps the MCP app.

    Expects: Authorization: Bearer ipx_...
    Sets current_tenant_id contextvar on success.
    Returns 401 JSON-RPC error on failure.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        auth_value = headers.get(b"authorization", b"").decode()

        if not auth_value.startswith("Bearer ipx_"):
            await self._send_401(send, "Missing or invalid API key. Expected: Authorization: Bearer ipx_...")
            return

        raw_key = auth_value[len("Bearer "):]
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

        try:
            async with async_session() as session:
                result = await session.execute(
                    select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active.is_(True))
                )
                api_key = result.scalar_one_or_none()
                if not api_key:
                    await self._send_401(send, "Invalid API key")
                    return

                result = await session.execute(
                    select(Tenant).where(Tenant.id == api_key.tenant_id, Tenant.is_active.is_(True))
                )
                tenant = result.scalar_one_or_none()
                if not tenant:
                    await self._send_401(send, "Tenant not found or disabled")
                    return

                from datetime import datetime, timezone
                api_key.last_used_at = datetime.now(timezone.utc)
                await session.commit()

        except Exception:
            logger.exception("MCP auth middleware DB error")
            await self._send_401(send, "Authentication service unavailable")
            return

        token_tid = current_tenant_id.set(str(tenant.id))
        token_akid = current_api_key_id.set(str(api_key.id))
        try:
            await self.app(scope, receive, send)
        finally:
            current_api_key_id.reset(token_akid)
            current_tenant_id.reset(token_tid)

    @staticmethod
    async def _send_401(send, detail: str):
        body = json.dumps({"error": {"code": -32001, "message": detail}}).encode()
        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": [
                [b"content-type", b"application/json"],
                [b"content-length", str(len(body)).encode()],
            ],
        })
        await send({"type": "http.response.body", "body": body})
