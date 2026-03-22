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


def _patch_ollama_settings():
    """Return a patch context that forces the Ollama provider path."""
    mock_settings = MagicMock()
    mock_settings.llm_provider = "ollama"
    mock_settings.ollama_url = "http://ollama:11434"
    mock_settings.llm_model = "qwen2.5-coder:7b"
    mock_settings.llm_temperature = 0.2
    mock_settings.llm_max_tokens = 4096
    mock_settings.llm_timeout = 60
    return patch("app.llm.client.settings", mock_settings)


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

        with _patch_ollama_settings(), patch("app.llm.client.httpx.AsyncClient", return_value=mock_client_ctx):
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

        with _patch_ollama_settings(), patch("app.llm.client.httpx.AsyncClient", return_value=mock_client_ctx):
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

        with _patch_ollama_settings(), patch("app.llm.client.httpx.AsyncClient", return_value=mock_client_ctx):
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

        with _patch_ollama_settings(), patch("app.llm.client.httpx.AsyncClient", return_value=mock_client_ctx):
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

        with _patch_ollama_settings(), patch("app.llm.client.httpx.AsyncClient", return_value=mock_client_ctx):
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

        with _patch_ollama_settings(), patch("app.llm.client.httpx.AsyncClient", return_value=mock_client_ctx):
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

        with _patch_ollama_settings(), patch("app.llm.client.httpx.AsyncClient", return_value=mock_client_ctx):
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

        with _patch_ollama_settings(), patch("app.llm.client.httpx.AsyncClient", return_value=mock_client_ctx):
            from app.llm.client import stream_chat_completion

            tokens = []
            async for token in stream_chat_completion([{"role": "user", "content": "hi"}]):
                tokens.append(token)

            assert tokens == ["data"]


class TestFinishReason:
    """Test that finish_reason is captured in metadata."""

    @pytest.mark.asyncio
    async def test_ollama_finish_reason_stop(self):
        chunks = [
            json.dumps({"message": {"content": "Hello"}, "done": False}),
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

        with _patch_ollama_settings(), patch("app.llm.client.httpx.AsyncClient", return_value=mock_client_ctx):
            from app.llm.client import stream_chat_completion

            meta: dict = {}
            async for _ in stream_chat_completion([{"role": "user", "content": "hi"}], metadata=meta):
                pass

            assert meta["finish_reason"] == "stop"

    @pytest.mark.asyncio
    async def test_ollama_finish_reason_length(self):
        chunks = [
            json.dumps({"message": {"content": "Hello"}, "done": False}),
            json.dumps({"done": True, "done_reason": "length"}),
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

        with _patch_ollama_settings(), patch("app.llm.client.httpx.AsyncClient", return_value=mock_client_ctx):
            from app.llm.client import stream_chat_completion

            meta: dict = {}
            async for _ in stream_chat_completion([{"role": "user", "content": "hi"}], metadata=meta):
                pass

            assert meta["finish_reason"] == "length"

    @pytest.mark.asyncio
    async def test_openai_finish_reason_stop(self):
        chunks = [
            'data: {"choices":[{"delta":{"content":"Hi"},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
            "data: [DONE]",
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

        with (
            patch("app.llm.client.httpx.AsyncClient", return_value=mock_client_ctx),
            patch("app.llm.client.settings") as mock_settings,
        ):
            mock_settings.llm_provider = "openai"
            mock_settings.openai_llm_model = "gpt-4"
            mock_settings.llm_temperature = 0.2
            mock_settings.llm_max_tokens = 4096
            mock_settings.llm_timeout = 60
            mock_settings.openai_base_url = "https://api.openai.com/v1"
            mock_settings.gemini_api_key = "test-key"

            from app.llm.client import stream_chat_completion

            meta: dict = {}
            async for _ in stream_chat_completion([{"role": "user", "content": "hi"}], metadata=meta):
                pass

            assert meta["finish_reason"] == "stop"

    @pytest.mark.asyncio
    async def test_openai_finish_reason_length(self):
        chunks = [
            'data: {"choices":[{"delta":{"content":"Hi"},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{},"finish_reason":"length"}]}',
            "data: [DONE]",
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

        with (
            patch("app.llm.client.httpx.AsyncClient", return_value=mock_client_ctx),
            patch("app.llm.client.settings") as mock_settings,
        ):
            mock_settings.llm_provider = "openai"
            mock_settings.openai_llm_model = "gpt-4"
            mock_settings.llm_temperature = 0.2
            mock_settings.llm_max_tokens = 4096
            mock_settings.llm_timeout = 60
            mock_settings.openai_base_url = "https://api.openai.com/v1"
            mock_settings.gemini_api_key = "test-key"

            from app.llm.client import stream_chat_completion

            meta: dict = {}
            async for _ in stream_chat_completion([{"role": "user", "content": "hi"}], metadata=meta):
                pass

            assert meta["finish_reason"] == "length"


class TestUsageExtraction:
    """Test that token usage data is extracted from LLM API responses."""

    @pytest.mark.asyncio
    async def test_openai_usage_from_stream(self):
        """Gemini/OpenAI returns usage in a separate SSE chunk with empty choices."""
        chunks = [
            'data: {"choices":[{"delta":{"content":"Hello"},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{"content":" world"},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
            'data: {"choices":[],"usage":{"prompt_tokens":150,"completion_tokens":25,"total_tokens":175}}',
            "data: [DONE]",
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

        with (
            patch("app.llm.client.httpx.AsyncClient", return_value=mock_client_ctx),
            patch("app.llm.client.settings") as mock_settings,
        ):
            mock_settings.llm_provider = "openai"
            mock_settings.openai_llm_model = "gemini-2.5-flash"
            mock_settings.llm_temperature = 0.2
            mock_settings.llm_max_tokens = 4096
            mock_settings.llm_timeout = 60
            mock_settings.openai_base_url = "https://generativelanguage.googleapis.com/v1beta/openai"
            mock_settings.gemini_api_key = "test-key"

            from app.llm.client import stream_chat_completion

            meta: dict = {}
            tokens = []
            async for token in stream_chat_completion([{"role": "user", "content": "hi"}], metadata=meta):
                tokens.append(token)

            assert tokens == ["Hello", " world"]
            assert "usage" in meta
            assert meta["usage"]["prompt_tokens"] == 150
            assert meta["usage"]["completion_tokens"] == 25
            assert meta["usage"]["total_tokens"] == 175

    @pytest.mark.asyncio
    async def test_openai_usage_fallback_when_no_usage_chunk(self):
        """When API doesn't return usage data, fallback to SSE chunk count."""
        chunks = [
            'data: {"choices":[{"delta":{"content":"Hi"},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
            "data: [DONE]",
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

        with (
            patch("app.llm.client.httpx.AsyncClient", return_value=mock_client_ctx),
            patch("app.llm.client.settings") as mock_settings,
        ):
            mock_settings.llm_provider = "openai"
            mock_settings.openai_llm_model = "gemini-2.5-flash"
            mock_settings.llm_temperature = 0.2
            mock_settings.llm_max_tokens = 4096
            mock_settings.llm_timeout = 60
            mock_settings.openai_base_url = "https://api.openai.com/v1"
            mock_settings.gemini_api_key = "test-key"

            from app.llm.client import stream_chat_completion

            meta: dict = {}
            async for _ in stream_chat_completion([{"role": "user", "content": "hi"}], metadata=meta):
                pass

            assert "usage" in meta
            assert meta["usage"]["prompt_tokens"] == 0
            assert meta["usage"]["completion_tokens"] == 1
            assert meta["usage"]["total_tokens"] == 1

    @pytest.mark.asyncio
    async def test_stream_options_include_usage_in_payload(self):
        """Verify that stream_options with include_usage is sent in the request payload."""
        chunks = [
            'data: {"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}]}',
            "data: [DONE]",
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

        with (
            patch("app.llm.client.httpx.AsyncClient", return_value=mock_client_ctx),
            patch("app.llm.client.settings") as mock_settings,
        ):
            mock_settings.llm_provider = "openai"
            mock_settings.openai_llm_model = "gemini-2.5-flash"
            mock_settings.llm_temperature = 0.2
            mock_settings.llm_max_tokens = 4096
            mock_settings.llm_timeout = 60
            mock_settings.openai_base_url = "https://api.openai.com/v1"
            mock_settings.gemini_api_key = "test-key"

            from app.llm.client import stream_chat_completion

            async for _ in stream_chat_completion([{"role": "user", "content": "hi"}]):
                pass

            call_args = mock_client.stream.call_args
            payload = call_args.kwargs.get("json") or call_args[1].get("json")
            assert payload["stream_options"] == {"include_usage": True}


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
