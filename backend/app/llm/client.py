"""LLM client with streaming support for multiple providers.

Supported providers:
  - "ollama"  — local Ollama server (default)
  - "openai"  — any OpenAI-compatible API (Gemini, GPT-4o, OpenRouter, etc.)
"""

import json
import logging
import time
from collections.abc import AsyncGenerator

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Typed LLM error with machine-readable error_code for the frontend."""

    def __init__(self, status_code: int, error_code: str, detail: str):
        self.status_code = status_code
        self.error_code = error_code
        self.detail = detail
        super().__init__(detail)


def _error_code_from_status(status_code: int) -> str:
    if status_code == 401 or status_code == 403:
        return "auth_failed"
    if status_code == 404:
        return "model_not_found"
    if status_code == 429:
        return "rate_limited"
    if status_code >= 500:
        return "server_error"
    return "bad_request"


def _effective_model() -> str:
    if settings.llm_provider == "openai":
        return settings.openai_llm_model
    return settings.llm_model


async def stream_chat_completion(
    messages: list[dict],
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> AsyncGenerator[str, None]:
    """Stream chat completion tokens from the configured LLM provider."""
    if settings.llm_provider == "openai":
        async for token in _stream_openai_compatible(messages, model, temperature, max_tokens):
            yield token
    else:
        async for token in _stream_ollama(messages, model, temperature, max_tokens):
            yield token


async def _stream_ollama(
    messages: list[dict],
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> AsyncGenerator[str, None]:
    """Stream from local Ollama server."""
    model = model or settings.llm_model
    temperature = temperature if temperature is not None else settings.llm_temperature
    max_tokens = max_tokens or settings.llm_max_tokens

    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }

    url = f"{settings.ollama_url}/api/chat"
    t0 = time.perf_counter()
    token_count = 0
    first_token_ms = 0.0

    logger.info(
        "LLM stream starting",
        extra={
            "provider": "ollama",
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "prompt_messages": len(messages),
        },
    )

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.llm_timeout, connect=10.0)) as client:
            async with client.stream("POST", url, json=payload) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    duration_ms = round((time.perf_counter() - t0) * 1000, 1)
                    logger.error(
                        "Ollama API error",
                        extra={"status": response.status_code, "body": body.decode()[:500], "duration_ms": duration_ms},
                    )
                    raise LLMError(
                        response.status_code,
                        _error_code_from_status(response.status_code),
                        f"Ollama returned {response.status_code}",
                    )

                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if data.get("done"):
                        break

                    content = data.get("message", {}).get("content", "")
                    if content:
                        token_count += 1
                        if token_count == 1:
                            first_token_ms = round((time.perf_counter() - t0) * 1000, 1)
                        yield content
    except LLMError:
        raise
    except httpx.ConnectError as e:
        raise LLMError(0, "unreachable", f"Ollama unreachable: {e}") from e
    except httpx.TimeoutException as e:
        raise LLMError(0, "timeout", f"Ollama timeout: {e}") from e

    _log_completion("ollama", model, token_count, t0, first_token_ms)


async def _stream_openai_compatible(
    messages: list[dict],
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> AsyncGenerator[str, None]:
    """Stream from any OpenAI-compatible API (Gemini, GPT-4o, OpenRouter, etc.)."""
    model = model or settings.openai_llm_model
    temperature = temperature if temperature is not None else settings.llm_temperature
    max_tokens = max_tokens or settings.llm_max_tokens

    payload: dict = {
        "model": model,
        "messages": messages,
        "stream": True,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.openai_llm_api_key}",
    }

    t0 = time.perf_counter()
    token_count = 0
    first_token_ms = 0.0

    logger.info(
        "LLM stream starting",
        extra={
            "provider": "openai-compatible",
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "prompt_messages": len(messages),
            "base_url": settings.openai_base_url,
        },
    )

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.llm_timeout, connect=15.0)) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    duration_ms = round((time.perf_counter() - t0) * 1000, 1)
                    logger.error(
                        "OpenAI-compatible API error",
                        extra={"status": response.status_code, "body": body.decode()[:500], "duration_ms": duration_ms},
                    )
                    raise LLMError(
                        response.status_code,
                        _error_code_from_status(response.status_code),
                        f"LLM API returned {response.status_code}: {body.decode()[:200]}",
                    )

                async for line in response.aiter_lines():
                    stripped = line.strip()
                    if not stripped or not stripped.startswith("data: "):
                        continue
                    data_str = stripped[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    choices = data.get("choices", [])
                    if not choices:
                        continue
                    delta = choices[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        token_count += 1
                        if token_count == 1:
                            first_token_ms = round((time.perf_counter() - t0) * 1000, 1)
                        yield content
    except LLMError:
        raise
    except httpx.ConnectError as e:
        raise LLMError(0, "unreachable", f"LLM API unreachable: {e}") from e
    except httpx.TimeoutException as e:
        raise LLMError(0, "timeout", f"LLM API timeout: {e}") from e

    _log_completion("openai-compatible", model, token_count, t0, first_token_ms)


def _log_completion(provider: str, model: str, token_count: int, t0: float, first_token_ms: float) -> None:
    total_ms = round((time.perf_counter() - t0) * 1000, 1)
    tokens_per_sec = round(token_count / (total_ms / 1000), 1) if total_ms > 0 else 0
    logger.info(
        "LLM stream completed",
        extra={
            "provider": provider,
            "model": model,
            "token_count": token_count,
            "duration_ms": total_ms,
            "first_token_ms": first_token_ms,
            "tokens_per_sec": tokens_per_sec,
        },
    )


async def check_health() -> bool:
    """Check if the configured LLM provider is reachable."""
    if settings.llm_provider == "openai":
        return await _check_health_openai()
    return await _check_health_ollama()


async def _check_health_ollama() -> bool:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.ollama_url}/api/tags")
            if resp.status_code != 200:
                logger.warning("Ollama health check failed", extra={"status": resp.status_code})
                return False
            data = resp.json()
            models = [m.get("name", "") for m in data.get("models", [])]
            available = any(settings.llm_model in m for m in models)
            if not available:
                logger.warning("Ollama model not found", extra={"expected": settings.llm_model, "available": models})
            return available
    except Exception as e:
        logger.warning("Ollama unreachable", extra={"error": str(e)})
        return False


async def _check_health_openai() -> bool:
    if not settings.openai_llm_api_key:
        logger.warning("OpenAI-compatible API key not configured")
        return False
    try:
        url = f"{settings.openai_base_url.rstrip('/')}/models"
        headers = {"Authorization": f"Bearer {settings.openai_llm_api_key}"}
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                return True
            logger.warning("OpenAI-compatible health check failed", extra={"status": resp.status_code})
            return resp.status_code < 500
    except Exception as e:
        logger.warning("OpenAI-compatible API unreachable", extra={"error": str(e)})
        return False
