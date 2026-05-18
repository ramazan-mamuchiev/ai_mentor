"""Embedding via Gemini API or BotHub (OpenAI-compatible).

Provider is chosen automatically based on settings.llm_provider:
  - "gemini"  -> Google genai SDK (models.embed_content)
  - "bothub"  -> OpenAI-compatible POST /embeddings via httpx

Both providers support custom output dimensionality.
"""

import hashlib
import json
import logging
import time
from typing import TYPE_CHECKING, Callable

import numpy as np

from app.config import settings
from app.llm.credentials import embedding_credentials
from app.utils.retry import retry_call

if TYPE_CHECKING:
    from google.genai import Client as GenaiClient

logger = logging.getLogger(__name__)

_gemini_client: "GenaiClient | None" = None

EMBEDDING_DIMS = settings.embedding_dims
BATCH_SIZE = 100



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
) -> tuple[list[list[float]], int]:
    """Embed a list of texts via Gemini API.

    Returns (list_of_vectors, total_api_tokens).

    Args:
        progress_callback: optional fn(fraction) called after each batch, fraction in [0..1].
    """
    if not texts:
        return [], 0

    texts = [t if t and t.strip() else " " for t in texts]

    client = _get_gemini_client()
    task_type = "RETRIEVAL_QUERY" if is_query else "RETRIEVAL_DOCUMENT"
    target_dims = EMBEDDING_DIMS

    all_embeddings: list[np.ndarray] = []
    total_api_tokens = 0
    total_batches = (len(texts) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_idx, i in enumerate(range(0, len(texts), BATCH_SIZE)):
        batch = texts[i : i + BATCH_SIZE]

        def _is_retryable(exc: Exception) -> bool:
            s = str(exc)
            return "429" in s or "RESOURCE_EXHAUSTED" in s or "503" in s

        t0 = time.perf_counter()
        result = retry_call(
            lambda: client.models.embed_content(
                model=settings.embedding_model_gemini,
                contents=batch,
                config=_embed_config(task_type=task_type, output_dimensionality=target_dims),
            ),
            max_retries=5,
            base_delay=2.0,
            max_delay=120.0,
            is_retryable=_is_retryable,
            label=f"embed_batch_{batch_idx + 1}",
        )

        batch_ms = round((time.perf_counter() - t0) * 1000, 1)

        raw = np.array([emb.values for emb in result.embeddings], dtype=np.float32)
        norms = np.linalg.norm(raw, axis=1, keepdims=True)
        norms = np.where(norms > 0, norms, 1.0)
        all_embeddings.append(raw / norms)

        for emb in result.embeddings:
            stats = getattr(emb, "statistics", None)
            if stats:
                total_api_tokens += getattr(stats, "token_count", 0) or 0

        log_extra = {
            "batch_index": batch_idx + 1, "total_batches": total_batches,
            "texts_count": len(batch), "duration_ms": batch_ms,
        }
        if batch_ms > 30000:
            logger.warning("Gemini embedding batch slow", extra=log_extra)
        else:
            logger.debug("Gemini embedding batch completed", extra=log_extra)

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
_sync_redis = None


def _get_sync_redis():
    global _sync_redis
    if _sync_redis is None:
        import redis as redis_lib
        _sync_redis = redis_lib.from_url(settings.redis_url, socket_connect_timeout=2, decode_responses=True)
    return _sync_redis

    if settings.llm_provider == "gemini":
        return _embed_via_gemini(texts, is_query=is_query, progress_callback=progress_callback)
    return _embed_via_openai_compatible(texts, is_query=is_query, progress_callback=progress_callback)


def _embedding_cache_key(text: str) -> str:
    h = hashlib.sha256(text.encode()).hexdigest()
    return f"emb:q:{settings.embedding_model_gemini}:{settings.embedding_dims}:{h}"


def embed_query(text: str) -> tuple[list[float], int]:
    """Embed a single query string for search. Returns (vector, api_tokens).

    When embedding_cache_enabled, caches query vectors in Redis to avoid
    repeated Gemini API calls for the same query text.
    """
    if settings.embedding_cache_enabled:
        try:
            r = _get_sync_redis()
            key = _embedding_cache_key(text)
            cached = r.get(key)
            if cached:
                logger.debug("Embedding cache hit", extra={"key": key[:60]})
                return json.loads(cached), 0
        except Exception:
            logger.debug("Embedding cache read failed", exc_info=True)

    results, api_tokens = embed_texts([text], is_query=True)
    vec = results[0]

    if settings.embedding_cache_enabled:
        try:
            r = _get_sync_redis()
            key = _embedding_cache_key(text)
            r.setex(key, settings.embedding_cache_ttl_hours * 3600, json.dumps(vec))
        except Exception:
            logger.debug("Embedding cache write failed", exc_info=True)
            
    return vec, api_tokens


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

