"""IPCodex MVP — FastAPI application with MCP server (streamable HTTP transport)."""

import contextlib
import logging

from fastapi import FastAPI
from sqlalchemy import text
from starlette.routing import Mount

from mcp.server.fastmcp import FastMCP

from app.config import settings
from app.mcp.server import (
    tool_get_api_endpoint,
    tool_ingest_document,
    tool_list_devices,
    tool_search_documentation,
)

logging.basicConfig(
    level=getattr(logging, settings.app_log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
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


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("IPCodex MCP server starting (env=%s)", settings.app_env)
    async with mcp.session_manager.run():
        yield
    logger.info("IPCodex MCP server stopped")


app = FastAPI(
    title="IPCodex",
    version="0.1.0",
    lifespan=lifespan,
)

app.router.routes.append(Mount("/mcp", app=mcp.streamable_http_app()))


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    from app.database import engine

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {e}"

    return {"db": db_status}
