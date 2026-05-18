"""Embedding via Gemini API or BotHub (OpenAI-compatible).

Provider is chosen automatically based on settings.llm_provider:
  - "gemini"  -> Google genai SDK (models.embed_content)
  - "bothub"  -> OpenAI-compatible POST /embeddings via httpx

Both providers support custom output dimensionality.
"""

import logging
import time
from typing import TYPE_CHECKING, Callable

import numpy as np

from app.config import settings
from app.llm.credentials import embedding_credentials

if TYPE_CHECKING:
    from google.genai import Client as GenaiClient

logger = logging.getLogger(__name__)

_gemini_client: "GenaiClient | None" = None

EMBEDDING_DIMS = settings.embedding_dims
BATCH_SIZE = 100

_MAX_RETRIES = 5
_RETRY_BASE_DELAY = 2.0
_RETRY_MAX_DELAY = 120.0


def _embed_config(*, task_type: str, output_dimensionality: int):
    from google.genai import types

    return types.EmbedContentConfig(
        task_type=task_type,
        output_dimensionality=output_dimensionality,
    )


def _get_gemini_client() -> "GenaiClient":
    global _gemini_client
    if _gemini_client is None:
        from google import genai

        _gemini_client = genai.Client(api_key=settings.gemini_api_key)
        logger.info("Gemini embedding client initialized")
    return _gemini_client


def _embed_via_gemini(
    texts: list[str],
    *,
    is_query: bool = False,
    progress_callback: Callable[[float], None] | None = None,
) -> list[list[float]]:
    """Embed using Google genai SDK (Gemini-native)."""
    client = _get_gemini_client()
    task_type = "RETRIEVAL_QUERY" if is_query else "RETRIEVAL_DOCUMENT"
    target_dims = EMBEDDING_DIMS

    all_embeddings: list[np.ndarray] = []
    total_batches = (len(texts) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_idx, i in enumerate(range(0, len(texts), BATCH_SIZE)):
        batch = texts[i : i + BATCH_SIZE]

        for attempt in range(_MAX_RETRIES + 1):
            t0 = time.perf_counter()
            try:
                result = client.models.embed_content(
                    model=settings.embedding_model_gemini,
                    contents=batch,
                    config=_embed_config(task_type=task_type, output_dimensionality=target_dims),
                )
                break
            except Exception as exc:
                exc_str = str(exc)
                is_retryable = "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str or "503" in exc_str
                if not is_retryable or attempt == _MAX_RETRIES:
                    raise
                delay = min(_RETRY_BASE_DELAY * (2 ** attempt), _RETRY_MAX_DELAY)
                logger.warning(
                    "Gemini embedding retryable error, backing off",
                    extra={
                        "batch_index": batch_idx + 1, "attempt": attempt + 1,
                        "delay_s": delay, "error": exc_str[:300],
                    },
                )
                time.sleep(delay)

        batch_ms = round((time.perf_counter() - t0) * 1000, 1)
        raw = np.array([emb.values for emb in result.embeddings], dtype=np.float32)
        norms = np.linalg.norm(raw, axis=1, keepdims=True)
        norms = np.where(norms > 0, norms, 1.0)
        all_embeddings.append(raw / norms)

        _log_batch(batch_idx, total_batches, len(batch), batch_ms)
        if progress_callback is not None:
            progress_callback((batch_idx + 1) / total_batches)

    combined = np.vstack(all_embeddings) if len(all_embeddings) > 1 else all_embeddings[0]
    _log_done(texts, "gemini", settings.embedding_model_gemini, is_query)
    return combined.tolist()


def _embed_via_openai_compatible(
    texts: list[str],
    *,
    is_query: bool = False,
    progress_callback: Callable[[float], None] | None = None,
) -> list[list[float]]:
    """Embed using OpenAI-compatible /embeddings endpoint (BotHub, OpenRouter, etc.)."""
    import httpx

    api_key, base_url, model = embedding_credentials()
    url = f"{base_url.rstrip('/')}/embeddings"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    target_dims = EMBEDDING_DIMS

    all_embeddings: list[np.ndarray] = []
    total_batches = (len(texts) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_idx, i in enumerate(range(0, len(texts), BATCH_SIZE)):
        batch = texts[i : i + BATCH_SIZE]

        for attempt in range(_MAX_RETRIES + 1):
            t0 = time.perf_counter()
            try:
                with httpx.Client(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
                    payload = {
                        "model": model,
                        "input": batch,
                        "dimensions": target_dims,
                    }
                    resp = client.post(url, json=payload, headers=headers)

                    if resp.status_code != 200:
                        error_text = resp.text[:300]
                        is_retryable = resp.status_code in (429, 500, 503)
                        if not is_retryable or attempt == _MAX_RETRIES:
                            raise RuntimeError(
                                f"Embedding API returned {resp.status_code}: {error_text}"
                            )
                        delay = min(_RETRY_BASE_DELAY * (2 ** attempt), _RETRY_MAX_DELAY)
                        logger.warning(
                            "Embedding API retryable error, backing off",
                            extra={
                                "batch_index": batch_idx + 1, "attempt": attempt + 1,
                                "delay_s": delay, "status": resp.status_code,
                            },
                        )
                        time.sleep(delay)
                        continue

                    data = resp.json()
                    break
            except RuntimeError:
                raise
            except Exception as exc:
                if attempt == _MAX_RETRIES:
                    raise
                delay = min(_RETRY_BASE_DELAY * (2 ** attempt), _RETRY_MAX_DELAY)
                logger.warning(
                    "Embedding API error, backing off",
                    extra={
                        "batch_index": batch_idx + 1, "attempt": attempt + 1,
                        "delay_s": delay, "error": str(exc)[:300],
                    },
                )
                time.sleep(delay)

        batch_ms = round((time.perf_counter() - t0) * 1000, 1)

        sorted_items = sorted(data["data"], key=lambda x: x["index"])
        raw = np.array([item["embedding"] for item in sorted_items], dtype=np.float32)
        norms = np.linalg.norm(raw, axis=1, keepdims=True)
        norms = np.where(norms > 0, norms, 1.0)
        all_embeddings.append(raw / norms)

        _log_batch(batch_idx, total_batches, len(batch), batch_ms)
        if progress_callback is not None:
            progress_callback((batch_idx + 1) / total_batches)

    combined = np.vstack(all_embeddings) if len(all_embeddings) > 1 else all_embeddings[0]
    _, _, model_name = embedding_credentials()
    _log_done(texts, "openai-compatible", model_name, is_query)
    return combined.tolist()


def embed_texts(
    texts: list[str],
    *,
    is_query: bool = False,
    progress_callback: Callable[[float], None] | None = None,
) -> list[list[float]]:
    """Embed a list of texts via the configured provider. Returns list of EMBEDDING_DIMS-dim vectors."""
    if not texts:
        return []

    if settings.llm_provider == "gemini":
        return _embed_via_gemini(texts, is_query=is_query, progress_callback=progress_callback)
    return _embed_via_openai_compatible(texts, is_query=is_query, progress_callback=progress_callback)


def embed_query(text: str) -> list[float]:
    """Embed a single query string for search. Returns EMBEDDING_DIMS-dim vector."""
    results = embed_texts([text], is_query=True)
    return results[0]


def _log_batch(batch_idx: int, total_batches: int, count: int, batch_ms: float) -> None:
    log_extra = {
        "batch_index": batch_idx + 1, "total_batches": total_batches,
        "texts_count": count, "duration_ms": batch_ms,
    }
    if batch_ms > 30000:
        logger.warning("Embedding batch slow", extra=log_extra)
    else:
        logger.debug("Embedding batch completed", extra=log_extra)


def _log_done(texts: list[str], provider: str, model: str, is_query: bool) -> None:
    logger.info(
        "Embedding completed",
        extra={
            "texts_count": len(texts),
            "provider": provider,
            "model": model,
            "dims": EMBEDDING_DIMS,
            "task_type": "RETRIEVAL_QUERY" if is_query else "RETRIEVAL_DOCUMENT",
        },
    )
