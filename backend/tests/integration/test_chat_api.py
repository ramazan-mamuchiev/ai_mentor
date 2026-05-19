"""Integration tests for Chat REST API endpoints with real PostgreSQL."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import ChatMessage, ChatMessageAnalytics, ChatSession, Chunk, Product, Document


async def _async_iter(items):
    for item in items:
        yield item


def _create_chat_app(db_engine):
    """Create a minimal FastAPI app with chat routes wired to a test DB."""
    import contextlib

    from fastapi import FastAPI

    from app.chat.router import router as chat_router

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        yield

    app = FastAPI(title="AI Mentor-Chat-Test", lifespan=lifespan)
    app.include_router(chat_router, prefix="/api/v1")

    return app


@pytest.fixture
async def chat_client(db_engine):
    """AsyncClient wired to a FastAPI app with chat routes and test DB.

    Uses a dedicated session maker that commits to real DB (not rolled-back).
    Cleans up all chat data after each test for isolation.
    """
    test_session_maker = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    app = _create_chat_app(db_engine)

    with patch("app.chat.router.async_session", test_session_maker):
        async with LifespanManager(app) as manager:
            transport = ASGITransport(app=manager.app)
            async with AsyncClient(transport=transport, base_url="http://localhost") as ac:
                yield ac

    async with test_session_maker() as cleanup_session:
        await cleanup_session.execute(delete(ChatMessageAnalytics))
        await cleanup_session.execute(delete(ChatMessage))
        await cleanup_session.execute(delete(ChatSession))
        await cleanup_session.execute(delete(Chunk))
        await cleanup_session.execute(delete(Document))
        await cleanup_session.execute(delete(Product))
        await cleanup_session.commit()


class TestChatSessionsAPI:
    """Test chat session CRUD via HTTP endpoints."""

    async def test_create_session(self, chat_client):
        resp = await chat_client.post(
            "/api/v1/chat/sessions",
            json={"title": "Test Session", "product_filter": "HikCentral"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Test Session"
        assert data["product_filter"] == "HikCentral"
        assert data["message_count"] == 0
        assert "id" in data
        assert "created_at" in data

    async def test_create_session_minimal(self, chat_client):
        resp = await chat_client.post("/api/v1/chat/sessions", json={})
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] is None
        assert data["product_filter"] is None

    async def test_list_sessions_empty(self, chat_client):
        resp = await chat_client.get("/api/v1/chat/sessions")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_sessions_returns_created(self, chat_client):
        await chat_client.post(
            "/api/v1/chat/sessions",
            json={"title": "Session A"},
        )
        await chat_client.post(
            "/api/v1/chat/sessions",
            json={"title": "Session B"},
        )

        resp = await chat_client.get("/api/v1/chat/sessions")
        assert resp.status_code == 200
        sessions = resp.json()
        assert len(sessions) == 2
        titles = {s["title"] for s in sessions}
        assert "Session A" in titles
        assert "Session B" in titles

    async def test_get_session_detail(self, chat_client):
        create_resp = await chat_client.post(
            "/api/v1/chat/sessions",
            json={"title": "Detail Test"},
        )
        session_id = create_resp.json()["id"]

        resp = await chat_client.get(f"/api/v1/chat/sessions/{session_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == session_id
        assert data["title"] == "Detail Test"
        assert data["messages"] == []

    async def test_get_nonexistent_session(self, chat_client):
        resp = await chat_client.get("/api/v1/chat/sessions/99999")
        assert resp.status_code == 404

    async def test_delete_session(self, chat_client):
        create_resp = await chat_client.post(
            "/api/v1/chat/sessions",
            json={"title": "To Delete"},
        )
        session_id = create_resp.json()["id"]

        del_resp = await chat_client.delete(f"/api/v1/chat/sessions/{session_id}")
        assert del_resp.status_code == 204

        get_resp = await chat_client.get(f"/api/v1/chat/sessions/{session_id}")
        assert get_resp.status_code == 404

    async def test_delete_nonexistent_session(self, chat_client):
        resp = await chat_client.delete("/api/v1/chat/sessions/99999")
        assert resp.status_code == 404


class TestChatMessagesAPI:
    """Test chat message sending via HTTP with mocked LLM."""

    async def test_send_message_returns_sse_stream(self, chat_client):
        create_resp = await chat_client.post(
            "/api/v1/chat/sessions",
            json={"title": "Stream Test"},
        )
        session_id = create_resp.json()["id"]

        with patch(
            "app.chat.router.stream_chat_completion",
            return_value=_async_iter(["Hello", " from", " LLM"]),
        ):
            resp = await chat_client.post(
                f"/api/v1/chat/sessions/{session_id}/messages",
                json={"content": "How to authenticate?"},
            )

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

        lines = resp.text.strip().split("\n")
        events = []
        for line in lines:
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

        event_types = [e["type"] for e in events]
        assert "sources" in event_types
        assert "token" in event_types
        assert "done" in event_types

        tokens = [e["content"] for e in events if e["type"] == "token"]
        assert "".join(tokens) == "Hello from LLM"

        done_event = next(e for e in events if e["type"] == "done")
        assert "message_id" in done_event
        assert "duration_ms" in done_event

    async def test_send_message_to_nonexistent_session(self, chat_client):
        resp = await chat_client.post(
            "/api/v1/chat/sessions/99999/messages",
            json={"content": "Hello?"},
        )
        assert resp.status_code == 404

    async def test_send_empty_message_rejected(self, chat_client):
        create_resp = await chat_client.post(
            "/api/v1/chat/sessions",
            json={"title": "Validation Test"},
        )
        session_id = create_resp.json()["id"]

        resp = await chat_client.post(
            f"/api/v1/chat/sessions/{session_id}/messages",
            json={"content": ""},
        )
        assert resp.status_code == 422

    async def test_messages_persisted_after_stream(self, chat_client):
        create_resp = await chat_client.post(
            "/api/v1/chat/sessions",
            json={"title": "Persistence Test"},
        )
        session_id = create_resp.json()["id"]

        with patch(
            "app.chat.router.stream_chat_completion",
            return_value=_async_iter(["Answer: ", "use HMAC"]),
        ):
            await chat_client.post(
                f"/api/v1/chat/sessions/{session_id}/messages",
                json={"content": "How to auth?"},
            )

        detail_resp = await chat_client.get(f"/api/v1/chat/sessions/{session_id}")
        assert detail_resp.status_code == 200
        messages = detail_resp.json()["messages"]

        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "How to auth?"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == "Answer: use HMAC"
        assert messages[1]["sources"] is not None
        assert messages[1]["duration_ms"] is not None

    async def test_session_title_auto_set_from_first_message(self, chat_client):
        create_resp = await chat_client.post(
            "/api/v1/chat/sessions",
            json={},
        )
        session_id = create_resp.json()["id"]
        assert create_resp.json()["title"] is None

        with patch(
            "app.chat.router.stream_chat_completion",
            return_value=_async_iter(["Response"]),
        ):
            await chat_client.post(
                f"/api/v1/chat/sessions/{session_id}/messages",
                json={"content": "What is HikCentral?"},
            )

        detail_resp = await chat_client.get(f"/api/v1/chat/sessions/{session_id}")
        assert detail_resp.json()["title"] == "What is HikCentral?"

    async def test_multiple_messages_in_session(self, chat_client):
        create_resp = await chat_client.post(
            "/api/v1/chat/sessions",
            json={"title": "Multi-turn"},
        )
        session_id = create_resp.json()["id"]

        for i in range(3):
            with patch(
                "app.chat.router.stream_chat_completion",
                return_value=_async_iter([f"Reply {i}"]),
            ):
                await chat_client.post(
                    f"/api/v1/chat/sessions/{session_id}/messages",
                    json={"content": f"Question {i}"},
                )

        detail_resp = await chat_client.get(f"/api/v1/chat/sessions/{session_id}")
        messages = detail_resp.json()["messages"]
        assert len(messages) == 6

        user_msgs = [m for m in messages if m["role"] == "user"]
        assistant_msgs = [m for m in messages if m["role"] == "assistant"]
        assert len(user_msgs) == 3
        assert len(assistant_msgs) == 3

    async def test_llm_error_returns_error_event(self, chat_client):
        create_resp = await chat_client.post(
            "/api/v1/chat/sessions",
            json={"title": "Error Test"},
        )
        session_id = create_resp.json()["id"]

        async def _failing_llm(*args, **kwargs):
            raise RuntimeError("Ollama returned 500")
            yield  # noqa: unreachable — makes this an async generator

        with patch(
            "app.chat.router.stream_chat_completion",
            side_effect=RuntimeError("Ollama returned 500"),
        ):
            resp = await chat_client.post(
                f"/api/v1/chat/sessions/{session_id}/messages",
                json={"content": "Will this fail?"},
            )

        assert resp.status_code == 200
        events = []
        for line in resp.text.strip().split("\n"):
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

        error_events = [e for e in events if e["type"] == "error"]
        assert len(error_events) == 1
        assert error_events[0]["error_code"] == "internal_error"


class TestChatWithRAG:
    """Test chat messages with real RAG pipeline (real DB, mocked LLM)."""

    async def _seed_documents(self, db_engine):
        """Insert test documents directly into DB for RAG to find."""
        from app.models import Chunk, Product, Document
        from tests.conftest import fake_embed_single

        session_maker = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
        async with session_maker() as session:
            product = Product(name="TestCam", manufacturer="TestMfg", version="1.0", slug="testmfg-testcam-1-0")
            session.add(product)
            await session.flush()

            doc = Document(
                product_id=product.id,
                format="markdown",
                title="TestCam API Guide",
                status="ready",
                total_chunks=1,
            )
            session.add(doc)
            await session.flush()

            chunk = Chunk(
                document_id=doc.id,
                chunk_index=0,
                heading_path="Authentication > API Keys",
                heading_level=2,
                content="Use API key in the X-Auth header for all requests.",
                token_count=12,
                embedding=fake_embed_single("API key authentication header"),
            )
            session.add(chunk)
            await session.commit()

    async def test_rag_sources_included_in_stream(self, chat_client, db_engine):
        await self._seed_documents(db_engine)

        create_resp = await chat_client.post(
            "/api/v1/chat/sessions",
            json={"title": "RAG Test", "product_filter": "TestCam"},
        )
        session_id = create_resp.json()["id"]

        with patch(
            "app.chat.router.stream_chat_completion",
            return_value=_async_iter(["Use X-Auth header."]),
        ):
            resp = await chat_client.post(
                f"/api/v1/chat/sessions/{session_id}/messages",
                json={"content": "How to authenticate?"},
            )

        events = []
        for line in resp.text.strip().split("\n"):
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

        sources_events = [e for e in events if e["type"] == "sources"]
        assert len(sources_events) == 1
        sources = sources_events[0]["sources"]
        assert len(sources) > 0
        assert sources[0]["doc_title"] == "TestCam API Guide"


class TestDebugPersistence:
    """Test that debug/analytics info is persisted and returned after reload."""

    async def test_debug_persisted_after_stream(self, chat_client):
        """Send a message, then GET session — debug dict must be present."""
        create_resp = await chat_client.post(
            "/api/v1/chat/sessions",
            json={"title": "Debug Persist Test"},
        )
        session_id = create_resp.json()["id"]

        with patch(
            "app.chat.router.stream_chat_completion",
            return_value=_async_iter(["Hello", " world"]),
        ):
            await chat_client.post(
                f"/api/v1/chat/sessions/{session_id}/messages",
                json={"content": "Test question"},
            )

        detail_resp = await chat_client.get(f"/api/v1/chat/sessions/{session_id}")
        assert detail_resp.status_code == 200
        messages = detail_resp.json()["messages"]

        assistant_msgs = [m for m in messages if m["role"] == "assistant"]
        assert len(assistant_msgs) == 1

        debug = assistant_msgs[0].get("debug")
        assert debug is not None, "debug must be present after reload"
        assert "model" in debug
        assert "llm_provider" in debug
        assert "total_ms" in debug
        assert "chunks_found" in debug
        assert "top_similarity" in debug
        assert "embedding_model" in debug
        assert debug["session_id"] == session_id
        assert debug["message_id"] == assistant_msgs[0]["id"]
        assert debug["user_message_id"] is not None
        assert debug["rag_build_ms"] >= 0

    async def test_debug_contains_timing_metrics(self, chat_client):
        """Verify timing fields are populated with non-negative values."""
        create_resp = await chat_client.post(
            "/api/v1/chat/sessions",
            json={"title": "Timing Test"},
        )
        session_id = create_resp.json()["id"]

        with patch(
            "app.chat.router.stream_chat_completion",
            return_value=_async_iter(["Response"]),
        ):
            await chat_client.post(
                f"/api/v1/chat/sessions/{session_id}/messages",
                json={"content": "How does it work?"},
            )

        detail_resp = await chat_client.get(f"/api/v1/chat/sessions/{session_id}")
        debug = detail_resp.json()["messages"][1]["debug"]

        assert debug["total_ms"] >= 0
        assert debug["rag_ms"] >= 0
        assert debug["llm_ms"] >= 0
        assert debug["token_count"] >= 0
        assert debug["response_length"] > 0

    async def test_user_messages_have_no_debug(self, chat_client):
        """User messages should not have debug info."""
        create_resp = await chat_client.post(
            "/api/v1/chat/sessions",
            json={"title": "No Debug Test"},
        )
        session_id = create_resp.json()["id"]

        with patch(
            "app.chat.router.stream_chat_completion",
            return_value=_async_iter(["OK"]),
        ):
            await chat_client.post(
                f"/api/v1/chat/sessions/{session_id}/messages",
                json={"content": "Hello"},
            )

        detail_resp = await chat_client.get(f"/api/v1/chat/sessions/{session_id}")
        user_msgs = [m for m in detail_resp.json()["messages"] if m["role"] == "user"]
        for m in user_msgs:
            assert m.get("debug") is None

    async def test_debug_survives_multiple_messages(self, chat_client):
        """Debug should be present for each assistant message in multi-turn chat."""
        create_resp = await chat_client.post(
            "/api/v1/chat/sessions",
            json={"title": "Multi-turn Debug"},
        )
        session_id = create_resp.json()["id"]

        for i in range(3):
            with patch(
                "app.chat.router.stream_chat_completion",
                return_value=_async_iter([f"Reply {i}"]),
            ):
                await chat_client.post(
                    f"/api/v1/chat/sessions/{session_id}/messages",
                    json={"content": f"Question {i}"},
                )

        detail_resp = await chat_client.get(f"/api/v1/chat/sessions/{session_id}")
        assistant_msgs = [m for m in detail_resp.json()["messages"] if m["role"] == "assistant"]
        assert len(assistant_msgs) == 3

        for msg in assistant_msgs:
            assert msg["debug"] is not None
            assert msg["debug"]["session_id"] == session_id
            assert msg["debug"]["user_message_id"] is not None
