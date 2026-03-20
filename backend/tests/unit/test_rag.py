"""Unit tests for RAG service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.chat.rag import _format_context, _build_history_messages, build_rag_prompt


class TestFormatContext:
    def test_empty_chunks(self):
        result = _format_context([])
        assert result == "No relevant documentation found."

    def test_single_chunk(self):
        chunks = [{
            "doc_title": "API Guide",
            "heading_path": "Auth > Login",
            "product_name": "Camera X",
            "firmware_version": "2.0",
            "similarity": 0.85,
            "content": "Use POST /api/login to authenticate.",
        }]
        result = _format_context(chunks)
        assert "API Guide" in result
        assert "Auth > Login" in result
        assert "Camera X" in result
        assert "FW: 2.0" in result
        assert "0.85" in result
        assert "POST /api/login" in result

    def test_multiple_chunks_numbered(self):
        chunks = [
            {"doc_title": "Doc1", "heading_path": "H1", "product_name": "", "firmware_version": "", "similarity": 0.9, "content": "Content 1"},
            {"doc_title": "Doc2", "heading_path": "H2", "product_name": "", "firmware_version": "", "similarity": 0.8, "content": "Content 2"},
        ]
        result = _format_context(chunks)
        assert "Source 1:" in result
        assert "Source 2:" in result

    def test_chunk_without_product(self):
        chunks = [{
            "doc_title": "Manual",
            "heading_path": "Setup",
            "product_name": "",
            "firmware_version": "",
            "similarity": 0.7,
            "content": "Setup instructions.",
        }]
        result = _format_context(chunks)
        assert "Product:" not in result


class TestBuildHistoryMessages:
    def test_empty_history(self):
        result = _build_history_messages([], 10)
        assert result == []

    def test_respects_max_messages(self):
        msgs = [MagicMock(role="user", content=f"msg{i}") for i in range(20)]
        result = _build_history_messages(msgs, 5)
        assert len(result) == 5
        assert result[0]["content"] == "msg15"
        assert result[-1]["content"] == "msg19"

    def test_returns_all_when_under_limit(self):
        msgs = [MagicMock(role="user", content="a"), MagicMock(role="assistant", content="b")]
        result = _build_history_messages(msgs, 10)
        assert len(result) == 2
        assert result[0] == {"role": "user", "content": "a"}
        assert result[1] == {"role": "assistant", "content": "b"}


class TestBuildRagPrompt:
    @pytest.mark.asyncio
    @patch("app.chat.rag._detect_product_from_query", new_callable=AsyncMock, return_value=None)
    @patch("app.chat.rag.search_documents")
    async def test_builds_prompt_with_context(self, mock_search, _mock_detect):
        mock_search.return_value = [
            {
                "content": "Use HMAC-SHA256 for auth.",
                "heading_path": "Authentication",
                "heading_level": 2,
                "token_count": 10,
                "doc_title": "HikCentral API",
                "product_name": "HikCentral",
                "manufacturer": "Hikvision",
                "firmware_version": "2.6",
                "similarity": 0.92,
            }
        ]

        db = AsyncMock()
        messages, sources, _debug = await build_rag_prompt(
            db=db,
            query="How to authenticate?",
            product_filter="HikCentral",
        )

        assert len(messages) >= 2
        assert messages[0]["role"] == "system"
        assert "IPCodex AI" in messages[0]["content"]
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "How to authenticate?"

        assert len(sources) == 1
        assert sources[0]["doc_title"] == "HikCentral API"
        assert sources[0]["similarity"] == 0.92

    @pytest.mark.asyncio
    @patch("app.chat.rag._detect_product_from_query", new_callable=AsyncMock, return_value=None)
    @patch("app.chat.rag.search_documents")
    async def test_system_prompt_instructs_code_generation(self, mock_search, _mock_detect):
        mock_search.return_value = []
        db = AsyncMock()
        messages, _, _debug = await build_rag_prompt(db=db, query="test")

        system_content = messages[0]["content"]
        assert "code examples" in system_content.lower()
        assert "API endpoints" in system_content
        assert "same language as the user" in system_content

    @pytest.mark.asyncio
    @patch("app.chat.rag._detect_product_from_query", new_callable=AsyncMock, return_value=None)
    @patch("app.chat.rag.search_documents")
    async def test_content_preview_length_500(self, mock_search, _mock_detect):
        long_content = "A" * 1000
        mock_search.return_value = [
            {
                "content": long_content,
                "heading_path": "Section",
                "heading_level": 2,
                "token_count": 200,
                "doc_title": "Doc",
                "product_name": "",
                "manufacturer": "",
                "firmware_version": "",
                "similarity": 0.8,
            }
        ]
        db = AsyncMock()
        _, sources, _debug = await build_rag_prompt(db=db, query="test")

        assert len(sources[0]["content_preview"]) == 500

    @pytest.mark.asyncio
    @patch("app.chat.rag._detect_product_from_query", new_callable=AsyncMock, return_value=None)
    @patch("app.chat.rag.search_documents")
    async def test_includes_history(self, mock_search, _mock_detect):
        mock_search.return_value = []

        history = [
            MagicMock(role="user", content="Hello"),
            MagicMock(role="assistant", content="Hi there!"),
        ]

        db = AsyncMock()
        messages, sources, _debug = await build_rag_prompt(
            db=db,
            query="What is the API key?",
            history=history,
        )

        roles = [m["role"] for m in messages]
        assert "user" in roles
        assert "assistant" in roles
        assert messages[-1]["content"] == "What is the API key?"

    @pytest.mark.asyncio
    @patch("app.chat.rag._detect_product_from_query", new_callable=AsyncMock, return_value=None)
    @patch("app.chat.rag.search_documents")
    async def test_empty_search_results(self, mock_search, _mock_detect):
        mock_search.return_value = []

        db = AsyncMock()
        messages, sources, _debug = await build_rag_prompt(db=db, query="Unknown topic")

        assert len(sources) == 0
        system_content = messages[0]["content"]
        assert "No relevant documentation found" in system_content

    @pytest.mark.asyncio
    @patch("app.chat.rag._detect_product_from_query", new_callable=AsyncMock, return_value=None)
    @patch("app.chat.rag.search_documents")
    async def test_system_prompt_instructs_proto_formatting(self, mock_search, _mock_detect):
        mock_search.return_value = []
        db = AsyncMock()
        messages, _, _debug = await build_rag_prompt(db=db, query="test")

        system_content = messages[0]["content"]
        assert "proto/gRPC" in system_content
        assert "proto" in system_content.lower()
        assert "table" in system_content.lower()
