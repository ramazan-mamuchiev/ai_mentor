"""Gemini-based re-ranking for search results.

After the bi-encoder (vector search) retrieves candidate chunks, Gemini scores
each (query, chunk) pair for relevance.  This improves precision at the cost
of one LLM API call (~200-500ms for 20 candidates).

No local models or heavy dependencies (PyTorch, sentence-transformers) required.
"""

import json
import logging
import time

import httpx

from app.config import settings
from app.ingestion.text_cleaner import clean_for_embedding

logger = logging.getLogger(__name__)

RERANK_MODEL = "gemini-2.0-flash"

_RERANK_PROMPT = """\
You are a relevance scoring engine. Given a user query and a list of text chunks, \
rate each chunk's relevance to the query on a scale from 0.0 to 1.0.

Return ONLY a JSON array of numbers (floats) in the same order as the chunks. \
No explanation, no markdown, no extra text — just the JSON array.

Example output: [0.95, 0.3, 0.72, 0.1]

User query: {query}

Chunks:
{chunks}"""


def _build_rerank_text(result: dict) -> str:
    """Build cleaned, enriched text for scoring.

    1. Strip Markdown formatting — same as embedding pipeline
    2. Prepend heading_path for topic awareness
    """
    heading = result.get("heading_path", "")
    content = clean_for_embedding(result.get("content", ""))
    if heading:
        return f"[{heading}]\n{content}"
    return content


def _build_chunks_text(results: list[dict]) -> str:
    parts = []
    for i, r in enumerate(results):
        text = _build_rerank_text(r)
        # Limit each chunk to ~500 chars to fit within context
        if len(text) > 500:
            text = text[:500] + "..."
        parts.append(f"[{i}] {text}")
    return "\n\n".join(parts)


async def rerank(query: str, results: list[dict], top_k: int = 5) -> list[dict]:
    """Re-rank search results using Gemini API.

    Args:
        query: The user's search query.
        results: List of search result dicts (must have "content" key).
        top_k: Number of top results to return after re-ranking.

    Returns:
        Re-ranked list of results, trimmed to top_k.
    """
    if not results or len(results) <= 1:
        return results[:top_k]

    if not settings.gemini_api_key:
        logger.warning("Gemini API key not configured, skipping rerank")
        return results[:top_k]

    chunks_text = _build_chunks_text(results)
    prompt = _RERANK_PROMPT.format(query=query, chunks=chunks_text)

    url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.gemini_api_key}",
    }
    payload = {
        "model": settings.rerank_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": 256,
    }

    t0 = time.perf_counter()

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
            response = await client.post(url, json=payload, headers=headers)

        if response.status_code != 200:
            logger.warning(
                "Gemini rerank API error, falling back to original order",
                extra={"status": response.status_code, "body": response.text[:300]},
            )
            return results[:top_k]

        data = response.json()
        content = data["choices"][0]["message"]["content"].strip()

        # Parse JSON array from response (handle markdown code fences)
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        scores = json.loads(content)

        if not isinstance(scores, list) or len(scores) != len(results):
            logger.warning(
                "Gemini rerank returned unexpected format",
                extra={"expected": len(results), "got": len(scores) if isinstance(scores, list) else type(scores).__name__},
            )
            return results[:top_k]

    except (httpx.HTTPError, json.JSONDecodeError, KeyError, IndexError) as e:
        logger.warning(
            "Gemini rerank failed, falling back to original order",
            extra={"error": str(e)},
        )
        return results[:top_k]

    rerank_ms = round((time.perf_counter() - t0) * 1000, 1)

    scored = list(zip(results, scores))
    scored.sort(key=lambda x: float(x[1]), reverse=True)

    reranked: list[dict] = []
    for r, score in scored[:top_k]:
        r = dict(r)
        raw_score = float(score)
        r["rerank_score"] = round(raw_score, 4)
        r["similarity"] = round(raw_score, 4)
        reranked.append(r)

    logger.debug(
        "Gemini re-ranking completed",
        extra={
            "candidates": len(results),
            "top_k": top_k,
            "rerank_ms": rerank_ms,
            "top_rerank_score": reranked[0]["rerank_score"] if reranked else 0,
        },
    )
    return reranked
