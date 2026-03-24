"""LLM-based metadata extraction for chunks: doc_type and structured entities."""

import json
import logging
import time
from dataclasses import dataclass, field

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

DOC_TYPES = [
    "api_reference",
    "user_guide",
    "configuration",
    "changelog",
    "release_notes",
    "troubleshooting",
    "protocol",
    "model_schema",
    "overview",
    "other",
]

_EXTRACTION_PROMPT = (
    "You are a metadata extraction engine. For each numbered text chunk below, extract:\n"
    "1. doc_type: exactly one of: " + ", ".join(DOC_TYPES) + "\n"
    "2. entities: an object with these keys (each value is an array of strings, empty array if none found):\n"
    "   - api_endpoints: HTTP endpoints like 'GET /api/v1/users'\n"
    "   - config_params: configuration parameter names\n"
    "   - error_codes: error codes or error identifiers\n"
    "   - protocols: protocol names (HTTP, RTSP, ONVIF, gRPC, etc.)\n"
    "   - keywords: 3-7 most important domain-specific terms\n\n"
    "Return ONLY a JSON array with one object per chunk, in order. "
    "Each object must have exactly two keys: \"doc_type\" and \"entities\".\n"
    "Do NOT include any text outside the JSON array."
)


@dataclass
class ChunkMetadata:
    doc_type: str = "other"
    entities: dict = field(default_factory=dict)


@dataclass
class ExtractionUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model: str = ""
    extract_ms: float = 0.0
    batches: int = 0


@dataclass
class ExtractionResult:
    metadata: list[ChunkMetadata] = field(default_factory=list)
    usage: ExtractionUsage = field(default_factory=ExtractionUsage)


def _default_metadata() -> ChunkMetadata:
    return ChunkMetadata(
        doc_type="other",
        entities={
            "api_endpoints": [],
            "config_params": [],
            "error_codes": [],
            "protocols": [],
            "keywords": [],
        },
    )


def _build_batch_prompt(texts: list[str]) -> str:
    parts = [_EXTRACTION_PROMPT, ""]
    for i, text in enumerate(texts, 1):
        preview = text[:1500] if len(text) > 1500 else text
        parts.append(f"--- Chunk {i} ---")
        parts.append(preview)
        parts.append("")
    return "\n".join(parts)


def _parse_response(raw: str, expected_count: int) -> list[ChunkMetadata]:
    """Parse LLM JSON response into ChunkMetadata list with validation."""
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:])
        if raw.endswith("```"):
            raw = raw[:-3].strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Failed to parse extraction JSON", extra={"raw": raw[:500]})
        return [_default_metadata() for _ in range(expected_count)]

    if not isinstance(data, list):
        data = [data]

    results: list[ChunkMetadata] = []
    for i in range(expected_count):
        if i < len(data) and isinstance(data[i], dict):
            item = data[i]
            doc_type = item.get("doc_type", "other")
            if doc_type not in DOC_TYPES:
                doc_type = "other"

            entities = item.get("entities", {})
            if not isinstance(entities, dict):
                entities = {}

            clean_entities: dict[str, list[str]] = {}
            for key in ("api_endpoints", "config_params", "error_codes", "protocols", "keywords"):
                val = entities.get(key, [])
                if isinstance(val, list):
                    clean_entities[key] = [str(v) for v in val if v]
                else:
                    clean_entities[key] = []

            results.append(ChunkMetadata(doc_type=doc_type, entities=clean_entities))
        else:
            results.append(_default_metadata())

    return results


def _call_llm_sync(prompt: str) -> tuple[str, dict]:
    """Synchronous LLM call for use in Celery worker. Returns (response_text, usage_dict)."""
    url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": settings.metadata_extraction_model,
        "messages": [
            {"role": "system", "content": "You extract structured metadata from text chunks. Return only valid JSON."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": 2048,
        "reasoning_effort": "none",
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.gemini_api_key}",
    }

    with httpx.Client(timeout=httpx.Timeout(30.0, connect=5.0)) as client:
        resp = client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    text = data["choices"][0]["message"]["content"].strip()
    usage = data.get("usage", {})
    return text, usage


async def _call_llm_async(prompt: str) -> tuple[str, dict]:
    """Async LLM call for use in FastAPI endpoints."""
    url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": settings.metadata_extraction_model,
        "messages": [
            {"role": "system", "content": "You extract structured metadata from text chunks. Return only valid JSON."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": 2048,
        "reasoning_effort": "none",
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.gemini_api_key}",
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0)) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    text = data["choices"][0]["message"]["content"].strip()
    usage = data.get("usage", {})
    return text, usage


def extract_metadata_batch_sync(chunk_texts: list[str]) -> ExtractionResult:
    """Extract metadata from chunks synchronously (for Celery worker).

    Splits chunks into batches, calls LLM for each batch, and aggregates results.
    """
    if not settings.metadata_extraction_enabled or not chunk_texts:
        return ExtractionResult(
            metadata=[_default_metadata() for _ in chunk_texts],
            usage=ExtractionUsage(model=settings.metadata_extraction_model),
        )

    t0 = time.perf_counter()
    batch_size = settings.metadata_extraction_batch_size
    all_metadata: list[ChunkMetadata] = []
    total_usage = ExtractionUsage(model=settings.metadata_extraction_model)

    for start in range(0, len(chunk_texts), batch_size):
        batch = chunk_texts[start : start + batch_size]
        prompt = _build_batch_prompt(batch)

        try:
            raw_response, usage = _call_llm_sync(prompt)
            batch_meta = _parse_response(raw_response, len(batch))

            total_usage.prompt_tokens += usage.get("prompt_tokens", 0)
            total_usage.completion_tokens += usage.get("completion_tokens", 0)
            total_usage.batches += 1

            all_metadata.extend(batch_meta)
        except Exception:
            logger.warning(
                "Metadata extraction batch failed, using defaults",
                extra={"batch_start": start, "batch_size": len(batch)},
                exc_info=True,
            )
            all_metadata.extend([_default_metadata() for _ in batch])

    total_usage.total_tokens = total_usage.prompt_tokens + total_usage.completion_tokens
    total_usage.extract_ms = round((time.perf_counter() - t0) * 1000, 1)

    logger.info(
        "Metadata extraction completed",
        extra={
            "chunks": len(chunk_texts),
            "batches": total_usage.batches,
            "extract_ms": total_usage.extract_ms,
            "prompt_tokens": total_usage.prompt_tokens,
            "completion_tokens": total_usage.completion_tokens,
        },
    )

    return ExtractionResult(metadata=all_metadata, usage=total_usage)


async def extract_metadata_batch_async(chunk_texts: list[str]) -> ExtractionResult:
    """Extract metadata from chunks asynchronously (for FastAPI endpoints)."""
    if not settings.metadata_extraction_enabled or not chunk_texts:
        return ExtractionResult(
            metadata=[_default_metadata() for _ in chunk_texts],
            usage=ExtractionUsage(model=settings.metadata_extraction_model),
        )

    t0 = time.perf_counter()
    batch_size = settings.metadata_extraction_batch_size
    all_metadata: list[ChunkMetadata] = []
    total_usage = ExtractionUsage(model=settings.metadata_extraction_model)

    for start in range(0, len(chunk_texts), batch_size):
        batch = chunk_texts[start : start + batch_size]
        prompt = _build_batch_prompt(batch)

        try:
            raw_response, usage = await _call_llm_async(prompt)
            batch_meta = _parse_response(raw_response, len(batch))

            total_usage.prompt_tokens += usage.get("prompt_tokens", 0)
            total_usage.completion_tokens += usage.get("completion_tokens", 0)
            total_usage.batches += 1

            all_metadata.extend(batch_meta)
        except Exception:
            logger.warning(
                "Metadata extraction batch failed, using defaults",
                extra={"batch_start": start, "batch_size": len(batch)},
                exc_info=True,
            )
            all_metadata.extend([_default_metadata() for _ in batch])

    total_usage.total_tokens = total_usage.prompt_tokens + total_usage.completion_tokens
    total_usage.extract_ms = round((time.perf_counter() - t0) * 1000, 1)

    logger.info(
        "Metadata extraction completed (async)",
        extra={
            "chunks": len(chunk_texts),
            "batches": total_usage.batches,
            "extract_ms": total_usage.extract_ms,
            "prompt_tokens": total_usage.prompt_tokens,
            "completion_tokens": total_usage.completion_tokens,
        },
    )

    return ExtractionResult(metadata=all_metadata, usage=total_usage)
