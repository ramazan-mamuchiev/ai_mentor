"""Request logging middleware: request ID, access log, timing, client info."""

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.logging_config import active_requests_count, request_id_ctx

access_logger = logging.getLogger("access")

_SKIP_PATHS = {"/health"}
_SLOW_THRESHOLD_SEC = 5.0


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        import app.logging_config as lc

        req_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        token = request_id_ctx.set(req_id)

        lc.active_requests_count += 1
        t0 = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            lc.active_requests_count -= 1
            request_id_ctx.reset(token)
            raise

        duration_ms = round((time.perf_counter() - t0) * 1000, 1)
        lc.active_requests_count -= 1

        response.headers["X-Request-ID"] = req_id

        if request.url.path not in _SKIP_PATHS:
            client_ip = request.client.host if request.client else "-"
            x_forwarded = request.headers.get("X-Forwarded-For", "-")
            user_agent = request.headers.get("User-Agent", "-")
            request_size = int(request.headers.get("Content-Length", 0))
            response_size = int(response.headers.get("Content-Length", 0))
            query_string = str(request.url.query) if request.url.query else ""

            log_data = {
                "method": request.method,
                "path": request.url.path,
                "query_string": query_string,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "client_ip": client_ip,
                "x_forwarded_for": x_forwarded,
                "user_agent": user_agent,
                "request_size": request_size,
                "response_size": response_size,
                "active_requests": lc.active_requests_count,
            }

            msg = (
                f"{request.method} {request.url.path} "
                f"{response.status_code} {duration_ms}ms"
            )

            status = response.status_code
            if status >= 500:
                access_logger.error(msg, extra=log_data)
            elif status >= 400 or duration_ms > _SLOW_THRESHOLD_SEC * 1000:
                access_logger.warning(msg, extra=log_data)
            else:
                access_logger.info(msg, extra=log_data)

        request_id_ctx.reset(token)
        return response
