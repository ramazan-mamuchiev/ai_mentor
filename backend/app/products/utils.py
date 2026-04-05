"""Utility helpers for the products module."""

from __future__ import annotations

import json
import re
import unicodedata


def make_product_slug(manufacturer: str, name: str, version: str = "") -> str:
    """Build a URL-safe slug from manufacturer, product name, and version."""
    parts = [manufacturer, name]
    if version:
        parts.append(version)
    raw = " ".join(p for p in parts if p)
    raw = unicodedata.normalize("NFKD", raw)
    raw = raw.encode("ascii", "ignore").decode("ascii")
    raw = raw.lower()
    raw = re.sub(r"[^a-z0-9]+", "-", raw)
    raw = raw.strip("-")
    return raw or "product"


# ---------------------------------------------------------------------------
# Lifecycle payload sanitisation
# ---------------------------------------------------------------------------
# LLM-generated JSON may contain non-string values where the frontend expects
# strings (e.g. example_value: {} instead of "{}").  The helpers below coerce
# such values to JSON strings at the API boundary so React never receives a
# raw object where it expects a renderable primitive.

_PHASE_STR_KEYS: set[str] = {
    "phase_name", "action", "api_call", "http_method",
    "content_type", "notes", "request_example", "response_example",
    "output_used_by",
}
_DM_FIELD_STR_KEYS: set[str] = {
    "name", "type", "constraints", "description", "example_value",
}
_PREREQ_STR_KEYS: set[str] = {
    "name", "type", "description", "example_value", "how_to_obtain",
}
_ERR_STR_KEYS: set[str] = {
    "error_code", "meaning", "recovery_action",
}
_PATTERN_STR_KEYS: set[str] = {
    "pattern", "description", "code_hint",
    "pattern_type", "endpoint", "mechanism",
}
_DEP_STR_KEYS: set[str] = {
    "from_action", "to_action", "data_flow",
}


def sanitize_str_fields(items: list, str_keys: set[str]) -> list:
    """Ensure that *str_keys* inside each dict are coerced to strings."""
    sanitized: list = []
    for item in items:
        if not isinstance(item, dict):
            sanitized.append(item)
            continue
        row = dict(item)
        for k in str_keys:
            v = row.get(k)
            if v is not None and not isinstance(v, (str, int, float, bool)):
                row[k] = json.dumps(v, ensure_ascii=False)
        sanitized.append(row)
    return sanitized


def sanitize_data_models(models: list) -> list:
    """Sanitize data-model dicts, including nested field records."""
    result: list = []
    for md in models:
        if not isinstance(md, dict):
            result.append(md)
            continue
        md = dict(md)
        if "fields" in md and isinstance(md["fields"], list):
            md["fields"] = sanitize_str_fields(md["fields"], _DM_FIELD_STR_KEYS)
        result.append(md)
    return result


def sanitize_lifecycle_payload(lc) -> dict:  # noqa: ANN001 – accepts ApiLifecycle
    """Build a frontend-safe dict from an ``ApiLifecycle`` model instance."""
    return {
        "status": lc.status,
        "phases": sanitize_str_fields(lc.phases or [], _PHASE_STR_KEYS),
        "unique_patterns": sanitize_str_fields(lc.unique_patterns or [], _PATTERN_STR_KEYS),
        "dependency_chains": sanitize_str_fields(lc.dependency_chains or [], _DEP_STR_KEYS),
        "code_skeleton": lc.code_skeleton or "",
        "code_skeleton_translations": lc.code_skeleton_translations or {},
        "data_models": sanitize_data_models(lc.data_models or []),
        "error_catalog": sanitize_str_fields(lc.error_catalog or [], _ERR_STR_KEYS),
        "prerequisites": sanitize_str_fields(lc.prerequisites or [], _PREREQ_STR_KEYS),
        "data_access_patterns": sanitize_str_fields(lc.data_access_patterns or [], _PATTERN_STR_KEYS),
        "endpoint_coverage": lc.endpoint_coverage or [],
        "integration_data_flows": lc.integration_data_flows or {},
        "validation_issues": lc.validation_issues or [],
        "validation_retries": lc.validation_retries,
        "prompt_tokens": lc.prompt_tokens,
        "completion_tokens": lc.completion_tokens,
        "analysis_ms": lc.analysis_ms,
        "model": lc.model,
        "created_at": lc.created_at.isoformat() if lc.created_at else None,
        "updated_at": lc.updated_at.isoformat() if lc.updated_at else None,
    }
