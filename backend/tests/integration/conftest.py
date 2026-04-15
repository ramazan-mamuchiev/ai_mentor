"""Integration test fixtures: Testcontainers PostgreSQL + pgvector, mock embedder."""

import os
import pathlib
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from tests.conftest import fake_embed_query, fake_embed_texts

SCHEMA_PATH = pathlib.Path(__file__).resolve().parents[2] / "db" / "schema.sql"


@pytest.fixture(scope="session")
def pg_container():
    """Start a PostgreSQL+pgvector container for the entire test session."""
    container = PostgresContainer(
        image="pgvector/pgvector:pg16",
        username="test",
        password="test",
        dbname="lexiro_test",
    )
    with container:
        yield container


@pytest.fixture(scope="session")
def pg_url(pg_container):
    """Async connection URL for the test database."""
    host = pg_container.get_container_host_ip()
    port = pg_container.get_exposed_port(5432)
    return f"postgresql+asyncpg://test:test@{host}:{port}/lexiro_test"


@pytest.fixture(scope="session")
async def _init_schema(pg_url):
    """Create schema once per session (tables + pgvector extension)."""
    engine = create_async_engine(pg_url, echo=False)
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")

    async with engine.begin() as conn:
        for statement in schema_sql.split(";"):
            stmt = statement.strip()
            if stmt:
                await conn.execute(text(stmt))

    await engine.dispose()


@pytest.fixture
async def db_engine(pg_url, _init_schema):
    """Per-test async engine."""
    engine = create_async_engine(pg_url, echo=False)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine):
    """Per-test async session with rollback for isolation."""
    async with db_engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)

        yield session

        await session.close()
        await trans.rollback()


@pytest.fixture(autouse=True)
def _mock_embedder():
    """Auto-mock embedding functions for all integration tests."""
    import app.ingestion.embedder  # noqa: F401
    import app.ingestion.pipeline  # noqa: F401
    import app.search.service  # noqa: F401

    with (
        patch("app.ingestion.embedder.embed_texts", side_effect=fake_embed_texts),
        patch("app.ingestion.embedder.embed_query", side_effect=fake_embed_query),
        patch("app.ingestion.pipeline.embed_texts", side_effect=fake_embed_texts),
        patch("app.search.service.embed_query", side_effect=fake_embed_query),
    ):
        yield


@pytest.fixture
def sample_md_file(tmp_path):
    """Create a small test markdown file."""
    content = """# ZKTeco Protocol Guide

## Door Control

### Open Door Command
To open a door remotely, send the CONTROL DEVICE command:
`C1:CONTROL DEVICE 01010105`
Where 01 = control output, 01 = door 1, 01 = lock, 05 = 5 seconds.

### Close Door Command
To close and lock a door:
`C2:CONTROL DEVICE 06010100`
Where 06 = lock/unlock, 01 = door 1, 01 = lock.

## Event Monitoring

### Event Types
| Code | Description |
|------|-------------|
| 0    | Normal punch open |
| 1    | Punch during normal open |
| 2    | First card normal open |
| 200  | Door opened correctly |
| 201  | Door closed correctly |

### Real-time Events
The device pushes events via HTTP POST to the server callback URL.
Events include card number, timestamp, and verification mode.

## Device Configuration

### Network Settings
Configure IP address, gateway, and DNS via the SET OPTIONS command.
Example: `SET OPTIONS IPAddress=192.168.1.100,GATEIPAddress=192.168.1.1`

### Time Synchronization
The server sends time sync commands periodically.
Format: `SET OPTIONS DateTime=YYYY-MM-DD HH:MM:SS`
"""
    path = tmp_path / "test_protocol.md"
    path.write_text(content, encoding="utf-8")
    return str(path)


@pytest.fixture
def sample_swagger_file(tmp_path):
    """Create a small test OpenAPI spec."""
    content = """openapi: "3.0.0"
info:
  title: Access Control API
  version: "1.0"
paths:
  /doors:
    get:
      summary: List all doors
      tags:
        - doors
      responses:
        "200":
          description: List of doors
  /doors/{id}/open:
    post:
      summary: Open a specific door
      tags:
        - doors
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: integer
      responses:
        "200":
          description: Door opened successfully
  /events:
    get:
      summary: Get recent events
      tags:
        - events
      responses:
        "200":
          description: List of events
"""
    path = tmp_path / "api_spec.yaml"
    path.write_text(content, encoding="utf-8")
    return str(path)
