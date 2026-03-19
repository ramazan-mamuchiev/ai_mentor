"""Unit tests for LLM client (Ollama API)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.llm.client import LLMError, _error_code_from_status


class TestLLMError:
    """Test LLMError class and error_code_from_status mapping."""

    def test_llm_error_attributes(self):
        err = LLMError(400, "bad_request", "Bad request detail")
        assert err.status_code == 400
        assert err.error_code == "bad_request"
        assert err.detail == "Bad request detail"
        assert str(err) == "Bad request detail"

    def test_llm_error_is_exception(self):
        err = LLMError(500, "server_error", "fail")
        assert isinstance(err, Exception)

    @pytest.mark.parametrize("status,expected_code", [
        (400, "bad_request"),
        (401, "auth_failed"),
        (403, "auth_failed"),
        (404, "model_not_found"),
        (429, "rate_limited"),
        (500, "server_error"),
        (502, "server_error"),
        (503, "server_error"),
        (422, "bad_request"),
    ])
    def test_error_code_from_status(self, status, expected_code):
        assert _error_code_from_status(status) == expected_code


class TestStreamChatCompletion:
    """Test stream_chat_completion function."""

    @pytest.mark.asyncio
    async def test_yields_tokens_from_stream(self):
        chunks = [
            json.dumps({"message": {"content": "Hello"}, "done": False}),
            json.dumps({"message": {"content": " world"}, "done": False}),
            json.dumps({"done": True}),
        ]

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.aiter_lines = MagicMock(return_value=_async_iter(chunks))

        mock_client = AsyncMock()
        mock_stream_ctx = AsyncMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_client.stream = MagicMock(return_value=mock_stream_ctx)

        mock_client_ctx = AsyncMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.llm.client.httpx.AsyncClient", return_value=mock_client_ctx):
            from app.llm.client import stream_chat_completion

            tokens = []
            async for token in stream_chat_completion([{"role": "user", "content": "hi"}]):
                tokens.append(token)

            assert tokens == ["Hello", " world"]

    @pytest.mark.asyncio
    async def test_raises_llm_error_on_non_200(self):
        mock_response = AsyncMock()
        mock_response.status_code = 500
        mock_response.aread = AsyncMock(return_value=b"Internal Server Error")

        mock_client = AsyncMock()
        mock_stream_ctx = AsyncMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_client.stream = MagicMock(return_value=mock_stream_ctx)

        mock_client_ctx = AsyncMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.llm.client.httpx.AsyncClient", return_value=mock_client_ctx):
            from app.llm.client import stream_chat_completion

            with pytest.raises(LLMError) as exc_info:
                async for _ in stream_chat_completion([{"role": "user", "content": "hi"}]):
                    pass
            assert exc_info.value.status_code == 500
            assert exc_info.value.error_code == "server_error"

    @pytest.mark.asyncio
    async def test_raises_llm_error_on_401(self):
        mock_response = AsyncMock()
        mock_response.status_code = 401
        mock_response.aread = AsyncMock(return_value=b"Unauthorized")

        mock_client = AsyncMock()
        mock_stream_ctx = AsyncMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_client.stream = MagicMock(return_value=mock_stream_ctx)

        mock_client_ctx = AsyncMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.llm.client.httpx.AsyncClient", return_value=mock_client_ctx):
            from app.llm.client import stream_chat_completion

            with pytest.raises(LLMError) as exc_info:
                async for _ in stream_chat_completion([{"role": "user", "content": "hi"}]):
                    pass
            assert exc_info.value.error_code == "auth_failed"

    @pytest.mark.asyncio
    async def test_raises_llm_error_on_connect_error(self):
        mock_client = AsyncMock()
        mock_client.stream = MagicMock(side_effect=httpx.ConnectError("Connection refused"))

        mock_client_ctx = AsyncMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.llm.client.httpx.AsyncClient", return_value=mock_client_ctx):
            from app.llm.client import stream_chat_completion

            with pytest.raises(LLMError) as exc_info:
                async for _ in stream_chat_completion([{"role": "user", "content": "hi"}]):
                    pass
            assert exc_info.value.error_code == "unreachable"

    @pytest.mark.asyncio
    async def test_raises_llm_error_on_timeout(self):
        mock_client = AsyncMock()
        mock_client.stream = MagicMock(side_effect=httpx.ReadTimeout("Read timed out"))

        mock_client_ctx = AsyncMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.llm.client.httpx.AsyncClient", return_value=mock_client_ctx):
            from app.llm.client import stream_chat_completion

            with pytest.raises(LLMError) as exc_info:
                async for _ in stream_chat_completion([{"role": "user", "content": "hi"}]):
                    pass
            assert exc_info.value.error_code == "timeout"

    @pytest.mark.asyncio
    async def test_skips_empty_content(self):
        chunks = [
            json.dumps({"message": {"content": ""}, "done": False}),
            json.dumps({"message": {"content": "data"}, "done": False}),
            json.dumps({"done": True}),
        ]

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.aiter_lines = MagicMock(return_value=_async_iter(chunks))

        mock_client = AsyncMock()
        mock_stream_ctx = AsyncMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_client.stream = MagicMock(return_value=mock_stream_ctx)

        mock_client_ctx = AsyncMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.llm.client.httpx.AsyncClient", return_value=mock_client_ctx):
            from app.llm.client import stream_chat_completion

            tokens = []
            async for token in stream_chat_completion([{"role": "user", "content": "hi"}]):
                tokens.append(token)

            assert tokens == ["data"]


    @pytest.mark.asyncio
    async def test_handles_malformed_json(self):
        chunks = [
            "not valid json",
            json.dumps({"message": {"content": "ok"}, "done": False}),
            json.dumps({"done": True}),
        ]

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.aiter_lines = MagicMock(return_value=_async_iter(chunks))

        mock_client = AsyncMock()
        mock_stream_ctx = AsyncMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_client.stream = MagicMock(return_value=mock_stream_ctx)

        mock_client_ctx = AsyncMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.llm.client.httpx.AsyncClient", return_value=mock_client_ctx):
            from app.llm.client import stream_chat_completion

            tokens = []
            async for token in stream_chat_completion([{"role": "user", "content": "hi"}]):
                tokens.append(token)

            assert tokens == ["ok"]

    @pytest.mark.asyncio
    async def test_handles_empty_lines(self):
        chunks = [
            "",
            "   ",
            json.dumps({"message": {"content": "data"}, "done": False}),
            "",
            json.dumps({"done": True}),
        ]

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.aiter_lines = MagicMock(return_value=_async_iter(chunks))

        mock_client = AsyncMock()
        mock_stream_ctx = AsyncMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_client.stream = MagicMock(return_value=mock_stream_ctx)

        mock_client_ctx = AsyncMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.llm.client.httpx.AsyncClient", return_value=mock_client_ctx):
            from app.llm.client import stream_chat_completion

            tokens = []
            async for token in stream_chat_completion([{"role": "user", "content": "hi"}]):
                tokens.append(token)

            assert tokens == ["data"]


class TestCheckHealth:
    """Test check_health function."""

    @pytest.mark.asyncio
    async def test_returns_true_when_model_available(self):
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json = MagicMock(return_value={
            "models": [{"name": "mistral:latest"}, {"name": "llama2:latest"}]
        })

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_ctx = AsyncMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.llm.client.httpx.AsyncClient", return_value=mock_client_ctx),
            patch("app.llm.client.settings") as mock_settings,
        ):
            mock_settings.llm_provider = "ollama"
            mock_settings.ollama_url = "http://ollama:11434"
            mock_settings.llm_model = "mistral:latest"
            from app.llm.client import check_health
            result = await check_health()
            assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_model_not_found(self):
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json = MagicMock(return_value={"models": [{"name": "llama2:latest"}]})

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_ctx = AsyncMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.llm.client.httpx.AsyncClient", return_value=mock_client_ctx),
            patch("app.llm.client.settings") as mock_settings,
        ):
            mock_settings.llm_provider = "ollama"
            mock_settings.ollama_url = "http://ollama:11434"
            mock_settings.llm_model = "nonexistent-model:latest"
            from app.llm.client import check_health
            result = await check_health()
            assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_connection_error(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))
        mock_client_ctx = AsyncMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.llm.client.httpx.AsyncClient", return_value=mock_client_ctx),
            patch("app.llm.client.settings") as mock_settings,
        ):
            mock_settings.llm_provider = "ollama"
            mock_settings.ollama_url = "http://ollama:11434"
            from app.llm.client import check_health
            result = await check_health()
            assert result is False


async def _async_iter(items):
    for item in items:
        yield item
