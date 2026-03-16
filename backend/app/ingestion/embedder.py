"""Embedding abstraction: local (all-MiniLM-L6-v2) or OpenAI.

Local model produces 384-dim vectors, zero-padded to 1536 for pgvector
compatibility with future OpenAI embeddings.
"""

import logging
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

        logger.info("Loading local embedding model: %s", settings.embedding_model_local)
        _local_model = SentenceTransformer(settings.embedding_model_local)
        logger.info("Local embedding model loaded (dims=%d)", LOCAL_DIMS)
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

    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        vecs = model.encode(batch, normalize_embeddings=True, show_progress_bar=False)
        all_embeddings.append(vecs)

    combined = np.vstack(all_embeddings) if len(all_embeddings) > 1 else all_embeddings[0]
    padded = _zero_pad(combined, EMBEDDING_DIMS)
    return padded.tolist()


def _embed_openai(texts: list[str]) -> list[list[float]]:
    import openai

    client = openai.OpenAI(api_key=settings.openai_api_key)
    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        response = client.embeddings.create(model=settings.embedding_model_openai, input=batch)
        for item in response.data:
            all_embeddings.append(item.embedding)

    return all_embeddings


def embed_query(text: str) -> list[float]:
    """Embed a single query string. Returns 1536-dim vector."""
    results = embed_texts([text])
    return results[0]
