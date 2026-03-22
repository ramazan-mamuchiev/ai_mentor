"""Cross-encoder re-ranking for search results.

After the bi-encoder (vector search) retrieves candidate chunks, a cross-encoder
scores each (query, chunk) pair more accurately.  This dramatically improves
precision at the cost of a small latency increase (~50-200ms for 20 candidates).

The chunk text is cleaned from Markdown artifacts and enriched with heading_path
before scoring, consistent with the embedding pipeline.
"""

import logging
import math
import time
from typing import TYPE_CHECKING

from app.config import settings
from app.ingestion.text_cleaner import clean_for_embedding

if TYPE_CHECKING:
    from sentence_transformers import CrossEncoder

logger = logging.getLogger(__name__)

_reranker: "CrossEncoder | None" = None

RERANK_MODEL = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"


def _get_reranker() -> "CrossEncoder":
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder

        t0 = time.perf_counter()
        logger.info("Loading cross-encoder reranker", extra={"model": RERANK_MODEL})
        _reranker = CrossEncoder(RERANK_MODEL)
        duration = round(time.perf_counter() - t0, 2)
        logger.info("Cross-encoder loaded", extra={"model": RERANK_MODEL, "duration_sec": duration})
    return _reranker


def _build_rerank_text(result: dict) -> str:
    """Build cleaned, enriched text for cross-encoder scoring.

    1. Strip Markdown formatting (bold, links, images, HTML) — same as embedding pipeline
    2. Prepend heading_path for topic awareness
    """
    heading = result.get("heading_path", "")
    content = clean_for_embedding(result.get("content", ""))
    if heading:
        return f"[{heading}]\n{content}"
    return content


def rerank(query: str, results: list[dict], top_k: int = 5) -> list[dict]:
    """Re-rank search results using a cross-encoder.

    Args:
        query: The user's search query.
        results: List of search result dicts (must have "content" key).
        top_k: Number of top results to return after re-ranking.

    Returns:
        Re-ranked list of results, trimmed to top_k.
    """
    if not results or len(results) <= 1:
        return results[:top_k]

    model = _get_reranker()

    pairs = [[query, _build_rerank_text(r)] for r in results]

    t0 = time.perf_counter()
    scores = model.predict(pairs)
    rerank_ms = round((time.perf_counter() - t0) * 1000, 1)

    scored = list(zip(results, scores))
    scored.sort(key=lambda x: float(x[1]), reverse=True)

    reranked: list[dict] = []
    for r, score in scored[:top_k]:
        r = dict(r)
        raw_score = float(score)
        r["rerank_score"] = round(raw_score, 4)
        r["similarity"] = round(1.0 / (1.0 + math.exp(-raw_score)), 4)
        reranked.append(r)

    logger.debug(
        "Re-ranking completed",
        extra={
            "candidates": len(results),
            "top_k": top_k,
            "rerank_ms": rerank_ms,
            "top_rerank_score": reranked[0]["rerank_score"] if reranked else 0,
        },
    )
    return reranked
