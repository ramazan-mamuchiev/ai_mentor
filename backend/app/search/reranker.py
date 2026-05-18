"""Gemini-based re-ranking for search results.

After the bi-encoder (vector search) retrieves candidate chunks, Gemini scores
each (query, chunk) pair for relevance.  This improves precision at the cost
of one LLM API call (~200-500ms for 20 candidates).

No local models or heavy dependencies (PyTorch, sentence-transformers) required.
"""

import json
import logging
import re
import time
from dataclasses import dataclass, field

import httpx

from app.config import settings
from app.llm.credentials import llm_credentials
from app.llm.http_client import gemini_client
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

Scoring guidelines:
- 0.8-1.0: Chunk directly answers the query or contains the exact information requested.
- 0.5-0.7: Chunk is partially relevant — covers a related topic or contains useful context.
- 0.2-0.4: Chunk is tangentially related — same domain but does not address the query.
- 0.0-0.1: Chunk is irrelevant to the query.

When the query is a "how-to" or conceptual question, prefer chunks from guides and overviews \
(type: user_guide, overview, troubleshooting) over raw API/protocol references \
(type: api_reference, protocol, model_schema). \
A guide that explains the data flow is more useful than a bare RPC signature.

Score based on the chunk's language-independent meaning. A Russian query can match English docs and vice versa.

Return ONLY a JSON array of numbers (floats) in the same order as the chunks. \
No explanation, no markdown fences, no extra text — just the raw JSON array.

Example output: [0.95, 0.3, 0.72, 0.1]

User query: {query}

Chunks:
{chunks}"""


def _build_rerank_text(result: dict) -> str:
    heading = result.get("heading_path", "")
    content = clean_for_embedding(result.get("content", ""))
    meta_parts: list[str] = []
    if heading:
        meta_parts.append(f"[{heading}]")
    doc_type = result.get("doc_type")
    if doc_type and doc_type != "other":
        meta_parts.append(f"[type: {doc_type}]")
    product = result.get("product_name")
    if product:
        meta_parts.append(f"[product: {product}]")
    prefix = " ".join(meta_parts)
    if prefix:
        return f"{prefix}\n{content}"
    return content


def _build_chunks_text(results: list[dict]) -> str:
    parts = []
    for i, r in enumerate(results):
        text = _build_rerank_text(r)
        if len(text) > 1000:
            text = text[:1000] + "..."
        parts.append(f"[{i}] {text}")
    return "\n\n".join(parts)


_MAX_RERANK_ATTEMPTS = 2

_FLOAT_RE = re.compile(r"[\d]+\.?[\d]*")


def _parse_scores(content: str, expected_count: int) -> list[float] | None:
    """Parse rerank scores from LLM output, tolerating formatting quirks."""
    try:
        scores = json.loads(content)
        if isinstance(scores, list) and len(scores) == expected_count:
            return [float(s) for s in scores]
    except (json.JSONDecodeError, ValueError):
        pass

    numbers = _FLOAT_RE.findall(content)
    if len(numbers) == expected_count:
        try:
            return [min(max(float(n), 0.0), 1.0) for n in numbers]
        except ValueError:
            pass

    logger.warning(
        "Gemini rerank returned unparseable format",
        extra={"expected": expected_count, "extracted": len(numbers), "raw": content[:200]},
    )
    return None


async def _call_rerank_api(
    prompt: str,
    expected_count: int,
    usage: RerankUsage,
) -> list[float] | None:
    """Single API call to get rerank scores. Returns scores list or None on failure."""
    api_key, base_url = llm_credentials()
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": settings.rerank_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": 256,
        "stream_options": {"include_usage": True},
    }

    try:
        response = await gemini_client().post(url, json=payload, headers=headers, timeout=30.0)

        if response.status_code != 200:
            logger.warning(
                "Gemini rerank API error",
                extra={"status": response.status_code, "body": response.text[:300]},
            )
            return None

        data = response.json()

        api_usage = data.get("usage", {})
        usage.prompt_tokens += api_usage.get("prompt_tokens", 0)
        usage.completion_tokens += api_usage.get("completion_tokens", 0)
        usage.total_tokens += api_usage.get("total_tokens", 0)

        content = data["choices"][0]["message"]["content"].strip()

        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        scores = _parse_scores(content, expected_count)
        if scores is None:
            return None

        return scores

    except (httpx.HTTPError, json.JSONDecodeError, KeyError, IndexError, ValueError) as e:
        logger.warning("Gemini rerank call failed", extra={"error": str(e)})
        return None


async def rerank(query: str, results: list[dict], top_k: int = 5) -> RerankResult:
    """Re-rank search results using Gemini API with retry on parse failure.

    Returns RerankResult with re-ranked results and token usage stats.
    """
    empty_usage = RerankUsage(model=settings.rerank_model)

    if not results or len(results) <= 1:
        return RerankResult(results=results[:top_k], usage=empty_usage)

    api_key, _ = llm_credentials()
    if not api_key:
        logger.warning("LLM API key not configured, skipping rerank")
        return RerankResult(results=results[:top_k], usage=empty_usage)

    chunks_text = _build_chunks_text(results)
    prompt = _RERANK_PROMPT.format(query=query, chunks=chunks_text)

    t0 = time.perf_counter()
    usage = RerankUsage(model=settings.rerank_model)
    scores: list[float] | None = None

    for attempt in range(_MAX_RERANK_ATTEMPTS):
        scores = await _call_rerank_api(prompt, len(results), usage)
        if scores is not None:
            break
        if attempt < _MAX_RERANK_ATTEMPTS - 1:
            logger.warning("Retrying rerank after parse failure", extra={"attempt": attempt + 1})

    if scores is None:
        logger.warning("Gemini rerank failed after retries, falling back to original order")
        usage.rerank_ms = round((time.perf_counter() - t0) * 1000, 1)
        return RerankResult(results=results[:top_k], usage=usage)

    usage.rerank_ms = round((time.perf_counter() - t0) * 1000, 1)

    scored = list(zip(results, scores))
    scored.sort(key=lambda x: x[1], reverse=True)

    reranked: list[dict] = []
    for r, score in scored[:top_k]:
        r = dict(r)
        r["rerank_score"] = round(score, 4)
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
