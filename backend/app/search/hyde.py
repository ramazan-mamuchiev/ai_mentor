"""HyDE (Hypothetical Document Embedding) for improved retrieval.

Generates a hypothetical documentation paragraph that would answer the user's
query, then embeds *that* instead of the raw query. This bridges the gap
between "question language" and "documentation language" in embedding space.

Enabled per query_type via settings.hyde_query_types (default: code, technical, troubleshooting).
"""

import logging
import time

from app.config import settings
from app.llm.http_client import gemini_client

logger = logging.getLogger(__name__)

_HYDE_PROMPT = """\
You are a technical documentation writer. Given the user's question below, \
write a SHORT (2-4 sentences) technical documentation paragraph that would \
directly answer this question. Write in English. Include specific API paths, \
parameter names, code snippets, or configuration keys if relevant. \
Do NOT include any preamble, just the documentation paragraph.

Question: {query}"""


async def generate_hyde(query: str, query_type: str | None = None) -> tuple[str | None, dict]:
    """Generate a hypothetical document for the given query.

    Returns (hyde_text, usage_meta). Returns (None, meta) if HyDE is disabled
    or the query_type is not in the configured list.
    """
    if not settings.hyde_enabled:
        return None, {}

    allowed_types = {t.strip() for t in settings.hyde_query_types.split(",") if t.strip()}
    if query_type and query_type not in allowed_types:
        logger.debug("HyDE skipped: query_type=%s not in allowed types %s",
                      query_type, allowed_types)
        return None, {"hyde_skipped": f"query_type={query_type} not in allowed"}

    url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.gemini_api_key}",
    }
    payload = {
        "model": settings.hyde_model,
        "messages": [{"role": "user", "content": _HYDE_PROMPT.format(query=query)}],
        "temperature": 0.3,
        "max_tokens": settings.hyde_max_tokens,
    }

    try:
        t0 = time.perf_counter()
        resp = await gemini_client().post(url, json=payload, headers=headers, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()

        hyde_ms = round((time.perf_counter() - t0) * 1000, 1)

        hyde_text = data["choices"][0]["message"]["content"].strip()
        usage = data.get("usage", {})

        meta = {
            "hyde_model": settings.hyde_model,
            "hyde_ms": hyde_ms,
            "hyde_prompt_tokens": usage.get("prompt_tokens", 0),
            "hyde_completion_tokens": usage.get("completion_tokens", 0),
            "hyde_text_len": len(hyde_text),
        }

        logger.debug(
            "HyDE generated",
            extra={"query": query[:100], "hyde_len": len(hyde_text), "ms": hyde_ms},
        )

        return hyde_text, meta

    except Exception:
        logger.warning("HyDE generation failed, proceeding without it", exc_info=True)
        return None, {"hyde_error": "generation_failed"}
