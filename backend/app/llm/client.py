"""Ollama LLM client with streaming support."""

import json
import logging
import time
from collections.abc import AsyncGenerator

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


async def stream_chat_completion(
    messages: list[dict],
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> AsyncGenerator[str, None]:
    """Stream chat completion tokens from Ollama.

    Yields individual text chunks as they arrive.
    """
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
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "prompt_messages": len(messages),
        },
    )

    async with httpx.AsyncClient(timeout=httpx.Timeout(settings.llm_timeout, connect=10.0)) as client:
        async with client.stream("POST", url, json=payload) as response:
            if response.status_code != 200:
                body = await response.aread()
                duration_ms = round((time.perf_counter() - t0) * 1000, 1)
                logger.error(
                    "Ollama API error",
                    extra={
                        "status": response.status_code,
                        "body": body.decode()[:500],
                        "duration_ms": duration_ms,
                    },
                )
                raise RuntimeError(f"Ollama returned {response.status_code}")

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

    total_ms = round((time.perf_counter() - t0) * 1000, 1)
    tokens_per_sec = round(token_count / (total_ms / 1000), 1) if total_ms > 0 else 0

    logger.info(
        "LLM stream completed",
        extra={
            "model": model,
            "token_count": token_count,
            "duration_ms": total_ms,
            "first_token_ms": first_token_ms,
            "tokens_per_sec": tokens_per_sec,
        },
    )


async def check_health() -> bool:
    """Check if Ollama is reachable and the configured model is available."""
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
                logger.warning(
                    "Ollama model not found",
                    extra={"expected": settings.llm_model, "available": models},
                )
            return available
    except Exception as e:
        logger.warning("Ollama unreachable", extra={"error": str(e)})
        return False
