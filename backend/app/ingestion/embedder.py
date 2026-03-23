"""Embedding via Gemini API.

Gemini models use task_type to distinguish queries from documents:
  - "RETRIEVAL_QUERY" for search queries
  - "RETRIEVAL_DOCUMENT" for document passages being indexed
"""

import logging
import time
from typing import TYPE_CHECKING

import numpy as np

from app.config import settings

if TYPE_CHECKING:
    from google.genai import Client as GenaiClient

logger = logging.getLogger(__name__)

_gemini_client: "GenaiClient | None" = None

EMBEDDING_DIMS = settings.embedding_dims
# Gemini BatchEmbedContents API allows at most 100 items per request
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


def embed_texts(texts: list[str], *, is_query: bool = False) -> list[list[float]]:
    """Embed a list of texts via Gemini API. Returns list of EMBEDDING_DIMS-dim vectors."""
    if not texts:
        return []

    client = _get_gemini_client()
    task_type = "RETRIEVAL_QUERY" if is_query else "RETRIEVAL_DOCUMENT"
    target_dims = EMBEDDING_DIMS

    all_embeddings: list[np.ndarray] = []
    total_batches = (len(texts) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_idx, i in enumerate(range(0, len(texts), BATCH_SIZE)):
        batch = texts[i : i + BATCH_SIZE]
        t0 = time.perf_counter()
        result = client.models.embed_content(
            model=settings.embedding_model_gemini,
            contents=batch,
            config=_embed_config(task_type=task_type, output_dimensionality=target_dims),
        )
        batch_ms = round((time.perf_counter() - t0) * 1000, 1)

        raw = np.array([emb.values for emb in result.embeddings], dtype=np.float32)
        norms = np.linalg.norm(raw, axis=1, keepdims=True)
        norms = np.where(norms > 0, norms, 1.0)
        all_embeddings.append(raw / norms)

        log_extra = {
            "batch_index": batch_idx + 1, "total_batches": total_batches,
            "texts_count": len(batch), "duration_ms": batch_ms,
        }
        if batch_ms > 30000:
            logger.warning("Gemini embedding batch slow", extra=log_extra)
        else:
            logger.debug("Gemini embedding batch completed", extra=log_extra)

    combined = np.vstack(all_embeddings) if len(all_embeddings) > 1 else all_embeddings[0]

    logger.info(
        "Embedding completed",
        extra={
            "texts_count": len(texts),
            "provider": "gemini",
            "model": settings.embedding_model_gemini,
            "dims": target_dims,
            "task_type": task_type,
        },
    )
    return combined.tolist()


def embed_query(text: str) -> list[float]:
    """Embed a single query string for search. Returns EMBEDDING_DIMS-dim vector."""
    results = embed_texts([text], is_query=True)
    return results[0]
