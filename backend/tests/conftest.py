"""Root conftest: shared helpers and fake embedding for all tests."""

import hashlib
import math


EMBEDDING_DIMS = 1536


def fake_embed_single(text: str) -> list[float]:
    """Generate a deterministic 1536-dim vector from text hash.

    Similar texts won't produce similar vectors (unlike real embeddings),
    but identical texts always produce identical vectors. This is sufficient
    for testing DB storage, retrieval, and cosine distance ordering when
    we control which vectors are "close" by using the same text.
    """
    h = hashlib.sha256(text.encode()).digest()
    raw = [float(b) / 255.0 for b in h]
    vec = (raw * (EMBEDDING_DIMS // len(raw) + 1))[:EMBEDDING_DIMS]
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        vec = [x / norm for x in vec]
    return vec


def fake_embed_texts(texts: list[str]) -> list[list[float]]:
    """Batch fake embedding — returns list of 1536-dim vectors."""
    if not texts:
        return []
    return [fake_embed_single(t) for t in texts]


def fake_embed_query(text: str) -> list[float]:
    """Single fake embedding — returns 1536-dim vector."""
    return fake_embed_single(text)
