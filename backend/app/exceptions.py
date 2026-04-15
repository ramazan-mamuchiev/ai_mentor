"""Global exception handlers — unified JSON error envelope with request_id."""

import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.logging_config import request_id_ctx
from app.llm.client import LLMError
from app.uploads.quota import QuotaError

logger = logging.getLogger(__name__)


def _request_id() -> str:
    return request_id_ctx.get("-")


def _error_response(
    status_code: int,
    error: str,
    details: list | dict | None = None,
) -> JSONResponse:
    body: dict = {
        "error": error,
        "request_id": _request_id(),
    }
    if details is not None:
        body["details"] = details
    return JSONResponse(status_code=status_code, content=body)


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    return _error_response(exc.status_code, exc.detail or "Error")


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    details = [
        {
            "field": " → ".join(str(loc) for loc in err["loc"]),
            "message": err["msg"],
            "type": err["type"],
        }
        for err in exc.errors()
    ]
    return _error_response(422, "Validation error", details)


async def llm_error_handler(request: Request, exc: LLMError) -> JSONResponse:
    logger.warning(
        "LLM error [request_id=%s]: %s (%s)",
        _request_id(),
        exc.detail,
        exc.error_code,
    )
    return _error_response(
        exc.status_code,
        exc.detail,
        {"error_code": exc.error_code},
    )


async def quota_error_handler(request: Request, exc: QuotaError) -> JSONResponse:
    return _error_response(
        413,
        str(exc),
        {
            "quota_type": exc.quota_type,
            "limit_bytes": exc.limit_bytes,
            "used_bytes": exc.used_bytes,
        },
    )


async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    logger.error(
        "Unhandled exception [request_id=%s] %s %s: %s",
        _request_id(),
        request.method,
        request.url.path,
        exc,
        exc_info=True,
    )
    detail = (
        str(exc) if settings.app_env == "development" else "Internal server error"
    )
    return _error_response(500, detail)
