"""Shared httpx clients with connection pooling for LLM API calls.

Eliminates per-request TCP/TLS handshake overhead (~30-50ms each) by reusing
persistent connections.  Two clients are maintained:

- ``gemini_client()`` — for OpenAI-compatible APIs (Gemini, GPT, etc.)
- ``ollama_client()`` — for local Ollama server

Per-request timeouts can be overridden via ``client.post(..., timeout=...)``.
"""

import httpx

from app.config import settings

_gemini: httpx.AsyncClient | None = None
_ollama: httpx.AsyncClient | None = None


def gemini_client() -> httpx.AsyncClient:
    """Return (or lazily create) the shared async client for Gemini/OpenAI API."""
    global _gemini
    if _gemini is None or _gemini.is_closed:
        _gemini = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=10.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    return _gemini


def ollama_client() -> httpx.AsyncClient:
    """Return (or lazily create) the shared async client for Ollama."""
    global _ollama
    if _ollama is None or _ollama.is_closed:
        _ollama = httpx.AsyncClient(
            timeout=httpx.Timeout(float(settings.llm_timeout), connect=10.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
    return _ollama


async def close_clients() -> None:
    """Gracefully close all shared clients (call on app shutdown)."""
    global _gemini, _ollama
    if _gemini and not _gemini.is_closed:
        await _gemini.aclose()
        _gemini = None
    if _ollama and not _ollama.is_closed:
        await _ollama.aclose()
        _ollama = None
