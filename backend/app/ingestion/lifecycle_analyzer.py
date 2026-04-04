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
    data_models: list[dict] = field(default_factory=list)
    error_catalog: list[dict] = field(default_factory=list)
    prerequisites: list[dict] = field(default_factory=list)
    data_access_patterns: list[dict] = field(default_factory=list)
    endpoint_coverage: list[dict] = field(default_factory=list)
    integration_data_flows: dict = field(default_factory=dict)
    validation_issues: list[dict] = field(default_factory=list)
    validation_retries: int = 0
    usage: LifecycleUsage = field(default_factory=LifecycleUsage)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_EXTRACTION_PROMPT = """\
You are an API integration analyst. You are given the FULL documentation of a product API.
Your task is to extract EVERYTHING a developer needs to write production integration code
from scratch — the complete integration blueprint.

IMPORTANT: ALL output text MUST be in English, regardless of the source document language.
If the documentation is in Chinese, Russian, or any other language, translate all free-text
fields into English. Keep original API endpoint paths, parameter names, code identifiers,
and header names unchanged.

Analyze the document and return a JSON object with ALL of the following sections:

## 1. phases
An ordered array of integration steps. Each step:
- phase_name: "setup" | "authentication" | "initialization" | "operation" | "cleanup" | "other"
- step_order: integer (global ordering across all phases)
- action: what the developer does (human-readable)
- api_call: the specific endpoint/method (e.g. "POST /auth/token", "rpc Login"). Empty string if no API call.
- http_method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE" | "" (empty if not HTTP)
- content_type: request content type (e.g. "application/json", "multipart/form-data"). Empty string if not applicable.
- inputs: array of what this step needs (from previous steps or external config)
- outputs: array of what this step produces (tokens, session IDs, object IDs)
- output_used_by: array of later step actions that consume this output
- is_required: boolean
- notes: unique details, gotchas, quirks specific to THIS API
- request_example: minimal but complete request body/params as a string (JSON, form fields, or query params). Empty string if no request body.
- response_example: key fields of the response as a string (JSON with important fields). Empty string if unknown.

## 2. unique_patterns
Array of things that make this API different from a standard REST/gRPC API:
- pattern: short identifier (e.g. "digest_auth", "hmac_signing", "session_init")
- description: what it is
- impact: what breaks if you ignore it
- code_hint: one-line code suggestion

Focus on: non-standard auth, required initialization rituals, unusual data flow,
idempotency, rate limiting, required headers, binary protocols, mixed transport,
session affinity, mandatory request ordering, custom error formats.

## 3. dependency_chains
Array of explicit "A must happen before B" relationships:
- from_action: action name (must match a phase action)
- to_action: action name (must match a phase action)
- data_flow: what data passes between them
- description: why the dependency exists

## 4. code_skeleton
A PRODUCTION-READY Python script using httpx that demonstrates the full lifecycle from
setup to cleanup. Requirements:
- Use real endpoint paths and parameter names from the documentation
- Include proper headers (Authorization, Content-Type, custom headers)
- Include actual request body structure (not placeholders)
- Parse response JSON and extract needed fields by name
- Handle authentication token refresh
- Handle specific HTTP error codes mentioned in the docs (not generic try/except)
- Include retry with exponential backoff for transient errors (429, 503)
- Handle pagination if the API uses it
- Include cleanup/logout if the API requires it
- Add type hints and brief comments for non-obvious steps

## 5. source_doc_issues
Array of issues found IN THE SOURCE DOCUMENTATION (not in your analysis).
Be thorough — check every endpoint for completeness.

- issue_type: one of:
  "phantom_endpoint" — endpoint mentioned but never described
  "contradictory_params" — parameter described differently in different places
  "missing_auth_docs" — authentication mentioned but not documented
  "broken_reference" — reference to non-existent section/endpoint
  "deprecated_undocumented" — deprecated without being marked as such
  "inconsistent_model" — data model fields don't match between sections
  "missing_error_docs" — endpoint described without error responses
  "missing_request_body" — POST/PUT/PATCH endpoint without request body description
  "missing_response_schema" — endpoint without response format description
  "ambiguous_type" — parameter type is vague (e.g. "string" for what is clearly an enum, "object" without field descriptions)
  "missing_pagination_docs" — list endpoint without pagination description
  "version_mismatch" — documentation references API version that doesn't match the described behavior
  "undocumented_header" — header used in examples but never described
  "incomplete_example" — code example is truncated, missing imports, or uses unexplained placeholders
  "stale_url" — URL in documentation that appears non-functional (http instead of https, placeholder domain)
  "missing_rate_limit_docs" — rate limiting mentioned but specific limits not documented

- severity: "error" | "warning" | "info"
  error: API integration WILL fail without this info (phantom_endpoint, contradictory_params, missing_auth_docs)
  warning: code will be incorrect/fragile (missing_request_body, missing_response_schema, missing_error_docs, incomplete_example)
  info: inconvenience or potential issue (ambiguous_type, stale_url, version_mismatch, undocumented_header, missing_pagination_docs, missing_rate_limit_docs)

- description: what the issue is
- affected_entity: which endpoint/model/section is affected
- suggestion: how to resolve it

## 6. data_models
Array of request/response data structures used by the API:
- model_name: descriptive name (e.g. "CreateCameraRequest", "AuthTokenResponse")
- used_in: array of api_call strings that use this model (must match phase api_call values)
- direction: "request" | "response" | "both"
- content_type: "application/json" | "multipart/form-data" | "application/x-www-form-urlencoded" | "application/xml" | other
- fields: array of:
  - name: field name
  - type: data type ("string", "integer", "boolean", "array<string>", "object", "float", etc.)
  - required: boolean
  - description: what this field does
  - constraints: validation rules if any (min/max, regex pattern, enum values like "enum: active|inactive|deleted")
  - example_value: a realistic example value as a string

Extract ALL models you can find in the documentation, even if incomplete. For each
POST/PUT/PATCH endpoint, there should be at least a request model. For each endpoint
returning data, there should be at least a response model.

## 7. error_catalog
Array of error responses the API can return:
- http_status: integer (e.g. 400, 401, 403, 404, 409, 429, 500, 503)
- error_code: API-specific error code string if any (e.g. "CAMERA_OFFLINE", "TOKEN_EXPIRED"). Empty string if none.
- meaning: what this error means in context of this API
- phase: which phase_name this error is most likely in ("authentication", "operation", etc.)
- recovery_action: "retry" | "re_auth" | "abort" | "wait" | "other"
- retry_after_seconds: integer or null (e.g. 60 for rate limiting)

Extract ALL error codes/statuses mentioned anywhere in the documentation.

## 8. prerequisites
Array of things a developer needs BEFORE making any API call:
- name: identifier (e.g. "BASE_URL", "API_KEY", "CLIENT_CERTIFICATE", "SDK_LIBRARY")
- type: "url" | "secret" | "file" | "enum" | "string" | "sdk"
- description: what it is and why it's needed
- example_value: a realistic example (use placeholder domains like "example.com" for URLs, "your-api-key-here" for secrets)
- how_to_obtain: where/how the developer gets this (admin panel, registration, download, etc.)

## 9. data_access_patterns
Array of patterns for retrieving collections/streams of data:
- pattern_type: "pagination_offset" | "pagination_cursor" | "streaming_sse" | "websocket" | "long_polling" | "batch" | "callback_webhook" | "none"
- endpoint: which endpoint uses this pattern
- mechanism: how it works (parameter names, header names, response fields for next page, etc.)
- code_hint: 2-3 line Python code showing the pattern

If the API has list endpoints but pagination is not documented, still include an entry
with pattern_type "none" and note it in source_doc_issues as "missing_pagination_docs".

## 10. endpoint_coverage
Array assessing documentation completeness for EACH endpoint found in the docs:
- endpoint: the endpoint path (e.g. "/api/v1/cameras")
- method: HTTP method (e.g. "POST")
- has_request_body_docs: boolean — is the request body/params described?
- has_response_docs: boolean — is the response format described?
- has_error_docs: boolean — are error responses described?
- has_example: boolean — is there a code example or curl command?
- completeness: float 0.0-1.0 (average of the 4 boolean fields above)
- missing: array of strings describing what's missing (e.g. ["request_body", "error_codes", "example"])

Be honest and strict in this assessment. This helps developers know which parts
of the documentation to trust and where they need to be careful.

## 11. integration_data_flows
An object describing the architectural data-flow graph between system components.
This helps developers understand the overall topology BEFORE writing code.

### components
Array of system components (nodes of the graph):
- id: short snake_case identifier (e.g. "client", "auth_server", "video_module", "camera_hw")
- name: human-readable name
- type: "external" (the developer's code) | "service" | "gateway" | "hardware" | "storage" | "queue"
- description: what this component does (1 sentence)

There MUST be at least one component with type "external" representing the integration client.

### flows
Array of directed data flows (edges of the graph):
- from: component id (must match a component)
- to: component id (must match a component)
- label: what is transferred (e.g. "POST /auth/login (credentials)", "MJPEG video stream")
- protocol: "HTTP" | "HTTPS" | "gRPC" | "WebSocket" | "SSE" | "RTSP" | "MQTT" | "TCP" | "UDP" | "other"
- data_type: semantic type (e.g. "credentials", "token", "config", "video_stream", "events", "command")
- direction: "request" | "response" | "bidirectional"

Include BOTH request and response flows where applicable (e.g. client sends credentials,
auth_server returns token — these are 2 separate flows).

### diagram_mermaid
A Mermaid graph (LR direction) representing the flows. Use descriptive node labels.
Use `-->|label|` syntax for edge labels. Keep labels short (max ~30 chars).
Example: `graph LR\n  client[Client] -->|POST /login| auth[Auth Server]\n  auth -->|JWT token| client`

Return ONLY valid JSON. Do NOT include any text outside the JSON object.
"""

_MERGE_PROMPT = """\
You are an API integration analyst. You have lifecycle analyses from {count} separate documentation \
files for the same product. Merge them into a single coherent product integration blueprint.

IMPORTANT: ALL output text MUST be in English. Translate any non-English content into English.

Rules:
- Deduplicate phases that appear in multiple documents (same endpoint = same phase).
- Order phases into a coherent lifecycle: setup -> authentication -> initialization -> operations -> cleanup.
- Merge unique_patterns from all documents, deduplicating by pattern name.
- Merge data_models: deduplicate by model_name, combine fields from different docs, keep the most complete version.
- Merge error_catalog: deduplicate by (http_status, error_code), keep the most detailed description.
- Merge prerequisites: deduplicate by name, keep the most complete description.
- Merge data_access_patterns: deduplicate by (endpoint, pattern_type).
- Merge endpoint_coverage: deduplicate by (endpoint, method), combine coverage info (if one doc has request_body and another has error_docs, the merged entry should have both).
- Merge integration_data_flows: combine all components (deduplicate by id), combine all flows (deduplicate by from+to+label), rebuild diagram_mermaid to reflect the full system.
- Build a unified code_skeleton covering the full API (all documents combined).
- If documents contradict each other (different auth methods, conflicting params), report in source_doc_issues.
- Preserve all unique information from each document.

Return the same JSON structure as the individual analyses (phases, unique_patterns, \
dependency_chains, code_skeleton, source_doc_issues, data_models, error_catalog, \
prerequisites, data_access_patterns, endpoint_coverage, integration_data_flows).

Here are the individual lifecycle analyses:

{lifecycles_json}

Return ONLY valid JSON. Do NOT include any text outside the JSON object.
"""

_CORRECTION_PROMPT = """\
Your previous API integration analysis had these errors:

{errors}

Here is your previous result:
{previous_result}

Fix ONLY the identified errors. Keep everything else unchanged.
All output text MUST remain in English.
Return the corrected full JSON object with the same structure (phases, unique_patterns, \
dependency_chains, code_skeleton, source_doc_issues, data_models, error_catalog, \
prerequisites, data_access_patterns, endpoint_coverage, integration_data_flows).

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
        "max_tokens": settings.lifecycle_analysis_max_output_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.gemini_api_key}",
    }

    max_retries = 3
    retry_delays = [5, 15, 30]
    retryable_statuses = {429, 500, 502, 503, 504}

    t0 = time.perf_counter()
    with httpx.Client(timeout=httpx.Timeout(180.0, connect=10.0)) as client:
        last_exc: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                resp = client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                last_exc = None
                break
            except httpx.HTTPStatusError as e:
                last_exc = e
                if e.response.status_code in retryable_statuses and attempt < max_retries:
                    delay = retry_delays[min(attempt, len(retry_delays) - 1)]
                    logger.warning(
                        "LLM call got %s, retrying in %ds (attempt %d/%d)",
                        e.response.status_code, delay, attempt + 1, max_retries,
                    )
                    time.sleep(delay)
                else:
                    raise
            except (httpx.ConnectError, httpx.ReadTimeout) as e:
                last_exc = e
                if attempt < max_retries:
                    delay = retry_delays[min(attempt, len(retry_delays) - 1)]
                    logger.warning(
                        "LLM call network error: %s, retrying in %ds (attempt %d/%d)",
                        type(e).__name__, delay, attempt + 1, max_retries,
                    )
                    time.sleep(delay)
                else:
                    raise
        if last_exc is not None:
            raise last_exc
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
    r"/[a-zA-Z0-9][a-zA-Z0-9_/{}.:=-]+",
    re.IGNORECASE,
)

_API_PREFIX_RE = re.compile(r"^/api/v\d+/", re.IGNORECASE)


def _extract_endpoints_from_chunks(chunk_contents: list[str]) -> set[str]:
    """Extract all endpoint-like paths from chunk contents."""
    endpoints: set[str] = set()
    for content in chunk_contents:
        for match in _ENDPOINT_RE.finditer(content):
            path = match.group(0).strip()
            parts = path.split()
            ep = parts[-1] if len(parts) > 1 else parts[0]
            ep = _normalize_endpoint(ep)
            if ep and len(ep) > 1:
                endpoints.add(ep)
    return endpoints


def _normalize_endpoint(api_call: str) -> str:
    """Normalize endpoint for comparison: strip method, query string, trailing
    slashes, and normalize path parameter placeholders."""
    parts = api_call.strip().split()
    ep = parts[-1] if len(parts) > 1 else parts[0]
    ep = ep.split("?")[0]
    ep = ep.rstrip("/")
    ep = re.sub(r"\{[^}]+\}", "{id}", ep)
    ep = re.sub(r"/\d+(?=/|$)", "/{id}", ep)
    return ep.lower()


def _strip_api_prefix(ep: str) -> str:
    """Remove common API version prefixes for fuzzy comparison."""
    return _API_PREFIX_RE.sub("/", ep)


def _endpoints_match(a: str, b: str) -> bool:
    """Two-level endpoint comparison: exact then fuzzy (without api prefix)."""
    if a in b or b in a:
        return True
    a_stripped = _strip_api_prefix(a)
    b_stripped = _strip_api_prefix(b)
    if a_stripped in b_stripped or b_stripped in a_stripped:
        return True
    return False


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

    # --- New validations for enhanced analysis ---

    # Endpoint coverage check: at least 80% of known endpoints should be covered
    if known_endpoints and result.endpoint_coverage:
        covered = {_normalize_endpoint(ec.get("endpoint", "") + " " + ec.get("method", ""))
                   for ec in result.endpoint_coverage if ec.get("endpoint")}
        coverage_ratio = len(covered & known_endpoints) / len(known_endpoints) if known_endpoints else 1.0
        if coverage_ratio < 0.5:
            lifecycle_errors.append(
                f"endpoint_coverage only covers {coverage_ratio:.0%} of endpoints found in the document. "
                f"Add coverage entries for ALL endpoints mentioned in the documentation."
            )
    elif known_endpoints and not result.endpoint_coverage:
        lifecycle_errors.append(
            "endpoint_coverage is empty but the document contains API endpoints. "
            "Add a coverage assessment for each endpoint."
        )

    # Request example check: POST/PUT/PATCH phases should have request_example
    mutating_methods = {"post", "put", "patch"}
    phases_missing_examples = []
    for phase in result.phases:
        method = phase.get("http_method", "").lower()
        api_call = phase.get("api_call", "")
        if api_call and (method in mutating_methods or
                         any(api_call.upper().startswith(m.upper()) for m in mutating_methods)):
            if not phase.get("request_example"):
                phases_missing_examples.append(phase.get("action", api_call))
    if phases_missing_examples and len(phases_missing_examples) <= 5:
        lifecycle_errors.append(
            f"These POST/PUT/PATCH phases are missing request_example: "
            f"{', '.join(phases_missing_examples)}. Add request body examples."
        )

    # Integration data flows check
    idf = result.integration_data_flows
    if isinstance(idf, dict) and idf:
        components = idf.get("components", [])
        flows = idf.get("flows", [])
        comp_ids = {c.get("id") for c in components if c.get("id")}
        has_external = any(c.get("type") == "external" for c in components)
        if components and not has_external:
            lifecycle_errors.append(
                "integration_data_flows.components must include at least one component "
                "with type 'external' representing the integration client."
            )
        for fl in flows:
            if fl.get("from") and fl["from"] not in comp_ids:
                lifecycle_errors.append(
                    f"integration_data_flows flow references unknown component '{fl['from']}'. "
                    f"Add it to components or fix the id."
                )
            if fl.get("to") and fl["to"] not in comp_ids:
                lifecycle_errors.append(
                    f"integration_data_flows flow references unknown component '{fl['to']}'. "
                    f"Add it to components or fix the id."
                )
    elif not idf or not isinstance(idf, dict):
        if result.phases:
            lifecycle_errors.append(
                "integration_data_flows is empty. Identify the system components "
                "(client, servers, gateways, hardware) and the data flows between them."
            )

    # Data models check: if doc contains JSON structures, data_models shouldn't be empty
    full_text = " ".join(chunk_contents)
    has_json_structures = '{"' in full_text or "'{" in full_text or '"type"' in full_text.lower()
    if has_json_structures and not result.data_models:
        lifecycle_errors.append(
            "The documentation contains JSON data structures but data_models is empty. "
            "Extract request/response models with their fields."
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
    logger.info("Lifecycle extraction LLM call starting",
                extra={"doc_len": len(doc_text), "model": settings.lifecycle_analysis_model})
    raw, llm_usage, call_ms = _call_llm_sync(_EXTRACTION_PROMPT, doc_text)
    usage.prompt_tokens += llm_usage.get("prompt_tokens", 0)
    usage.completion_tokens += llm_usage.get("completion_tokens", 0)
    usage.thinking_tokens += llm_usage.get("thinking_tokens", 0)
    usage.llm_ms += call_ms
    usage.llm_calls += 1
    logger.info("Lifecycle extraction LLM call completed",
                extra={"call_ms": call_ms,
                        "prompt_tokens": llm_usage.get("prompt_tokens", 0),
                        "completion_tokens": llm_usage.get("completion_tokens", 0),
                        "response_len": len(raw) if raw else 0})

    parsed = _parse_lifecycle_json(raw)
    if parsed is None:
        return LifecycleResult(
            validation_issues=[{"error": "Failed to parse LLM response as JSON"}],
            usage=usage,
        )

    return _lifecycle_from_parsed(parsed, usage)


def _lifecycle_from_parsed(parsed: dict, usage: LifecycleUsage, fallback: LifecycleResult | None = None) -> LifecycleResult:
    """Build LifecycleResult from parsed JSON, with optional fallback for corrections."""
    fb = fallback or LifecycleResult()
    return LifecycleResult(
        phases=parsed.get("phases", fb.phases),
        unique_patterns=parsed.get("unique_patterns", fb.unique_patterns),
        dependency_chains=parsed.get("dependency_chains", fb.dependency_chains),
        code_skeleton=parsed.get("code_skeleton", fb.code_skeleton),
        source_doc_issues=parsed.get("source_doc_issues", fb.source_doc_issues),
        data_models=parsed.get("data_models", fb.data_models),
        error_catalog=parsed.get("error_catalog", fb.error_catalog),
        prerequisites=parsed.get("prerequisites", fb.prerequisites),
        data_access_patterns=parsed.get("data_access_patterns", fb.data_access_patterns),
        endpoint_coverage=parsed.get("endpoint_coverage", fb.endpoint_coverage),
        integration_data_flows=parsed.get("integration_data_flows", fb.integration_data_flows),
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
        "data_models": previous.data_models,
        "error_catalog": previous.error_catalog,
        "prerequisites": previous.prerequisites,
        "data_access_patterns": previous.data_access_patterns,
        "endpoint_coverage": previous.endpoint_coverage,
        "integration_data_flows": previous.integration_data_flows,
    }, indent=2, ensure_ascii=False)

    prompt = _CORRECTION_PROMPT.format(
        errors="\n".join(f"- {e}" for e in errors),
        previous_result=previous_json,
    )

    raw, llm_usage, call_ms = _call_llm_sync(
        "You are an API integration analyst. Fix the errors in the previous analysis.",
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

    return _lifecycle_from_parsed(parsed, usage, fallback=previous)


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
            logger.warning(
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
# Merge helpers
# ---------------------------------------------------------------------------

_MERGE_BATCH_SIZE = 10


def _lc_to_merge_dict(lc) -> dict:
    """Convert an ApiLifecycle ORM object to a dict suitable for the merge prompt."""
    return {
        "document_id": lc.document_id,
        "phases": lc.phases or [],
        "unique_patterns": lc.unique_patterns or [],
        "dependency_chains": lc.dependency_chains or [],
        "code_skeleton": lc.code_skeleton or "",
        "data_models": lc.data_models or [],
        "error_catalog": lc.error_catalog or [],
        "prerequisites": lc.prerequisites or [],
        "data_access_patterns": lc.data_access_patterns or [],
        "endpoint_coverage": lc.endpoint_coverage or [],
        "integration_data_flows": lc.integration_data_flows or {},
    }


def _result_to_merge_dict(result: LifecycleResult) -> dict:
    """Convert a LifecycleResult to a dict suitable for the merge prompt."""
    return {
        "phases": result.phases,
        "unique_patterns": result.unique_patterns,
        "dependency_chains": result.dependency_chains,
        "code_skeleton": result.code_skeleton,
        "data_models": result.data_models,
        "error_catalog": result.error_catalog,
        "prerequisites": result.prerequisites,
        "data_access_patterns": result.data_access_patterns,
        "endpoint_coverage": result.endpoint_coverage,
        "integration_data_flows": result.integration_data_flows,
    }


def _merge_batch(batch_data: list[dict], usage: LifecycleUsage) -> LifecycleResult | None:
    """Merge a single batch of lifecycle dicts via one LLM call."""
    merge_prompt = _MERGE_PROMPT.format(
        count=len(batch_data),
        lifecycles_json=json.dumps(batch_data, indent=2, ensure_ascii=False),
    )

    raw, llm_usage, call_ms = _call_llm_sync(
        "You are an API integration analyst. Merge multiple lifecycle analyses into one.",
        merge_prompt,
    )
    usage.prompt_tokens += llm_usage.get("prompt_tokens", 0)
    usage.completion_tokens += llm_usage.get("completion_tokens", 0)
    usage.thinking_tokens += llm_usage.get("thinking_tokens", 0)
    usage.llm_ms += call_ms
    usage.llm_calls += 1

    parsed = _parse_lifecycle_json(raw)
    if parsed is None:
        return None

    return _lifecycle_from_parsed(parsed, usage)


def _hierarchical_merge(all_data: list[dict], usage: LifecycleUsage) -> LifecycleResult | None:
    """Recursively merge lifecycle dicts in batches of _MERGE_BATCH_SIZE.

    Level 0: merge raw doc lifecycles in batches → intermediate results
    Level 1+: merge intermediate results in batches → until 1 remains
    """
    current_level = all_data

    level = 0
    while len(current_level) > 1:
        logger.info(
            "Hierarchical merge level %d: %d items in batches of %d",
            level, len(current_level), _MERGE_BATCH_SIZE,
        )

        next_level: list[dict] = []
        for i in range(0, len(current_level), _MERGE_BATCH_SIZE):
            batch = current_level[i : i + _MERGE_BATCH_SIZE]

            if len(batch) == 1:
                next_level.append(batch[0])
                continue

            result = _merge_batch(batch, usage)
            if result is None:
                logger.warning("Batch merge failed at level %d, batch %d", level, i // _MERGE_BATCH_SIZE)
                next_level.append(batch[0])
                continue

            next_level.append(_result_to_merge_dict(result))

        current_level = next_level
        level += 1

    if not current_level:
        return None

    final = current_level[0]
    return _lifecycle_from_parsed(final, usage)


# ---------------------------------------------------------------------------
# Public API: per-product merge
# ---------------------------------------------------------------------------

def merge_product_lifecycle_sync(
    product_id: int,
    session,
) -> tuple[LifecycleResult, list[DocIssue]]:
    """Merge all document-level lifecycles for a product into one.

    Uses hierarchical merge when document count exceeds _MERGE_BATCH_SIZE:
    splits into batches, merges each batch, then merges the batch results
    recursively until one final lifecycle remains.

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
            data_models=lc.data_models or [],
            error_catalog=lc.error_catalog or [],
            prerequisites=lc.prerequisites or [],
            data_access_patterns=lc.data_access_patterns or [],
            endpoint_coverage=lc.endpoint_coverage or [],
            integration_data_flows=lc.integration_data_flows or {},
            usage=usage,
        )
        usage.analysis_ms = round((time.perf_counter() - t0) * 1000, 1)
        return result, []

    lifecycles_data = [_lc_to_merge_dict(lc) for lc in doc_lifecycles]

    if len(lifecycles_data) <= _MERGE_BATCH_SIZE:
        result = _merge_batch(lifecycles_data, usage)
    else:
        logger.info(
            "Starting hierarchical merge for product %d: %d documents",
            product_id, len(lifecycles_data),
        )
        result = _hierarchical_merge(lifecycles_data, usage)

    if result is None:
        return LifecycleResult(
            validation_issues=[{"error": "Failed to parse merged lifecycle JSON"}],
            usage=usage,
        ), []

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
