"""Smoke test fixtures: real PostgreSQL+pgvector WITHOUT mock embedder."""

import pathlib

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from testcontainers.postgres import PostgresContainer

SCHEMA_PATH = pathlib.Path(__file__).resolve().parents[2] / "db" / "schema.sql"


@pytest.fixture(scope="session")
def pg_container_smoke():
    """Start a PostgreSQL+pgvector container for smoke tests."""
    container = PostgresContainer(
        image="pgvector/pgvector:pg16",
        username="test",
        password="test",
        dbname="lexiro_smoke",
    )
    with container:
        yield container


@pytest.fixture(scope="session")
def pg_url_smoke(pg_container_smoke):
    host = pg_container_smoke.get_container_host_ip()
    port = pg_container_smoke.get_exposed_port(5432)
    return f"postgresql+asyncpg://test:test@{host}:{port}/lexiro_smoke"


@pytest.fixture(scope="session")
async def _init_schema_smoke(pg_url_smoke):
    engine = create_async_engine(pg_url_smoke, echo=False)
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")

    async with engine.begin() as conn:
        for statement in schema_sql.split(";"):
            stmt = statement.strip()
            if stmt:
                await conn.execute(text(stmt))

    await engine.dispose()


@pytest.fixture
async def db_session_smoke(pg_url_smoke, _init_schema_smoke):
    engine = create_async_engine(pg_url_smoke, echo=False)
    async with engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        yield session
        await session.close()
        await trans.rollback()
    await engine.dispose()
