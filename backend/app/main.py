"""IPCodex MVP — FastAPI application with MCP server (streamable HTTP transport)."""

import asyncio
import contextlib
import logging
import time

from fastapi import FastAPI
from sqlalchemy import text
from starlette.routing import Mount

from mcp.server.fastmcp import FastMCP

from app.config import settings
from app.chat.router import router as chat_router
from app.documents.router import router as documents_router
from app.logging_config import setup_logging, active_requests_count
from app.middleware.request_logging import RequestLoggingMiddleware
from app.mcp.server import (
    tool_get_api_endpoint,
    tool_ingest_document,
    tool_ingest_url,
    tool_list_devices,
    tool_search_documentation,
)

setup_logging()
logger = logging.getLogger(__name__)

mcp = FastMCP(
    "IPCodex",
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
)

mcp.tool(name="search_documentation")(tool_search_documentation)
mcp.tool(name="get_api_endpoint")(tool_get_api_endpoint)
mcp.tool(name="list_devices")(tool_list_devices)
mcp.tool(name="ingest_document")(tool_ingest_document)
mcp.tool(name="ingest_url")(tool_ingest_url)

_start_time: float = 0.0


async def _system_monitor():
    """Background task: log system stats every 60 seconds."""
    from app.database import engine

    sys_logger = logging.getLogger("system")
    while True:
        await asyncio.sleep(60)
        try:
            pool = engine.pool
            pool_status = pool.status()
            pool_size = pool.size()
            pool_checked_out = pool.checkedout()
            pool_overflow = pool.overflow()
            pool_pct = (pool_checked_out / max(pool_size, 1)) * 100

            uptime = round(time.time() - _start_time, 1)

            stats = {
                "db_pool_size": pool_size,
                "db_pool_checked_out": pool_checked_out,
                "db_pool_overflow": pool_overflow,
                "db_pool_status": pool_status,
                "active_requests": active_requests_count,
                "uptime_sec": uptime,
            }

            if pool_pct > 80:
                sys_logger.warning(
                    "System stats (pool > 80%%)", extra=stats
                )
            else:
                sys_logger.info("System stats", extra=stats)
        except Exception:
            sys_logger.exception("Failed to collect system stats")


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    global _start_time
    _start_time = time.time()
    logger.info(
        "IPCodex MCP server starting",
        extra={"env": settings.app_env, "version": "0.1.0"},
    )
    from app.s3 import ensure_bucket
    try:
        ensure_bucket()
    except Exception:
        logger.warning("S3 bucket init failed (will retry on first upload)", exc_info=True)
    monitor_task = asyncio.create_task(_system_monitor())
    async with mcp.session_manager.run():
        yield
    monitor_task.cancel()
    try:
        await monitor_task
    except asyncio.CancelledError:
        pass
    logger.info("IPCodex MCP server stopped")


app = FastAPI(
    title="IPCodex",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(RequestLoggingMiddleware)
app.include_router(documents_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.router.routes.append(Mount("/mcp", app=mcp.streamable_http_app()))


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    from app.database import engine
    from app.s3 import check_health as s3_health

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as e:
        logger.error("Readiness check failed (DB)", extra={"error_type": type(e).__name__, "error": str(e)})
        db_status = f"error: {e}"

    try:
        import redis as redis_lib
        r = redis_lib.from_url(settings.redis_url, socket_connect_timeout=2)
        r.ping()
        redis_status = "ok"
    except Exception as e:
        redis_status = f"error: {e}"

    s3_status = "ok" if s3_health() else "error"

    try:
        from app.llm.client import check_health as llm_health
        ollama_status = "ok" if await llm_health() else "model_not_ready"
    except Exception as e:
        ollama_status = f"error: {e}"

    return {"db": db_status, "redis": redis_status, "s3": s3_status, "ollama": ollama_status}
