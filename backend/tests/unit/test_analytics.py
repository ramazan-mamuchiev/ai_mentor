"""Unit tests for analytics ORM models and helper methods."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import ChatMessageAnalytics, SearchAnalytics


class TestChatMessageAnalyticsModel:
    def test_create_from_kwargs(self):
        a = ChatMessageAnalytics(
            message_id=42,
            session_id=1,
            user_message_id=41,
            llm_provider="openai",
            model="gemini-2.5-flash",
            temperature=0.7,
            max_tokens=4096,
            token_count=150,
            tokens_per_sec=30.0,
            response_length=600,
            total_ms=5000.0,
            rag_ms=200.0,
            llm_ms=4500.0,
            search_ms=180.0,
            first_token_ms=800.0,
            rag_build_ms=195.0,
            chunks_found=3,
            top_similarity=0.92,
            min_similarity=0.75,
            context_tokens=1200,
            history_messages=4,
            prompt_messages=6,
            embedding_model="intfloat/multilingual-e5-large",
            doc_context="HikCentral API Guide",
            auto_product="HikCentral",
            detected_doc_context="HikCentral API Guide",
            search_query="how to authenticate with HikCentral",
        )
        assert a.message_id == 42
        assert a.user_message_id == 41
        assert a.llm_provider == "openai"
        assert a.model == "gemini-2.5-flash"
        assert a.temperature == 0.7
        assert a.rag_build_ms == 195.0
        assert a.chunks_found == 3
        assert a.doc_context == "HikCentral API Guide"

    def test_to_debug_dict_contains_all_keys(self):
        a = ChatMessageAnalytics(
            message_id=1,
            session_id=1,
            llm_provider="ollama",
            model="qwen2.5-coder:7b",
            temperature=0.0,
            max_tokens=2048,
            token_count=50,
            tokens_per_sec=25.0,
            response_length=200,
            total_ms=3000.0,
            rag_ms=100.0,
            llm_ms=2800.0,
            search_ms=90.0,
            first_token_ms=500.0,
            chunks_found=2,
            top_similarity=0.88,
            min_similarity=0.72,
            context_tokens=800,
            history_messages=0,
            prompt_messages=2,
            embedding_model="intfloat/multilingual-e5-large",
            created_at=datetime(2026, 3, 19, 12, 0, 0, tzinfo=timezone.utc),
        )

        d = a.to_debug_dict()

        expected_keys = {
            "session_id", "message_id", "user_message_id", "timestamp",
            "model", "llm_provider", "temperature", "max_tokens",
            "first_token_ms", "rag_ms", "llm_ms", "total_ms", "search_ms",
            "rag_build_ms",
            "token_count", "tokens_per_sec", "response_length",
            "chunks_found", "top_similarity", "min_similarity",
            "context_tokens", "history_messages", "prompt_messages",
            "embedding_model",
            "product_filter", "version_filter",
            "doc_context", "auto_product", "detected_doc_context", "search_query",
            "user_input_tokens", "user_output_tokens",
            "llm_prompt_tokens", "llm_completion_tokens", "llm_total_tokens",
        }
        assert set(d.keys()) == expected_keys

    def test_to_debug_dict_values(self):
        a = ChatMessageAnalytics(
            message_id=10,
            session_id=5,
            user_message_id=9,
            llm_provider="openai",
            model="gemini-2.5-flash",
            temperature=0.3,
            max_tokens=4096,
            token_count=100,
            tokens_per_sec=20.0,
            response_length=400,
            total_ms=2000.0,
            rag_ms=150.0,
            llm_ms=1800.0,
            search_ms=120.0,
            first_token_ms=600.0,
            rag_build_ms=145.0,
            chunks_found=5,
            top_similarity=0.95,
            min_similarity=0.80,
            context_tokens=1500,
            history_messages=2,
            prompt_messages=4,
            embedding_model="text-embedding-3-small",
            doc_context="API Guide",
            auto_product=None,
            detected_doc_context=None,
            search_query="test query",
            created_at=datetime(2026, 3, 19, 10, 30, 0, tzinfo=timezone.utc),
        )

        d = a.to_debug_dict()
        assert d["session_id"] == 5
        assert d["message_id"] == 10
        assert d["user_message_id"] == 9
        assert d["model"] == "gemini-2.5-flash"
        assert d["llm_provider"] == "openai"
        assert d["temperature"] == 0.3
        assert d["rag_build_ms"] == 145.0
        assert d["top_similarity"] == 0.95
        assert d["doc_context"] == "API Guide"
        assert d["auto_product"] is None
        assert d["product_filter"] is None
        assert d["version_filter"] is None
        assert d["search_query"] == "test query"
        assert d["timestamp"] == "2026-03-19T10:30:00+00:00"

    def test_nullable_context_fields(self):
        a = ChatMessageAnalytics(
            message_id=1,
            session_id=1,
            llm_provider="ollama",
            model="qwen",
            doc_context=None,
            auto_product=None,
            detected_doc_context=None,
            search_query=None,
        )
        d = a.to_debug_dict()
        assert d["doc_context"] is None
        assert d["auto_product"] is None
        assert d["detected_doc_context"] is None
        assert d["search_query"] is None
        assert d["product_filter"] is None
        assert d["version_filter"] is None

    def test_to_debug_dict_with_session_filters(self):
        a = ChatMessageAnalytics(
            message_id=1,
            session_id=1,
            llm_provider="openai",
            model="gemini-2.5-flash",
        )
        d = a.to_debug_dict(product_filter="Axxon One", version_filter="2.0")
        assert d["product_filter"] == "Axxon One"
        assert d["version_filter"] == "2.0"


class TestSearchAnalyticsModel:
    def test_create_mcp_search(self):
        sa = SearchAnalytics(
            source="mcp",
            tool_name="search_documentation",
            query="how to open a door",
            product_filter="HikCentral",
            version_filter="V2.6",
            result_count=5,
            top_similarity=0.91,
            duration_ms=250.5,
            embedding_model="intfloat/multilingual-e5-large",
        )
        assert sa.source == "mcp"
        assert sa.tool_name == "search_documentation"
        assert sa.query == "how to open a door"
        assert sa.product_filter == "HikCentral"
        assert sa.version_filter == "V2.6"
        assert sa.result_count == 5
        assert sa.top_similarity == 0.91
        assert sa.duration_ms == 250.5

    def test_create_mcp_list_products(self):
        sa = SearchAnalytics(
            source="mcp",
            tool_name="list_products",
            query="",
            result_count=10,
            top_similarity=0,
            duration_ms=50.0,
            embedding_model="",
        )
        assert sa.tool_name == "list_products"
        assert sa.query == ""
        assert sa.top_similarity == 0
        assert sa.product_filter is None

    def test_create_mcp_get_api_endpoint(self):
        sa = SearchAnalytics(
            source="mcp",
            tool_name="get_api_endpoint",
            query="/acs/v1/door/doControl",
            product_filter="HikCentral",
            result_count=2,
            top_similarity=0.85,
            duration_ms=180.0,
            embedding_model="intfloat/multilingual-e5-large",
        )
        assert sa.tool_name == "get_api_endpoint"
        assert sa.query == "/acs/v1/door/doControl"
        assert sa.result_count == 2


class TestMcpSaveSearchAnalytics:
    """Verify that MCP tools call _save_search_analytics with correct args."""

    @pytest.mark.asyncio
    @patch("app.mcp.server._save_search_analytics", new_callable=AsyncMock)
    @patch("app.mcp.server.search_documents")
    async def test_search_documentation_saves_analytics(self, mock_search, mock_save):
        mock_search.return_value = [
            {"similarity": 0.91, "product_name": "X", "firmware_version": "1.0",
             "doc_title": "D", "heading_path": "H", "content": "C"},
        ]
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = AsyncMock()
        mock_cm.__aexit__.return_value = None

        with patch("app.mcp.server.async_session", return_value=mock_cm):
            from app.mcp.server import tool_search_documentation
            await tool_search_documentation(query="door control", product="HikCentral", version="2.6", limit=5)

        mock_save.assert_called_once()
        call_kwargs = mock_save.call_args
        args = call_kwargs.kwargs if call_kwargs.kwargs else {}
        if not args:
            args = dict(zip(
                ["source", "tool_name", "query", "duration_ms", "result_count",
                 "top_similarity", "product_filter", "version_filter"],
                call_kwargs.args if call_kwargs.args else [],
            ))
            if not args:
                args = {k: v for k, v in zip(
                    ["source", "tool_name", "query", "duration_ms", "result_count",
                     "top_similarity", "product_filter", "version_filter"],
                    call_kwargs[0] if call_kwargs[0] else [],
                )}

        assert mock_save.call_args.kwargs["source"] == "mcp"
        assert mock_save.call_args.kwargs["tool_name"] == "search_documentation"
        assert mock_save.call_args.kwargs["query"] == "door control"
        assert mock_save.call_args.kwargs["product_filter"] == "HikCentral"
        assert mock_save.call_args.kwargs["version_filter"] == "2.6"
        assert mock_save.call_args.kwargs["result_count"] == 1
        assert mock_save.call_args.kwargs["top_similarity"] == 0.91

    @pytest.mark.asyncio
    @patch("app.mcp.server._save_search_analytics", new_callable=AsyncMock)
    @patch("app.mcp.server.search_endpoint")
    async def test_get_api_endpoint_saves_analytics(self, mock_search, mock_save):
        mock_search.return_value = [
            {"similarity": 0.85, "product_name": "X", "firmware_version": "1.0",
             "doc_title": "D", "heading_path": "H", "content": "C", "match_type": "exact"},
        ]
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = AsyncMock()
        mock_cm.__aexit__.return_value = None

        with patch("app.mcp.server.async_session", return_value=mock_cm):
            from app.mcp.server import tool_get_api_endpoint
            await tool_get_api_endpoint(endpoint="/doors/open", product="TestProd")

        mock_save.assert_called_once()
        assert mock_save.call_args.kwargs["source"] == "mcp"
        assert mock_save.call_args.kwargs["tool_name"] == "get_api_endpoint"
        assert mock_save.call_args.kwargs["query"] == "/doors/open"
        assert mock_save.call_args.kwargs["product_filter"] == "TestProd"
        assert mock_save.call_args.kwargs["result_count"] == 1

    @pytest.mark.asyncio
    @patch("app.mcp.server._save_search_analytics", new_callable=AsyncMock)
    async def test_list_products_saves_analytics(self, mock_save):
        mock_cm = AsyncMock()
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        mock_cm.__aenter__.return_value = mock_session
        mock_cm.__aexit__.return_value = None

        with patch("app.mcp.server.async_session", return_value=mock_cm):
            from app.mcp.server import tool_list_products
            await tool_list_products(query="Hikvision")

        mock_save.assert_called_once()
        assert mock_save.call_args.kwargs["source"] == "mcp"
        assert mock_save.call_args.kwargs["tool_name"] == "list_products"
        assert mock_save.call_args.kwargs["query"] == "Hikvision"

    @pytest.mark.asyncio
    @patch("app.mcp.server._save_search_analytics", new_callable=AsyncMock)
    @patch("app.mcp.server.search_documents")
    async def test_search_no_results_saves_analytics(self, mock_search, mock_save):
        mock_search.return_value = []
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = AsyncMock()
        mock_cm.__aexit__.return_value = None

        with patch("app.mcp.server.async_session", return_value=mock_cm):
            from app.mcp.server import tool_search_documentation
            await tool_search_documentation(query="nonexistent")

        mock_save.assert_called_once()
        assert mock_save.call_args.kwargs["result_count"] == 0
        assert mock_save.call_args.kwargs["top_similarity"] == 0.0
