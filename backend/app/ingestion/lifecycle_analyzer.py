"""API lifecycle analyzer: extract auth flows, init sequences, dependencies, and unique patterns.

Two levels of analysis:
- Per-document: analyzes a single document's chunks to extract its lifecycle.
- Per-product merge: combines multiple document-level lifecycles into one coherent product lifecycle.

Includes a validation + correction loop that retries LLM when lifecycle errors are found,
and collects source doc issues as annotations.
"""

import json
import logging
import re
import time
from dataclasses import dataclass, field

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class DocIssue:
    issue_type: str
    severity: str = "warning"
    description: str = ""
    affected_entity: str | None = None
    suggestion: str | None = None
    chunk_id: int | None = None

    def to_dict(self) -> dict:
        d = {"issue_type": self.issue_type, "severity": self.severity, "description": self.description}
        if self.affected_entity:
            d["affected_entity"] = self.affected_entity
        if self.suggestion:
            d["suggestion"] = self.suggestion
        return d


@dataclass
class LifecycleUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    thinking_tokens: int = 0
    total_tokens: int = 0
    model: str = ""
    analysis_ms: float = 0.0
    llm_ms: float = 0.0
    llm_calls: int = 0


@dataclass
class LifecycleResult:
    phases: list[dict] = field(default_factory=list)
    unique_patterns: list[dict] = field(default_factory=list)
    dependency_chains: list[dict] = field(default_factory=list)
    code_skeleton: str = ""
    source_doc_issues: list[dict] = field(default_factory=list)
    validation_issues: list[dict] = field(default_factory=list)
    validation_retries: int = 0
    usage: LifecycleUsage = field(default_factory=LifecycleUsage)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_EXTRACTION_PROMPT = """\
You are an API lifecycle analyst. You are given the FULL documentation of a product API.
Your task is to extract the LIFECYCLE — the ordered sequence of steps a developer must follow
to use this API from scratch.

Analyze the document and return a JSON object with these sections:

## 1. phases
An ordered array of steps. Each step:
- phase_name: "setup" | "authentication" | "initialization" | "operation" | "cleanup" | "other"
- step_order: integer (global ordering)
- action: what the developer does (human-readable)
- api_call: the specific endpoint/method if any (e.g. "POST /auth/token", "rpc Login"). Empty string if no API call.
- inputs: array of what this step needs (from previous steps or external config)
- outputs: array of what this step produces (tokens, session IDs, object IDs)
- output_used_by: array of later step actions that consume this output
- is_required: boolean
- notes: unique details, gotchas, quirks specific to THIS API

## 2. unique_patterns
Array of things that make this API different from a standard REST/gRPC API:
- pattern: short identifier (e.g. "digest_auth", "hmac_signing", "session_init")
- description: what it is
- impact: what breaks if you ignore it
- code_hint: one-line code suggestion

Focus on: non-standard auth, required initialization rituals, unusual data flow,
idempotency, rate limiting, required headers, binary protocols, mixed transport.

## 3. dependency_chains
Array of explicit "A must happen before B" relationships:
- from_action: action name (must match a phase action)
- to_action: action name (must match a phase action)
- data_flow: what data passes between them
- description: why the dependency exists

## 4. code_skeleton
A minimal but complete Python pseudocode showing the full lifecycle from setup to cleanup.
Use real endpoint paths from the documentation. Include error handling for auth token refresh.

## 5. source_doc_issues
Array of issues you found IN THE SOURCE DOCUMENTATION (not in your analysis):
- issue_type: "phantom_endpoint" | "contradictory_params" | "missing_auth_docs" | "broken_reference" | "deprecated_undocumented" | "inconsistent_model"
- severity: "info" | "warning" | "error"
- description: what the issue is
- affected_entity: which endpoint/model/section is affected
- suggestion: how to resolve it

Return ONLY valid JSON. Do NOT include any text outside the JSON object.
"""

_MERGE_PROMPT = """\
You are an API lifecycle analyst. You have lifecycle analyses from {count} separate documentation \
files for the same product. Merge them into a single coherent product lifecycle.

Rules:
- Deduplicate phases that appear in multiple documents (same endpoint = same phase).
- Order phases into a coherent lifecycle: setup -> authentication -> initialization -> operations -> cleanup.
- Merge unique_patterns from all documents, deduplicating by pattern name.
- Build a unified code_skeleton covering the full API (all documents combined).
- If documents contradict each other (different auth methods, conflicting params), report in source_doc_issues.
- Preserve all unique information from each document.

Return the same JSON structure as the individual analyses (phases, unique_patterns, \
dependency_chains, code_skeleton, source_doc_issues).

Here are the individual lifecycle analyses:

{lifecycles_json}

Return ONLY valid JSON. Do NOT include any text outside the JSON object.
"""

_CORRECTION_PROMPT = """\
Your previous API lifecycle analysis had these errors:

{errors}

Here is your previous result:
{previous_result}

Fix ONLY the identified errors. Keep everything else unchanged.
Return the corrected full JSON object with the same structure (phases, unique_patterns, \
dependency_chains, code_skeleton, source_doc_issues).

Return ONLY valid JSON. Do NOT include any text outside the JSON object.
"""


# ---------------------------------------------------------------------------
# LLM calls (sync — for Celery workers)
# ---------------------------------------------------------------------------

def _call_llm_sync(system: str, user: str, *, json_mode: bool = True) -> tuple[str, dict, float]:
    """Synchronous LLM call. Returns (response_text, usage_dict, llm_ms).

    usage_dict includes prompt_tokens, completion_tokens, and thinking_tokens
    (if the model returns them).
    """
    url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"
    payload: dict = {
        "model": settings.lifecycle_analysis_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0,
        "max_tokens": 16384,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.gemini_api_key}",
    }

    t0 = time.perf_counter()
    with httpx.Client(timeout=httpx.Timeout(180.0, connect=10.0)) as client:
        resp = client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    llm_ms = round((time.perf_counter() - t0) * 1000, 1)

    text = data["choices"][0]["message"]["content"].strip()
    raw_usage = data.get("usage", {})

    usage = {
        "prompt_tokens": raw_usage.get("prompt_tokens", 0),
        "completion_tokens": raw_usage.get("completion_tokens", 0),
        "thinking_tokens": raw_usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0)
                           or raw_usage.get("thinking_tokens", 0),
    }

    return text, usage, llm_ms


def _parse_lifecycle_json(raw: str) -> dict | None:
    """Parse LLM response as JSON, stripping markdown fences."""
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:])
        if raw.endswith("```"):
            raw = raw[:-3].strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Failed to parse lifecycle JSON", extra={"raw_preview": raw[:500]})
        return None


def _estimate_tokens(text: str) -> int:
    words = len(text.split())
    return int(words * 1.3)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_ENDPOINT_RE = re.compile(
    r"(?:GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\s+/[^\s,;)\"']+|"
    r"/[a-zA-Z][a-zA-Z0-9_/{}.-]+",
    re.IGNORECASE,
)


def _extract_endpoints_from_chunks(chunk_contents: list[str]) -> set[str]:
    """Extract all endpoint-like paths from chunk contents."""
    endpoints: set[str] = set()
    for content in chunk_contents:
        for match in _ENDPOINT_RE.finditer(content):
            path = match.group(0).strip()
            parts = path.split()
            ep = parts[-1] if len(parts) > 1 else parts[0]
            ep = re.sub(r"\{[^}]+\}", "{id}", ep)
            endpoints.add(ep.lower())
    return endpoints


def _normalize_endpoint(api_call: str) -> str:
    """Normalize endpoint for comparison."""
    parts = api_call.strip().split()
    ep = parts[-1] if len(parts) > 1 else parts[0]
    ep = re.sub(r"\{[^}]+\}", "{id}", ep)
    return ep.lower()


def _validate_lifecycle(
    result: LifecycleResult,
    chunk_contents: list[str],
) -> tuple[list[str], list[DocIssue]]:
    """Validate a lifecycle result against source chunks.

    Returns (lifecycle_errors, source_doc_issues).
    lifecycle_errors: list of error descriptions (fixable by LLM retry).
    source_doc_issues: list of DocIssue (saved as annotations).
    """
    lifecycle_errors: list[str] = []
    doc_issues: list[DocIssue] = []

    if not result.phases:
        lifecycle_errors.append("No phases extracted. The document likely describes an API — extract its lifecycle.")
        return lifecycle_errors, doc_issues

    known_endpoints = _extract_endpoints_from_chunks(chunk_contents)

    phase_actions = {p.get("action", "") for p in result.phases}

    for phase in result.phases:
        api_call = phase.get("api_call", "")
        if api_call and "/" in api_call:
            normalized = _normalize_endpoint(api_call)
            if known_endpoints and not any(normalized in ep or ep in normalized for ep in known_endpoints):
                lifecycle_errors.append(
                    f"Phase '{phase.get('action')}' references endpoint '{api_call}' "
                    f"which was not found in the source documentation."
                )

    has_auth_phase = any(
        p.get("phase_name") in ("authentication", "setup")
        and any(kw in (p.get("action", "") + p.get("notes", "")).lower()
                for kw in ("auth", "login", "token", "key", "credential", "session"))
        for p in result.phases
    )
    full_text_lower = " ".join(chunk_contents).lower()
    doc_mentions_auth = any(
        kw in full_text_lower
        for kw in ("authentication", "authorization", "login", "bearer", "api key", "api_key", "token", "oauth", "digest")
    )
    if doc_mentions_auth and not has_auth_phase:
        lifecycle_errors.append(
            "The documentation mentions authentication but no authentication phase was extracted. "
            "Add an authentication phase."
        )

    for dep in result.dependency_chains:
        from_a = dep.get("from_action", "")
        to_a = dep.get("to_action", "")
        if from_a and from_a not in phase_actions:
            lifecycle_errors.append(
                f"dependency_chains references from_action '{from_a}' not found in phases."
            )
        if to_a and to_a not in phase_actions:
            lifecycle_errors.append(
                f"dependency_chains references to_action '{to_a}' not found in phases."
            )

    if result.code_skeleton:
        phase_outputs = set()
        for p in result.phases:
            for out in p.get("outputs", []):
                phase_outputs.add(out.lower().replace(" ", "_"))
            if p.get("api_call"):
                parts = p["api_call"].split()
                ep = parts[-1] if parts else ""
                if ep:
                    phase_outputs.add(ep.lower())

        skeleton_lower = result.code_skeleton.lower()
        skeleton_endpoints = set(_ENDPOINT_RE.findall(skeleton_lower))
        for ep_match in skeleton_endpoints:
            ep_parts = ep_match.strip().split()
            ep = ep_parts[-1] if len(ep_parts) > 1 else ep_parts[0]
            ep_norm = re.sub(r"\{[^}]+\}", "{id}", ep).lower()
            if known_endpoints and not any(ep_norm in ke or ke in ep_norm for ke in known_endpoints):
                phase_ep_calls = {
                    _normalize_endpoint(p["api_call"])
                    for p in result.phases if p.get("api_call")
                }
                if not any(ep_norm in pe or pe in ep_norm for pe in phase_ep_calls):
                    lifecycle_errors.append(
                        f"code_skeleton references endpoint '{ep_match.strip()}' "
                        f"not found in phases or source documentation."
                    )

    for issue in result.source_doc_issues:
        doc_issues.append(DocIssue(
            issue_type=issue.get("issue_type", "other"),
            severity=issue.get("severity", "warning"),
            description=issue.get("description", ""),
            affected_entity=issue.get("affected_entity"),
            suggestion=issue.get("suggestion"),
        ))

    return lifecycle_errors, doc_issues


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------

def _extract_lifecycle(doc_text: str, usage: LifecycleUsage) -> LifecycleResult:
    """Single LLM call to extract lifecycle from document text."""
    raw, llm_usage, call_ms = _call_llm_sync(_EXTRACTION_PROMPT, doc_text)
    usage.prompt_tokens += llm_usage.get("prompt_tokens", 0)
    usage.completion_tokens += llm_usage.get("completion_tokens", 0)
    usage.thinking_tokens += llm_usage.get("thinking_tokens", 0)
    usage.llm_ms += call_ms
    usage.llm_calls += 1

    parsed = _parse_lifecycle_json(raw)
    if parsed is None:
        return LifecycleResult(
            validation_issues=[{"error": "Failed to parse LLM response as JSON"}],
            usage=usage,
        )

    return LifecycleResult(
        phases=parsed.get("phases", []),
        unique_patterns=parsed.get("unique_patterns", []),
        dependency_chains=parsed.get("dependency_chains", []),
        code_skeleton=parsed.get("code_skeleton", ""),
        source_doc_issues=parsed.get("source_doc_issues", []),
        usage=usage,
    )


def _retry_with_corrections(
    previous: LifecycleResult,
    errors: list[str],
    usage: LifecycleUsage,
) -> LifecycleResult:
    """Re-call LLM with error hints to correct the lifecycle."""
    previous_json = json.dumps({
        "phases": previous.phases,
        "unique_patterns": previous.unique_patterns,
        "dependency_chains": previous.dependency_chains,
        "code_skeleton": previous.code_skeleton,
    }, indent=2, ensure_ascii=False)

    prompt = _CORRECTION_PROMPT.format(
        errors="\n".join(f"- {e}" for e in errors),
        previous_result=previous_json,
    )

    raw, llm_usage, call_ms = _call_llm_sync(
        "You are an API lifecycle analyst. Fix the errors in the previous analysis.",
        prompt,
    )
    usage.prompt_tokens += llm_usage.get("prompt_tokens", 0)
    usage.completion_tokens += llm_usage.get("completion_tokens", 0)
    usage.thinking_tokens += llm_usage.get("thinking_tokens", 0)
    usage.llm_ms += call_ms
    usage.llm_calls += 1

    parsed = _parse_lifecycle_json(raw)
    if parsed is None:
        return previous

    return LifecycleResult(
        phases=parsed.get("phases", previous.phases),
        unique_patterns=parsed.get("unique_patterns", previous.unique_patterns),
        dependency_chains=parsed.get("dependency_chains", previous.dependency_chains),
        code_skeleton=parsed.get("code_skeleton", previous.code_skeleton),
        source_doc_issues=parsed.get("source_doc_issues", []),
        usage=usage,
    )


def _validate_and_correct(
    result: LifecycleResult,
    chunk_contents: list[str],
    max_retries: int,
) -> tuple[LifecycleResult, list[DocIssue]]:
    """Validate lifecycle, retry LLM if lifecycle errors, collect doc issues."""
    all_doc_issues: list[DocIssue] = []
    last_errors: list[str] = []

    for attempt in range(max_retries + 1):
        lifecycle_errors, source_issues = _validate_lifecycle(result, chunk_contents)
        all_doc_issues.extend(source_issues)

        if not lifecycle_errors:
            result.validation_retries = attempt
            return result, all_doc_issues

        last_errors = lifecycle_errors

        if attempt < max_retries:
            logger.info(
                "Lifecycle validation failed, retrying",
                extra={"attempt": attempt + 1, "errors": lifecycle_errors},
            )
            result = _retry_with_corrections(result, lifecycle_errors, result.usage)

    result.validation_issues = [{"error": e} for e in last_errors]
    result.validation_retries = max_retries
    return result, all_doc_issues


# ---------------------------------------------------------------------------
# Public API: per-document analysis
# ---------------------------------------------------------------------------

def analyze_document_lifecycle_sync(
    document_id: int,
    session,
) -> tuple[LifecycleResult, list[DocIssue]]:
    """Analyze a single document and extract its API lifecycle.

    Args:
        document_id: The document to analyze.
        session: SQLAlchemy sync Session.

    Returns:
        (LifecycleResult, list of DocIssue annotations)
    """
    from sqlalchemy import select as sa_select
    from app.models import Chunk

    t0 = time.perf_counter()
    usage = LifecycleUsage(model=settings.lifecycle_analysis_model)

    chunks = session.execute(
        sa_select(Chunk.heading_path, Chunk.content, Chunk.id)
        .where(Chunk.document_id == document_id)
        .order_by(Chunk.chunk_index)
    ).all()

    if not chunks:
        return LifecycleResult(
            validation_issues=[{"error": "No chunks found for document"}],
            usage=usage,
        ), []

    chunk_contents = [c.content for c in chunks]
    doc_text_parts = []
    for c in chunks:
        doc_text_parts.append(f"## {c.heading_path}\n{c.content}")
    doc_text = "\n\n".join(doc_text_parts)

    total_tokens = _estimate_tokens(doc_text)

    if total_tokens > settings.lifecycle_analysis_max_doc_tokens:
        sections: dict[str, list[str]] = {}
        for c in chunks:
            top_heading = c.heading_path.split(" > ")[0] if " > " in c.heading_path else c.heading_path
            sections.setdefault(top_heading, []).append(c.content)

        summaries = []
        for heading, contents in sections.items():
            section_text = f"## {heading}\n" + "\n".join(contents)
            if _estimate_tokens(section_text) > 50_000:
                section_text = section_text[:200_000]
            summary_prompt = (
                f"Summarize this API documentation section with focus on: "
                f"endpoints, authentication, initialization steps, data models, "
                f"error handling. Preserve ALL endpoint paths and parameter names. "
                f"Preserve cross-references to other sections (e.g. 'see Authentication section', "
                f"'requires token from /auth/login'). These cross-references are critical "
                f"for lifecycle analysis.\n\n"
                f"{section_text}"
            )
            raw, llm_usage, call_ms = _call_llm_sync(
                "You are a technical documentation summarizer.",
                summary_prompt,
                json_mode=False,
            )
            usage.prompt_tokens += llm_usage.get("prompt_tokens", 0)
            usage.completion_tokens += llm_usage.get("completion_tokens", 0)
            usage.thinking_tokens += llm_usage.get("thinking_tokens", 0)
            usage.llm_ms += call_ms
            usage.llm_calls += 1
            summaries.append(f"## {heading}\n{raw}")

        doc_text = "\n\n".join(summaries)

    result = _extract_lifecycle(doc_text, usage)

    result, doc_issues = _validate_and_correct(
        result, chunk_contents, settings.lifecycle_validation_max_retries,
    )

    usage.analysis_ms = round((time.perf_counter() - t0) * 1000, 1)
    usage.total_tokens = usage.prompt_tokens + usage.completion_tokens
    result.usage = usage

    return result, doc_issues


# ---------------------------------------------------------------------------
# Public API: per-product merge
# ---------------------------------------------------------------------------

def merge_product_lifecycle_sync(
    product_id: int,
    session,
) -> tuple[LifecycleResult, list[DocIssue]]:
    """Merge all document-level lifecycles for a product into one.

    If only 1 doc-level lifecycle exists, copies it (no LLM call).

    Args:
        product_id: The product to merge lifecycles for.
        session: SQLAlchemy sync Session.

    Returns:
        (LifecycleResult, list of cross-document DocIssue annotations)
    """
    from sqlalchemy import select as sa_select
    from app.models import ApiLifecycle

    t0 = time.perf_counter()
    usage = LifecycleUsage(model=settings.lifecycle_analysis_model)

    doc_lifecycles = session.execute(
        sa_select(ApiLifecycle)
        .where(
            ApiLifecycle.product_id == product_id,
            ApiLifecycle.document_id.isnot(None),
            ApiLifecycle.status == "ready",
        )
    ).scalars().all()

    if not doc_lifecycles:
        return LifecycleResult(
            validation_issues=[{"error": "No document-level lifecycles found for product"}],
            usage=usage,
        ), []

    if len(doc_lifecycles) == 1:
        lc = doc_lifecycles[0]
        result = LifecycleResult(
            phases=lc.phases or [],
            unique_patterns=lc.unique_patterns or [],
            dependency_chains=lc.dependency_chains or [],
            code_skeleton=lc.code_skeleton or "",
            usage=usage,
        )
        usage.analysis_ms = round((time.perf_counter() - t0) * 1000, 1)
        return result, []

    lifecycles_data = []
    for lc in doc_lifecycles:
        lifecycles_data.append({
            "document_id": lc.document_id,
            "phases": lc.phases or [],
            "unique_patterns": lc.unique_patterns or [],
            "dependency_chains": lc.dependency_chains or [],
            "code_skeleton": lc.code_skeleton or "",
        })

    merge_prompt = _MERGE_PROMPT.format(
        count=len(lifecycles_data),
        lifecycles_json=json.dumps(lifecycles_data, indent=2, ensure_ascii=False),
    )

    raw, llm_usage, call_ms = _call_llm_sync(
        "You are an API lifecycle analyst. Merge multiple lifecycle analyses into one.",
        merge_prompt,
    )
    usage.prompt_tokens += llm_usage.get("prompt_tokens", 0)
    usage.completion_tokens += llm_usage.get("completion_tokens", 0)
    usage.thinking_tokens += llm_usage.get("thinking_tokens", 0)
    usage.llm_ms += call_ms
    usage.llm_calls += 1

    parsed = _parse_lifecycle_json(raw)
    if parsed is None:
        return LifecycleResult(
            validation_issues=[{"error": "Failed to parse merged lifecycle JSON"}],
            usage=usage,
        ), []

    result = LifecycleResult(
        phases=parsed.get("phases", []),
        unique_patterns=parsed.get("unique_patterns", []),
        dependency_chains=parsed.get("dependency_chains", []),
        code_skeleton=parsed.get("code_skeleton", ""),
        source_doc_issues=parsed.get("source_doc_issues", []),
        usage=usage,
    )

    all_chunk_contents: list[str] = []
    from app.models import Chunk
    from sqlalchemy import select as sa_select2
    for lc in doc_lifecycles:
        if lc.document_id:
            rows = session.execute(
                sa_select2(Chunk.content)
                .where(Chunk.document_id == lc.document_id)
            ).scalars().all()
            all_chunk_contents.extend(rows)

    result, doc_issues = _validate_and_correct(
        result, all_chunk_contents, settings.lifecycle_validation_max_retries,
    )

    usage.analysis_ms = round((time.perf_counter() - t0) * 1000, 1)
    usage.total_tokens = usage.prompt_tokens + usage.completion_tokens
    result.usage = usage

    return result, doc_issues
