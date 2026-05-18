"""Lexiro — FastAPI application with MCP server (streamable HTTP transport)."""

import asyncio
import contextlib
import logging
import time

from fastapi import FastAPI
from sqlalchemy import text
from starlette.routing import Mount

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from app.config import settings
from app.auth.router import router as auth_router
from app.chat.router import router as chat_router
from app.documents.router import router as documents_router
from app.products.router import router as products_router
from app.reindex.router import router as reindex_router
from app.share.router import router as share_router
from app.share.public import public_router as share_public_router
from app.uploads.router import router as uploads_router
from app.logging_config import setup_logging, active_requests_count
from app.middleware.request_logging import RequestLoggingMiddleware
from app.mcp.server import (
    tool_get_api_endpoint,
    tool_get_code_examples,
    tool_get_document_outline,
    tool_get_api_lifecycle,
    tool_get_product_info,
    tool_get_section,
    tool_grep_docs,
    tool_list_documents,
    tool_list_products,
    tool_search_documentation,
)

setup_logging()
logger = logging.getLogger(__name__)

mcp = FastMCP(
    "Lexiro",
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
    transport_security=TransportSecuritySettings(
        allowed_hosts=["lexiro.io", "localhost", "127.0.0.1"],
    ),
)

mcp.tool(name="search_documentation")(tool_search_documentation)
mcp.tool(name="get_api_endpoint")(tool_get_api_endpoint)
mcp.tool(name="list_products")(tool_list_products)
mcp.tool(name="get_product_info")(tool_get_product_info)
mcp.tool(name="list_documents")(tool_list_documents)
mcp.tool(name="get_document_outline")(tool_get_document_outline)
mcp.tool(name="get_section")(tool_get_section)
mcp.tool(name="get_code_examples")(tool_get_code_examples)
mcp.tool(name="grep_docs")(tool_grep_docs)
mcp.tool(name="get_api_lifecycle")(tool_get_api_lifecycle)

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


async def _apply_schema():
    """Apply schema.sql to ensure all tables exist (idempotent via IF NOT EXISTS)."""
    from app.database import engine
    import pathlib

    schema_path = pathlib.Path(__file__).resolve().parent.parent / "db" / "schema.sql"
    if not schema_path.exists():
        logger.warning("schema.sql not found, skipping startup migration", extra={"path": str(schema_path)})
        return

    sql = schema_path.read_text(encoding="utf-8")
    async with engine.begin() as conn:
        raw = await conn.get_raw_connection()
        await raw.driver_connection.execute(sql)
    logger.info("Startup schema migration applied successfully")

    await _migrate_devices_to_products()
    await _migrate_embedding_dims()
    await _migrate_doc_context()
    await _migrate_source_hash_index()
    await _migrate_upload_sessions()
    await _migrate_chunks_parent_content()
    await _migrate_ingested_at_to_uploaded_at()
    await _migrate_ingestion_attempts()
    await _apply_auth_schema()


async def _apply_auth_schema():
    """Apply pending SQL migrations, skip already applied ones."""
    from app.database import engine
    import pathlib

    migrations_dir = pathlib.Path(__file__).resolve().parent.parent / "db" / "migrations"
    async with engine.begin() as conn:
        raw = await conn.get_raw_connection()
        drv = raw.driver_connection

        applied = {
            row["filename"]
            for row in await drv.fetch("SELECT filename FROM schema_migrations")
        }

        for sql_file in sorted(migrations_dir.glob("*.sql")):
            if sql_file.name in applied:
                logger.debug("Migration already applied, skipping", extra={"file": sql_file.name})
                continue

            sql = sql_file.read_text(encoding="utf-8")
            await drv.execute(sql)
            await drv.execute(
                "INSERT INTO schema_migrations (filename) VALUES ($1)",
                sql_file.name,
            )
            logger.info("Migration applied", extra={"file": sql_file.name})


async def _migrate_devices_to_products():
    """Migrate legacy 'devices' table to 'products', handling all possible states."""
    from app.database import engine

    async with engine.begin() as conn:
        raw = await conn.get_raw_connection()
        drv = raw.driver_connection

        has_devices = await drv.fetchrow(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_name = 'devices'"
        )
        has_products = await drv.fetchrow(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_name = 'products'"
        )

        if has_devices and has_products:
            devices_count = await drv.fetchval("SELECT count(*) FROM devices")
            products_count = await drv.fetchval("SELECT count(*) FROM products")
            logger.info(
                "Both tables exist: devices=%d, products=%d",
                devices_count, products_count,
            )
            if devices_count > 0 and products_count == 0:
                logger.info("Transferring data from devices -> products")
                await drv.execute(
                    "INSERT INTO products (id, name, manufacturer, model, category, created_at) "
                    "SELECT id, name, manufacturer, model, category, created_at FROM devices"
                )
                seq_val = await drv.fetchval(
                    "SELECT max(id) FROM products"
                )
                if seq_val:
                    await drv.execute(
                        f"SELECT setval(pg_get_serial_sequence('products','id'), {seq_val})"
                    )
            await _migrate_fk_columns(drv, "products")
            if devices_count > 0 and products_count == 0:
                await drv.execute("DROP TABLE devices CASCADE")
                logger.info("Dropped legacy 'devices' table after data transfer")
            elif devices_count == 0:
                await drv.execute("DROP TABLE devices CASCADE")
                logger.info("Dropped empty legacy 'devices' table")
            else:
                logger.warning(
                    "Both devices and products contain data — manual review needed"
                )

        elif has_devices and not has_products:
            logger.info("Renaming devices -> products")
            await drv.execute("ALTER TABLE devices RENAME TO products")
            await _migrate_fk_columns(drv, "products")

        elif has_products and not has_devices:
            await _migrate_fk_columns(drv, "products")

        else:
            logger.info("Neither devices nor products table found")
            return

        logger.info("Migration devices -> products completed")


async def _migrate_fk_columns(drv, target_table: str):
    """Rename legacy device_id / device_filter columns and re-point FK constraints."""
    has_device_id_doc = await drv.fetchrow(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'documents' AND column_name = 'device_id'"
    )
    if has_device_id_doc:
        await drv.execute(
            "ALTER TABLE documents "
            "DROP CONSTRAINT IF EXISTS documents_device_id_fkey"
        )
        await drv.execute(
            "ALTER TABLE documents RENAME COLUMN device_id TO product_id"
        )
        await drv.execute(
            "ALTER TABLE documents "
            f"ADD CONSTRAINT documents_product_id_fkey "
            f"FOREIGN KEY (product_id) REFERENCES {target_table}(id) ON DELETE CASCADE"
        )
        logger.info("Renamed documents.device_id -> product_id")

    has_device_filter = await drv.fetchrow(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'chat_sessions' AND column_name = 'device_filter'"
    )
    if has_device_filter:
        await drv.execute(
            "ALTER TABLE chat_sessions RENAME COLUMN device_filter TO product_filter"
        )
        logger.info("Renamed chat_sessions.device_filter -> product_filter")


async def _migrate_doc_context():
    """Add doc_context column to chat_sessions if it doesn't exist."""
    from app.database import engine

    async with engine.begin() as conn:
        raw = await conn.get_raw_connection()
        row = await raw.driver_connection.fetchrow(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'chat_sessions' AND column_name = 'doc_context'"
        )
        if row:
            return
        await raw.driver_connection.execute(
            "ALTER TABLE chat_sessions ADD COLUMN doc_context TEXT"
        )
        logger.info("Added doc_context column to chat_sessions")


async def _migrate_source_hash_index():
    """Create idx_documents_source_hash if it doesn't exist."""
    from app.database import engine

    async with engine.begin() as conn:
        raw = await conn.get_raw_connection()
        await raw.driver_connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_documents_source_hash "
            "ON documents(source_hash) WHERE source_hash != ''"
        )
    logger.info("Ensured idx_documents_source_hash index exists")


async def _migrate_embedding_dims():
    """Resize the embedding column if it doesn't match the configured dimensions."""
    from app.database import engine

    target_dims = settings.embedding_dims
    async with engine.begin() as conn:
        raw = await conn.get_raw_connection()
        row = await raw.driver_connection.fetchrow(
            "SELECT atttypmod FROM pg_attribute "
            "WHERE attrelid = 'chunks'::regclass AND attname = 'embedding'"
        )
        if row is None:
            return

        current_dims = row["atttypmod"]
        if current_dims == target_dims:
            logger.info("Embedding dims already match", extra={"dims": target_dims})
            return

        logger.warning(
            "Embedding dimension mismatch — migrating",
            extra={"current_dims": current_dims, "target_dims": target_dims},
        )
        await raw.driver_connection.execute("UPDATE chunks SET embedding = NULL")
        await raw.driver_connection.execute("DROP INDEX IF EXISTS idx_chunks_embedding")
        await raw.driver_connection.execute(
            f"ALTER TABLE chunks ALTER COLUMN embedding TYPE vector({target_dims})"
        )
        await raw.driver_connection.execute(
            f"CREATE INDEX idx_chunks_embedding ON chunks "
            f"USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 128)"
        )
        logger.info(
            "Embedding column migrated (old embeddings cleared — reindex required)",
            extra={"old_dims": current_dims, "new_dims": target_dims},
        )


async def _migrate_upload_sessions():
    """Create upload_sessions table if it doesn't exist (handled by schema.sql, this is a safety net)."""
    from app.database import engine

    async with engine.begin() as conn:
        raw = await conn.get_raw_connection()
        drv = raw.driver_connection
        has_table = await drv.fetchrow(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_name = 'upload_sessions'"
        )
        if has_table:
            logger.info("Table 'upload_sessions' already exists")
            return
        await drv.execute("""
            CREATE TABLE upload_sessions (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                file_size BIGINT NOT NULL,
                "offset" BIGINT NOT NULL DEFAULT 0,
                content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
                product_name TEXT NOT NULL,
                firmware_version TEXT NOT NULL DEFAULT '1.0',
                manufacturer TEXT NOT NULL DEFAULT '',
                is_archive BOOLEAN NOT NULL DEFAULT FALSE,
                force BOOLEAN NOT NULL DEFAULT FALSE,
                s3_upload_id TEXT NOT NULL DEFAULT '',
                s3_key TEXT NOT NULL DEFAULT '',
                parts_json TEXT NOT NULL DEFAULT '[]',
                sha256_state TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'uploading',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                expires_at TIMESTAMPTZ NOT NULL
            )
        """)
        await drv.execute(
            "CREATE INDEX IF NOT EXISTS idx_upload_sessions_status ON upload_sessions(status)"
        )
        await drv.execute(
            "CREATE INDEX IF NOT EXISTS idx_upload_sessions_expires ON upload_sessions(expires_at)"
        )
        logger.info("Created upload_sessions table")


async def _migrate_chunks_parent_content():
    """Add parent_content column to chunks if it doesn't exist."""
    from app.database import engine

    async with engine.begin() as conn:
        raw = await conn.get_raw_connection()
        drv = raw.driver_connection
        row = await drv.fetchrow(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'chunks' AND column_name = 'parent_content'"
        )
        if row:
            return
        await drv.execute("ALTER TABLE chunks ADD COLUMN parent_content TEXT")
        logger.info("Added parent_content column to chunks")


async def _migrate_ingested_at_to_uploaded_at():
    """Rename ingested_at -> uploaded_at and add indexed_at column."""
    from app.database import engine

    async with engine.begin() as conn:
        raw = await conn.get_raw_connection()
        drv = raw.driver_connection

        has_ingested_at = await drv.fetchrow(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'documents' AND column_name = 'ingested_at'"
        )
        if has_ingested_at:
            await drv.execute("ALTER TABLE documents RENAME COLUMN ingested_at TO uploaded_at")
            logger.info("Renamed documents.ingested_at -> uploaded_at")

        has_indexed_at = await drv.fetchrow(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'documents' AND column_name = 'indexed_at'"
        )
        if not has_indexed_at:
            await drv.execute("ALTER TABLE documents ADD COLUMN indexed_at TIMESTAMPTZ")
            await drv.execute(
                "UPDATE documents SET indexed_at = uploaded_at WHERE status = 'ready' AND indexed_at IS NULL"
            )
            logger.info("Added indexed_at column and backfilled from uploaded_at for ready documents")


async def _migrate_ingestion_attempts():
    """Add ingestion_attempts and progress_updated_at columns to documents if missing."""
    from app.database import engine

    async with engine.begin() as conn:
        raw = await conn.get_raw_connection()
        drv = raw.driver_connection

        row = await drv.fetchrow(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'documents' AND column_name = 'ingestion_attempts'"
        )
        if not row:
            await drv.execute(
                "ALTER TABLE documents ADD COLUMN ingestion_attempts INT NOT NULL DEFAULT 0"
            )
            logger.info("Added ingestion_attempts column to documents")

        row2 = await drv.fetchrow(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'documents' AND column_name = 'progress_updated_at'"
        )
        if not row2:
            await drv.execute(
                "ALTER TABLE documents ADD COLUMN progress_updated_at TIMESTAMPTZ"
            )
            logger.info("Added progress_updated_at column to documents")


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    global _start_time
    _start_time = time.time()
    logger.info(
        "Lexiro MCP server starting",
        extra={"env": settings.app_env, "version": "0.1.0"},
    )

    try:
        await _apply_schema()
    except Exception:
        logger.warning("Startup schema migration failed", exc_info=True)

    try:
        await _migrate_embedding_dims()
    except Exception:
        logger.warning("Embedding dims migration failed (standalone)", exc_info=True)

    from app.s3 import ensure_bucket
    try:
        ensure_bucket()
    except Exception:
        logger.warning("S3 bucket init failed (will retry on first upload)", exc_info=True)

    try:
        from app.admin.seed_prompts import seed_prompts
        from app.database import async_session
        async with async_session() as session:
            await seed_prompts(session)
    except Exception:
        logger.warning("Prompt templates seed failed", exc_info=True)

    monitor_task = asyncio.create_task(_system_monitor())
    async with mcp.session_manager.run():
        yield
    monitor_task.cancel()
    try:
        await monitor_task
    except asyncio.CancelledError:
        pass

    from app.llm.http_client import close_clients
    await close_clients()

    logger.info("Lexiro MCP server stopped")


app = FastAPI(
    title="Lexiro",
    version="0.1.0",
    lifespan=lifespan,
)

from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.exceptions import (
    http_exception_handler,
    validation_exception_handler,
    llm_error_handler,
    quota_error_handler,
    unhandled_exception_handler,
)
from app.llm.client import LLMError
from app.uploads.quota import QuotaError

app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(LLMError, llm_error_handler)
app.add_exception_handler(QuotaError, quota_error_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

from fastapi import Depends
from app.auth.dependencies import get_current_tenant, require_admin, require_email_verified

_auth = [Depends(require_email_verified)]
_admin_auth = [Depends(require_admin)]

from starlette.middleware.gzip import GZipMiddleware

app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=6)
app.include_router(auth_router)
app.include_router(documents_router, prefix="/api/v1", dependencies=_auth)
app.include_router(products_router, prefix="/api/v1", dependencies=_auth)
app.include_router(chat_router, prefix="/api/v1", dependencies=_auth)
app.include_router(reindex_router, prefix="/api/v1", dependencies=_auth)
app.include_router(share_router, prefix="/api/v1", dependencies=_auth)
app.include_router(uploads_router, prefix="/api/v1", dependencies=_auth)
app.include_router(share_public_router, prefix="/api/v1")

from app.admin.router import router as admin_router
app.include_router(admin_router, prefix="/api/v1", dependencies=_admin_auth)

from app.mcp.auth_middleware import McpApiKeyAuthMiddleware
app.router.routes.append(Mount("/mcp", app=McpApiKeyAuthMiddleware(mcp.streamable_http_app())))


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
        llm_status = "ok" if await llm_health() else "model_not_ready"
    except Exception as e:
        llm_status = f"error: {e}"

    from app.config import settings as _cfg
    return {
        "db": db_status,
        "redis": redis_status,
        "s3": s3_status,
        "llm": llm_status,
        "llm_provider": _cfg.llm_provider,
    }
