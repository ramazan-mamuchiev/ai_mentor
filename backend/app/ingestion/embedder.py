"""Embedding abstraction: local (multilingual-e5-large) or OpenAI.

E5 models require prefix instructions:
  - "query: " for search queries
  - "passage: " for document passages being indexed
The model produces 1024-dim vectors natively.
"""

import logging
import time
from typing import TYPE_CHECKING

import numpy as np

from app.config import settings

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

_local_model: "SentenceTransformer | None" = None

EMBEDDING_DIMS = settings.embedding_dims
BATCH_SIZE = 256

E5_MODEL_PREFIXES = {"intfloat/multilingual-e5-large", "intfloat/multilingual-e5-base", "intfloat/multilingual-e5-small"}


def _is_e5_model() -> bool:
    return settings.embedding_model_local in E5_MODEL_PREFIXES


def _get_local_model() -> "SentenceTransformer":
    global _local_model
    if _local_model is None:
        from sentence_transformers import SentenceTransformer

        t0 = time.perf_counter()
        logger.info(
            "Loading local embedding model",
            extra={"model": settings.embedding_model_local},
        )
        _local_model = SentenceTransformer(settings.embedding_model_local)
        native_dims = _local_model.get_sentence_embedding_dimension()
        duration_sec = round(time.perf_counter() - t0, 2)
        logger.info(
            "Local embedding model loaded",
            extra={
                "model": settings.embedding_model_local,
                "native_dims": native_dims,
                "target_dims": EMBEDDING_DIMS,
                "is_e5": _is_e5_model(),
                "duration_sec": duration_sec,
            },
        )
    return _local_model


def _adjust_dims(vectors: np.ndarray, target_dims: int) -> np.ndarray:
    """Pad or truncate vectors to target dimensionality."""
    if vectors.shape[1] == target_dims:
        return vectors
    if vectors.shape[1] > target_dims:
        return vectors[:, :target_dims]
    padding = np.zeros((vectors.shape[0], target_dims - vectors.shape[1]), dtype=vectors.dtype)
    return np.hstack([vectors, padding])


def embed_texts(texts: list[str], *, is_query: bool = False) -> list[list[float]]:
    """Embed a list of texts. Returns list of EMBEDDING_DIMS-dim vectors.

    Args:
        texts: Raw text strings to embed.
        is_query: If True, adds "query: " prefix (for search).
                  If False, adds "passage: " prefix (for indexing).
                  Prefixes only applied for E5 models.
    """
    if not texts:
        return []

    if settings.embedding_provider == "openai":
        return _embed_openai(texts)
    return _embed_local(texts, is_query=is_query)


def _embed_local(texts: list[str], *, is_query: bool = False) -> list[list[float]]:
    model = _get_local_model()

    if _is_e5_model():
        prefix = "query: " if is_query else "passage: "
        texts = [prefix + t for t in texts]

    all_embeddings: list[np.ndarray] = []
    total_batches = (len(texts) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_idx, i in enumerate(range(0, len(texts), BATCH_SIZE)):
        batch = texts[i : i + BATCH_SIZE]
        t0 = time.perf_counter()
        vecs = model.encode(batch, normalize_embeddings=True, show_progress_bar=False)
        batch_ms = round((time.perf_counter() - t0) * 1000, 1)
        all_embeddings.append(vecs)

        log_extra = {
            "batch_index": batch_idx + 1, "total_batches": total_batches,
            "texts_count": len(batch), "duration_ms": batch_ms,
        }
        if batch_ms > 30000:
            logger.warning("Embedding batch slow", extra=log_extra)
        else:
            logger.debug("Embedding batch completed", extra=log_extra)

    combined = np.vstack(all_embeddings) if len(all_embeddings) > 1 else all_embeddings[0]
    adjusted = _adjust_dims(combined, EMBEDDING_DIMS)

    logger.info(
        "Embedding completed",
        extra={
            "texts_count": len(texts),
            "provider": "local",
            "dims": EMBEDDING_DIMS,
            "is_query": is_query,
            "is_e5": _is_e5_model(),
        },
    )
    return adjusted.tolist()


def _embed_openai(texts: list[str]) -> list[list[float]]:
    import openai

    client = openai.OpenAI(api_key=settings.openai_api_key)
    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        t0 = time.perf_counter()
        response = client.embeddings.create(model=settings.embedding_model_openai, input=batch)
        batch_ms = round((time.perf_counter() - t0) * 1000, 1)
        for item in response.data:
            all_embeddings.append(item.embedding)

        logger.debug(
            "OpenAI embedding batch completed",
            extra={"texts_count": len(batch), "duration_ms": batch_ms},
        )

    logger.info(
        "Embedding completed",
        extra={"texts_count": len(texts), "provider": "openai", "dims": EMBEDDING_DIMS},
    )
    return all_embeddings


def embed_query(text: str) -> list[float]:
    """Embed a single query string for search. Returns EMBEDDING_DIMS-dim vector."""
    results = embed_texts([text], is_query=True)
    return results[0]
