"""ASGI middleware for MCP endpoint: authenticate via Bearer API key (ipx_...)."""

import json
import logging
from contextvars import ContextVar

from sqlalchemy import select

from app.database import async_session
from app.logging_config import tenant_id_ctx, tenant_name_ctx
from app.models import ApiKey, Tenant

logger = logging.getLogger(__name__)

current_tenant_id: ContextVar[str | None] = ContextVar("current_tenant_id", default=None)
current_api_key_id: ContextVar[str | None] = ContextVar("current_api_key_id", default=None)
current_client_ip: ContextVar[str | None] = ContextVar("current_client_ip", default=None)
current_user_agent: ContextVar[str | None] = ContextVar("current_user_agent", default=None)


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
        from app.auth.service import hash_api_key
        key_hash = hash_api_key(raw_key)

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

                if not tenant.email_verified:
                    await self._send_401(
                        send,
                        "Email not verified. Please verify your email at https://lexiro.io/verify-email before using the API.",
                    )
                    return

                from datetime import datetime, timezone
                api_key.last_used_at = datetime.now(timezone.utc)
                await session.commit()

        except Exception:
            logger.exception("MCP auth middleware DB error")
            await self._send_401(send, "Authentication service unavailable")
            return

        client_ip = None
        if scope.get("client"):
            client_ip = scope["client"][0]
        x_forwarded = headers.get(b"x-forwarded-for", b"").decode()
        if x_forwarded:
            client_ip = x_forwarded.split(",")[0].strip()
        ua = headers.get(b"user-agent", b"").decode() or None

        token_tid = current_tenant_id.set(str(tenant.id))
        token_akid = current_api_key_id.set(str(api_key.id))
        token_cip = current_client_ip.set(client_ip)
        token_ua = current_user_agent.set(ua)
        log_tid = tenant_id_ctx.set(str(tenant.id))
        log_tname = tenant_name_ctx.set(tenant.name or tenant.email or "-")
        try:
            await self.app(scope, receive, send)
        finally:
            tenant_name_ctx.reset(log_tname)
            tenant_id_ctx.reset(log_tid)
            current_user_agent.reset(token_ua)
            current_client_ip.reset(token_cip)
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
