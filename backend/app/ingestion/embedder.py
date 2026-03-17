"""Embedding abstraction: local (all-MiniLM-L6-v2) or OpenAI.

Local model produces 384-dim vectors, zero-padded to 1536 for pgvector
compatibility with future OpenAI embeddings.
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

EMBEDDING_DIMS = settings.embedding_dims  # 1536
LOCAL_DIMS = 384
BATCH_SIZE = 256


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
        duration_sec = round(time.perf_counter() - t0, 2)
        logger.info(
            "Local embedding model loaded",
            extra={"model": settings.embedding_model_local, "dims": LOCAL_DIMS, "duration_sec": duration_sec},
        )
    return _local_model


def _zero_pad(vectors: np.ndarray, target_dims: int) -> np.ndarray:
    """Pad vectors with zeros to target dimensionality."""
    if vectors.shape[1] >= target_dims:
        return vectors[:, :target_dims]
    padding = np.zeros((vectors.shape[0], target_dims - vectors.shape[1]), dtype=vectors.dtype)
    return np.hstack([vectors, padding])


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts. Returns list of 1536-dim vectors."""
    if not texts:
        return []

    if settings.embedding_provider == "openai":
        return _embed_openai(texts)
    return _embed_local(texts)


def _embed_local(texts: list[str]) -> list[list[float]]:
    model = _get_local_model()
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
    padded = _zero_pad(combined, EMBEDDING_DIMS)

    logger.info(
        "Embedding completed",
        extra={"texts_count": len(texts), "provider": "local", "dims": EMBEDDING_DIMS},
    )
    return padded.tolist()


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
    """Embed a single query string. Returns 1536-dim vector."""
    results = embed_texts([text])
    return results[0]
