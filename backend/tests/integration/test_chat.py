"""Integration tests for Chat functionality with real PostgreSQL."""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select, text

from app.models import ChatMessage, ChatSession, Product, Document, FirmwareVersion, Chunk
from app.chat.rag import build_rag_prompt


class TestChatSessionsCRUD:
    """Test chat session CRUD operations against real PostgreSQL."""

    async def test_create_session(self, db_session):
        session = ChatSession(title="Test Chat", product_filter="Camera")
        db_session.add(session)
        await db_session.flush()

        assert session.id is not None
        assert session.title == "Test Chat"
        assert session.product_filter == "Camera"
        assert session.created_at is not None

    async def test_create_session_without_filters(self, db_session):
        session = ChatSession()
        db_session.add(session)
        await db_session.flush()

        assert session.id is not None
        assert session.title is None
        assert session.product_filter is None
        assert session.version_filter is None

    async def test_delete_session_cascades_messages(self, db_session):
        session = ChatSession(title="To Delete")
        db_session.add(session)
        await db_session.flush()

        msg1 = ChatMessage(session_id=session.id, role="user", content="Hello")
        msg2 = ChatMessage(session_id=session.id, role="assistant", content="Hi!")
        db_session.add_all([msg1, msg2])
        await db_session.flush()

        result = await db_session.execute(
            select(ChatMessage).where(ChatMessage.session_id == session.id)
        )
        assert len(result.scalars().all()) == 2

        await db_session.delete(session)
        await db_session.flush()

        result = await db_session.execute(
            select(ChatMessage).where(ChatMessage.session_id == session.id)
        )
        assert len(result.scalars().all()) == 0

    async def test_multiple_sessions_independent(self, db_session):
        s1 = ChatSession(title="Session 1")
        s2 = ChatSession(title="Session 2")
        db_session.add_all([s1, s2])
        await db_session.flush()

        msg1 = ChatMessage(session_id=s1.id, role="user", content="In session 1")
        msg2 = ChatMessage(session_id=s2.id, role="user", content="In session 2")
        db_session.add_all([msg1, msg2])
        await db_session.flush()

        r1 = await db_session.execute(
            select(ChatMessage).where(ChatMessage.session_id == s1.id)
        )
        r2 = await db_session.execute(
            select(ChatMessage).where(ChatMessage.session_id == s2.id)
        )
        assert len(r1.scalars().all()) == 1
        assert len(r2.scalars().all()) == 1


class TestChatMessagesCRUD:
    """Test chat message operations against real PostgreSQL."""

    async def test_create_user_message(self, db_session):
        session = ChatSession(title="Test")
        db_session.add(session)
        await db_session.flush()

        msg = ChatMessage(
            session_id=session.id,
            role="user",
            content="How to authenticate?",
        )
        db_session.add(msg)
        await db_session.flush()

        assert msg.id is not None
        assert msg.role == "user"
        assert msg.sources is None
        assert msg.duration_ms is None

    async def test_create_assistant_message_with_sources(self, db_session):
        session = ChatSession(title="Test")
        db_session.add(session)
        await db_session.flush()

        sources = [
            {"doc_title": "API Guide", "heading_path": "Auth", "similarity": 0.92}
        ]
        msg = ChatMessage(
            session_id=session.id,
            role="assistant",
            content="Use HMAC-SHA256 for authentication.",
            sources=sources,
            duration_ms=1500.5,
        )
        db_session.add(msg)
        await db_session.flush()

        fetched = await db_session.get(ChatMessage, msg.id)
        assert fetched.sources == sources
        assert fetched.duration_ms == 1500.5

    async def test_messages_ordered_by_created_at(self, db_session):
        session = ChatSession(title="Test")
        db_session.add(session)
        await db_session.flush()

        for i in range(5):
            role = "user" if i % 2 == 0 else "assistant"
            msg = ChatMessage(session_id=session.id, role=role, content=f"Message {i}")
            db_session.add(msg)
        await db_session.flush()

        result = await db_session.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.created_at)
        )
        messages = result.scalars().all()
        assert len(messages) == 5
        for i, msg in enumerate(messages):
            assert msg.content == f"Message {i}"


class TestRAGIntegration:
    """Test RAG pipeline with real data in PostgreSQL."""

    async def _ingest_test_data(self, db_session):
        """Insert a product, document, and chunks for RAG testing."""
        product = Product(name="HikCentral", manufacturer="Hikvision")
        db_session.add(product)
        await db_session.flush()

        fw = FirmwareVersion(product_id=product.id, version="2.6")
        db_session.add(fw)
        await db_session.flush()

        doc = Document(
            product_id=product.id,
            firmware_version_id=fw.id,
            format="pdf",
            title="HikCentral API Guide",
            status="ready",
            total_chunks=2,
        )
        db_session.add(doc)
        await db_session.flush()

        from tests.conftest import fake_embed_single

        chunk1 = Chunk(
            document_id=doc.id,
            chunk_index=0,
            heading_path="Authentication > HMAC-SHA256",
            heading_level=2,
            content="Use HMAC-SHA256 to sign API requests. Include the signature in the Authorization header.",
            token_count=20,
            embedding=fake_embed_single("HMAC-SHA256 authentication"),
        )
        chunk2 = Chunk(
            document_id=doc.id,
            chunk_index=1,
            heading_path="Door Control > Open Door",
            heading_level=2,
            content="POST /api/v1/doors/{id}/open to remotely open a door. Requires door_id parameter.",
            token_count=18,
            embedding=fake_embed_single("open door API endpoint"),
        )
        db_session.add_all([chunk1, chunk2])
        await db_session.flush()

        return product, doc

    async def test_rag_finds_relevant_chunks(self, db_session):
        await self._ingest_test_data(db_session)

        messages, sources = await build_rag_prompt(
            db=db_session,
            query="How to authenticate with HMAC?",
        )

        assert len(messages) >= 3
        assert messages[0]["role"] == "system"
        assert "IPCodex AI Assistant" in messages[0]["content"]
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "How to authenticate with HMAC?"
        assert len(sources) > 0

    async def test_rag_with_product_filter(self, db_session):
        await self._ingest_test_data(db_session)

        _, sources_match = await build_rag_prompt(
            db=db_session,
            query="authentication",
            product_filter="HikCentral",
        )

        _, sources_no_match = await build_rag_prompt(
            db=db_session,
            query="authentication",
            product_filter="NonExistentDevice",
        )

        assert len(sources_match) > 0
        assert len(sources_no_match) == 0

    async def test_rag_includes_history(self, db_session):
        await self._ingest_test_data(db_session)

        session = ChatSession(title="Test")
        db_session.add(session)
        await db_session.flush()

        history = [
            ChatMessage(session_id=session.id, role="user", content="What is HMAC?"),
            ChatMessage(session_id=session.id, role="assistant", content="HMAC is a hash-based auth."),
        ]
        for h in history:
            db_session.add(h)
        await db_session.flush()

        messages, _ = await build_rag_prompt(
            db=db_session,
            query="How do I use it?",
            history=history,
        )

        contents = [m["content"] for m in messages]
        assert any("What is HMAC?" in c for c in contents)
        assert any("HMAC is a hash-based auth." in c for c in contents)
        assert messages[-1]["content"] == "How do I use it?"

    async def test_rag_empty_db(self, db_session):
        messages, sources = await build_rag_prompt(
            db=db_session,
            query="anything at all",
        )

        assert len(sources) == 0
        context_msg = messages[1]["content"]
        assert "No relevant documentation found" in context_msg

    async def test_rag_source_fields(self, db_session):
        await self._ingest_test_data(db_session)

        _, sources = await build_rag_prompt(
            db=db_session,
            query="door control",
        )

        assert len(sources) > 0
        s = sources[0]
        assert "doc_title" in s
        assert "heading_path" in s
        assert "similarity" in s
        assert "content_preview" in s
        assert isinstance(s["similarity"], float)
        assert 0 <= s["similarity"] <= 1
        assert len(s["content_preview"]) <= 200
