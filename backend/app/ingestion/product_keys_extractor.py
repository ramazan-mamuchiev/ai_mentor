"""LLM-based product search key generation and chunk entity aggregation."""

import json
import logging
import time
from dataclasses import dataclass, field

import httpx

from app.config import settings
from app.llm.http_client import gemini_client

logger = logging.getLogger(__name__)

_PRODUCT_KEYS_PROMPT = """\
You generate search keys for a product in a documentation system.
Users search by typing product names, abbreviations, transliterations,
manufacturer names, categories, slang, use cases — anything.

Product: "{name}"
Manufacturer: "{manufacturer}"
Model: "{model}"
Category: "{category}"

Generate ALL possible strings a user might type to find this product.
Think about:
- Name with/without spaces, hyphens
- Cyrillic transliterations
- Abbreviations
- Manufacturer variations (Cyrillic, shortened)
- Category terms in Russian and English
- Model/series references
- Use cases and related concepts
- Slang and informal names
- Partial names users might type

Return ONLY a JSON array of unique strings. 20-40 items.
Do NOT include protocols or technical terms from documentation — those are added separately.
"""


@dataclass
class ProductKeysUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model: str = ""
    extract_ms: float = 0.0


@dataclass
class ProductKeysResult:
    keys: list[str] = field(default_factory=list)
    usage: ProductKeysUsage = field(default_factory=ProductKeysUsage)


def aggregate_chunk_entities(chunk_meta_dicts: list[dict]) -> list[str]:
    """Collect unique keywords and protocols from chunk metadata (free, no LLM)."""
    seen: set[str] = set()
    keys: list[str] = []
    for meta in chunk_meta_dicts:
        entities = meta.get("entities", {})
        for field_name in ("keywords", "protocols"):
            for val in entities.get(field_name, []):
                normalized = val.strip().lower()
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    keys.append(val.strip())
    return keys


def _parse_keys_response(raw: str) -> list[str]:
    """Parse LLM JSON response into list of key strings."""
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:])
        if raw.endswith("```"):
            raw = raw[:-3].strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Failed to parse product keys JSON", extra={"raw": raw[:500]})
        return []

    if not isinstance(data, list):
        return []

    return [str(item).strip() for item in data if item and str(item).strip()]


def generate_product_keys_sync(
    name: str,
    manufacturer: str = "",
    model: str = "",
    category: str = "",
) -> ProductKeysResult:
    """Generate product search keys via Gemini Flash (synchronous, for Celery worker)."""
    if not settings.product_keys_extraction_enabled:
        return ProductKeysResult()

    prompt = _PRODUCT_KEYS_PROMPT.format(
        name=name, manufacturer=manufacturer, model=model, category=category,
    )
    url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": settings.product_resolve_model,
        "messages": [
            {"role": "system", "content": "You generate product search keys. Return only valid JSON."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": 1024,
        "reasoning_effort": "none",
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.gemini_api_key}",
    }

    t0 = time.perf_counter()
    try:
        with httpx.Client(timeout=httpx.Timeout(30.0, connect=5.0)) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        raw_text = data["choices"][0]["message"]["content"].strip()
        api_usage = data.get("usage", {})
        extract_ms = round((time.perf_counter() - t0) * 1000, 1)

        keys = _parse_keys_response(raw_text)

        usage = ProductKeysUsage(
            prompt_tokens=api_usage.get("prompt_tokens", 0),
            completion_tokens=api_usage.get("completion_tokens", 0),
            total_tokens=api_usage.get("total_tokens", 0),
            model=settings.product_resolve_model,
            extract_ms=extract_ms,
        )

        logger.info(
            "Product keys generated",
            extra={
                "product": name,
                "keys_count": len(keys),
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "extract_ms": extract_ms,
            },
        )
        return ProductKeysResult(keys=keys, usage=usage)

    except Exception:
        logger.warning("Product keys extraction failed", exc_info=True)
        return ProductKeysResult(
            usage=ProductKeysUsage(
                model=settings.product_resolve_model,
                extract_ms=round((time.perf_counter() - t0) * 1000, 1),
            )
        )


async def generate_product_keys_async(
    name: str,
    manufacturer: str = "",
    model: str = "",
    category: str = "",
) -> ProductKeysResult:
    """Generate product search keys via Gemini Flash (async, for FastAPI)."""
    if not settings.product_keys_extraction_enabled:
        return ProductKeysResult()

    prompt = _PRODUCT_KEYS_PROMPT.format(
        name=name, manufacturer=manufacturer, model=model, category=category,
    )
    url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": settings.product_resolve_model,
        "messages": [
            {"role": "system", "content": "You generate product search keys. Return only valid JSON."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": 1024,
        "reasoning_effort": "none",
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.gemini_api_key}",
    }

    t0 = time.perf_counter()
    try:
        resp = await gemini_client().post(url, json=payload, headers=headers, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()

        raw_text = data["choices"][0]["message"]["content"].strip()
        api_usage = data.get("usage", {})
        extract_ms = round((time.perf_counter() - t0) * 1000, 1)

        keys = _parse_keys_response(raw_text)

        usage = ProductKeysUsage(
            prompt_tokens=api_usage.get("prompt_tokens", 0),
            completion_tokens=api_usage.get("completion_tokens", 0),
            total_tokens=api_usage.get("total_tokens", 0),
            model=settings.product_resolve_model,
            extract_ms=extract_ms,
        )

        logger.info(
            "Product keys generated (async)",
            extra={
                "product": name,
                "keys_count": len(keys),
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "extract_ms": extract_ms,
            },
        )
        return ProductKeysResult(keys=keys, usage=usage)

    except Exception:
        logger.warning("Product keys extraction failed (async)", exc_info=True)
        return ProductKeysResult(
            usage=ProductKeysUsage(
                model=settings.product_resolve_model,
                extract_ms=round((time.perf_counter() - t0) * 1000, 1),
            )
        )
