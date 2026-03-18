"""Unit tests for Chat REST API endpoints."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.chat.schemas import (
    ChatMessageResponse,
    CreateSessionRequest,
    SendMessageRequest,
    SessionDetailResponse,
    SessionListItem,
    SessionResponse,
    SourceInfo,
)


def _mock_async_session():
    """Create a mock async session context manager."""
    mock_session = AsyncMock()
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_session, mock_ctx


def _make_mock_chat_session(session_id=1, **overrides):
    s = MagicMock()
    s.id = session_id
    s.title = overrides.get("title")
    s.product_filter = overrides.get("product_filter")
    s.version_filter = overrides.get("version_filter")
    s.doc_context = overrides.get("doc_context")
    s.created_at = overrides.get("created_at", datetime.now(timezone.utc))
    s.updated_at = overrides.get("updated_at", datetime.now(timezone.utc))
    return s


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestChatSchemas:
    def test_create_session_request_defaults(self):
        req = CreateSessionRequest()
        assert req.title is None
        assert req.product_filter is None

    def test_create_session_request_with_values(self):
        req = CreateSessionRequest(title="Test", product_filter="Camera", version_filter="1.0")
        assert req.title == "Test"
        assert req.product_filter == "Camera"

    def test_session_response(self):
        now = datetime.now(timezone.utc)
        r = SessionResponse(id=1, title="Chat", product_filter=None, version_filter=None, created_at=now, updated_at=now)
        assert r.message_count == 0

    def test_session_list_item(self):
        now = datetime.now(timezone.utc)
        item = SessionListItem(
            id=1, title="Test", product_filter=None, version_filter=None,
            created_at=now, updated_at=now, message_count=5, last_message_preview="Hello",
        )
        assert item.message_count == 5
        assert item.last_message_preview == "Hello"

    def test_send_message_request_validation(self):
        req = SendMessageRequest(content="Hello")
        assert req.content == "Hello"

    def test_send_message_request_rejects_empty(self):
        with pytest.raises(Exception):
            SendMessageRequest(content="")

    def test_source_info(self):
        s = SourceInfo(
            doc_title="API Guide", heading_path="Auth", similarity=0.95,
            content_preview="Use HMAC...", product_name="Camera", firmware_version="2.0",
        )
        assert s.similarity == 0.95

    def test_chat_message_response(self):
        now = datetime.now(timezone.utc)
        m = ChatMessageResponse(
            id=1, session_id=1, role="assistant", content="Hello",
            sources=None, duration_ms=150.5, created_at=now,
        )
        assert m.role == "assistant"
        assert m.duration_ms == 150.5

    def test_session_detail_response(self):
        now = datetime.now(timezone.utc)
        d = SessionDetailResponse(
            id=1, title="Test", product_filter=None, version_filter=None,
            created_at=now, updated_at=now,
            messages=[
                ChatMessageResponse(id=1, session_id=1, role="user", content="Hi", created_at=now),
            ],
        )
        assert len(d.messages) == 1


# ---------------------------------------------------------------------------
# Router endpoint tests
# ---------------------------------------------------------------------------

class TestCreateSession:
    @pytest.mark.asyncio
    @patch("app.chat.router.async_session")
    async def test_creates_session(self, mock_session_factory):
        mock_session, mock_ctx = _mock_async_session()
        mock_session_factory.return_value = mock_ctx

        now = datetime.now(timezone.utc)
        mock_chat_session = MagicMock()
        mock_chat_session.id = 42
        mock_chat_session.title = "Test"
        mock_chat_session.product_filter = "Camera"
        mock_chat_session.version_filter = None
        mock_chat_session.doc_context = None
        mock_chat_session.created_at = now
        mock_chat_session.updated_at = now

        mock_session.refresh = AsyncMock(return_value=None)
        mock_session.commit = AsyncMock()

        with patch("app.chat.router.ChatSession") as MockChatSession:
            MockChatSession.return_value = mock_chat_session
            mock_session.add = MagicMock()

            from app.chat.router import create_session
            result = await create_session(CreateSessionRequest(title="Test", product_filter="Camera"))

            assert result.id == 42
            assert result.title == "Test"
            assert result.product_filter == "Camera"


class TestGetSession:
    @pytest.mark.asyncio
    @patch("app.chat.router.async_session")
    async def test_returns_session_with_messages(self, mock_session_factory):
        mock_session, mock_ctx = _mock_async_session()
        mock_session_factory.return_value = mock_ctx

        now = datetime.now(timezone.utc)
        chat_session = _make_mock_chat_session(session_id=5, title="My Chat")
        mock_session.get = AsyncMock(return_value=chat_session)

        mock_msg = MagicMock()
        mock_msg.id = 1
        mock_msg.session_id = 5
        mock_msg.role = "user"
        mock_msg.content = "Hello"
        mock_msg.sources = None
        mock_msg.duration_ms = None
        mock_msg.created_at = now

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_msg]
        mock_session.execute = AsyncMock(return_value=mock_result)

        from app.chat.router import get_session
        result = await get_session(5)

        assert result.id == 5
        assert result.title == "My Chat"
        assert len(result.messages) == 1
        assert result.messages[0].content == "Hello"

    @pytest.mark.asyncio
    @patch("app.chat.router.async_session")
    async def test_returns_404_when_not_found(self, mock_session_factory):
        mock_session, mock_ctx = _mock_async_session()
        mock_session_factory.return_value = mock_ctx
        mock_session.get = AsyncMock(return_value=None)

        from app.chat.router import get_session
        with pytest.raises(Exception) as exc_info:
            await get_session(999)
        assert exc_info.value.status_code == 404


class TestListSessions:
    @pytest.mark.asyncio
    @patch("app.chat.router.async_session")
    async def test_returns_sessions_list(self, mock_session_factory):
        mock_session, mock_ctx = _mock_async_session()
        mock_session_factory.return_value = mock_ctx

        now = datetime.now(timezone.utc)
        row = MagicMock()
        row.id = 1
        row.title = "Test Chat"
        row.product_filter = None
        row.version_filter = None
        row.doc_context = None
        row.created_at = now
        row.updated_at = now
        row.message_count = 3
        row.last_user_msg = "How to authenticate?"

        mock_result = MagicMock()
        mock_result.all.return_value = [row]
        mock_session.execute = AsyncMock(return_value=mock_result)

        from app.chat.router import list_sessions
        result = await list_sessions()

        assert len(result) == 1
        assert result[0].id == 1
        assert result[0].title == "Test Chat"
        assert result[0].message_count == 3
        assert result[0].last_message_preview == "How to authenticate?"

    @pytest.mark.asyncio
    @patch("app.chat.router.async_session")
    async def test_returns_empty_list(self, mock_session_factory):
        mock_session, mock_ctx = _mock_async_session()
        mock_session_factory.return_value = mock_ctx

        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        from app.chat.router import list_sessions
        result = await list_sessions()

        assert result == []

    @pytest.mark.asyncio
    @patch("app.chat.router.async_session")
    async def test_truncates_long_preview(self, mock_session_factory):
        mock_session, mock_ctx = _mock_async_session()
        mock_session_factory.return_value = mock_ctx

        now = datetime.now(timezone.utc)
        row = MagicMock()
        row.id = 2
        row.title = None
        row.product_filter = None
        row.version_filter = None
        row.doc_context = None
        row.created_at = now
        row.updated_at = now
        row.message_count = 1
        row.last_user_msg = "A" * 200

        mock_result = MagicMock()
        mock_result.all.return_value = [row]
        mock_session.execute = AsyncMock(return_value=mock_result)

        from app.chat.router import list_sessions
        result = await list_sessions()

        assert len(result[0].last_message_preview) == 100


class TestSendMessage:
    @pytest.mark.asyncio
    @patch("app.chat.router.async_session")
    async def test_rejects_invalid_session(self, mock_session_factory):
        mock_session, mock_ctx = _mock_async_session()
        mock_session_factory.return_value = mock_ctx
        mock_session.get = AsyncMock(return_value=None)

        from app.chat.router import send_message
        with pytest.raises(Exception) as exc_info:
            await send_message(999, SendMessageRequest(content="hello"))
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("app.chat.router.stream_chat_completion")
    @patch("app.chat.router.build_rag_prompt")
    @patch("app.chat.router.async_session")
    async def test_returns_streaming_response(self, mock_session_factory, mock_rag, mock_llm):
        mock_session, mock_ctx = _mock_async_session()
        mock_session_factory.return_value = mock_ctx

        now = datetime.now(timezone.utc)
        chat_session = _make_mock_chat_session(session_id=1, title="Test")
        chat_session.product_filter = None
        chat_session.version_filter = None
        mock_session.get = AsyncMock(return_value=chat_session)
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_msg = MagicMock()
        mock_msg.id = 10
        mock_session.refresh = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_rag.return_value = (
            [{"role": "user", "content": "hi"}],
            [{"doc_title": "Doc", "heading_path": "H", "similarity": 0.9, "content_preview": "...", "product_name": "", "firmware_version": ""}],
        )

        from app.chat.router import send_message
        response = await send_message(1, SendMessageRequest(content="hello"))

        from fastapi.responses import StreamingResponse
        assert isinstance(response, StreamingResponse)
        assert response.media_type == "text/event-stream"


class TestDeleteSession:
    @pytest.mark.asyncio
    @patch("app.chat.router.async_session")
    async def test_deletes_session(self, mock_session_factory):
        mock_session, mock_ctx = _mock_async_session()
        mock_session_factory.return_value = mock_ctx

        chat_session = _make_mock_chat_session(session_id=3)
        mock_session.get = AsyncMock(return_value=chat_session)
        mock_session.delete = AsyncMock()
        mock_session.commit = AsyncMock()

        from app.chat.router import delete_session
        await delete_session(3)

        mock_session.delete.assert_called_once_with(chat_session)
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.chat.router.async_session")
    async def test_delete_returns_404_when_not_found(self, mock_session_factory):
        mock_session, mock_ctx = _mock_async_session()
        mock_session_factory.return_value = mock_ctx
        mock_session.get = AsyncMock(return_value=None)

        from app.chat.router import delete_session
        with pytest.raises(Exception) as exc_info:
            await delete_session(999)
        assert exc_info.value.status_code == 404
