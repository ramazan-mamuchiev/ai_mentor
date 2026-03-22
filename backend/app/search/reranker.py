"""Gemini-based re-ranking for search results.

After the bi-encoder (vector search) retrieves candidate chunks, Gemini scores
each (query, chunk) pair for relevance.  This improves precision at the cost
of one LLM API call (~200-500ms for 20 candidates).

No local models or heavy dependencies (PyTorch, sentence-transformers) required.
"""

import json
import logging
import time
from dataclasses import dataclass, field

import httpx

from app.config import settings
from app.ingestion.text_cleaner import clean_for_embedding

logger = logging.getLogger(__name__)


@dataclass
class RerankUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model: str = ""
    rerank_ms: float = 0.0


@dataclass
class RerankResult:
    results: list[dict] = field(default_factory=list)
    usage: RerankUsage = field(default_factory=RerankUsage)


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
    heading = result.get("heading_path", "")
    content = clean_for_embedding(result.get("content", ""))
    if heading:
        return f"[{heading}]\n{content}"
    return content


def _build_chunks_text(results: list[dict]) -> str:
    parts = []
    for i, r in enumerate(results):
        text = _build_rerank_text(r)
        if len(text) > 500:
            text = text[:500] + "..."
        parts.append(f"[{i}] {text}")
    return "\n\n".join(parts)


async def rerank(query: str, results: list[dict], top_k: int = 5) -> RerankResult:
    """Re-rank search results using Gemini API.

    Returns RerankResult with re-ranked results and token usage stats.
    """
    empty_usage = RerankUsage(model=settings.rerank_model)

    if not results or len(results) <= 1:
        return RerankResult(results=results[:top_k], usage=empty_usage)

    if not settings.gemini_api_key:
        logger.warning("Gemini API key not configured, skipping rerank")
        return RerankResult(results=results[:top_k], usage=empty_usage)

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
        "stream_options": {"include_usage": True},
    }

    t0 = time.perf_counter()
    usage = RerankUsage(model=settings.rerank_model)

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
            response = await client.post(url, json=payload, headers=headers)

        if response.status_code != 200:
            logger.warning(
                "Gemini rerank API error, falling back to original order",
                extra={"status": response.status_code, "body": response.text[:300]},
            )
            return RerankResult(results=results[:top_k], usage=usage)

        data = response.json()

        api_usage = data.get("usage", {})
        usage.prompt_tokens = api_usage.get("prompt_tokens", 0)
        usage.completion_tokens = api_usage.get("completion_tokens", 0)
        usage.total_tokens = api_usage.get("total_tokens", 0)

        content = data["choices"][0]["message"]["content"].strip()

        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        scores = json.loads(content)

        if not isinstance(scores, list) or len(scores) != len(results):
            logger.warning(
                "Gemini rerank returned unexpected format",
                extra={"expected": len(results), "got": len(scores) if isinstance(scores, list) else type(scores).__name__},
            )
            return RerankResult(results=results[:top_k], usage=usage)

    except (httpx.HTTPError, json.JSONDecodeError, KeyError, IndexError) as e:
        logger.warning(
            "Gemini rerank failed, falling back to original order",
            extra={"error": str(e)},
        )
        return RerankResult(results=results[:top_k], usage=usage)

    usage.rerank_ms = round((time.perf_counter() - t0) * 1000, 1)

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
            "rerank_ms": usage.rerank_ms,
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "top_rerank_score": reranked[0]["rerank_score"] if reranked else 0,
        },
    )
    return RerankResult(results=reranked, usage=usage)
