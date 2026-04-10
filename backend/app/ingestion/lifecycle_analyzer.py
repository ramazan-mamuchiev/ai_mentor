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
from app.utils.retry import retry_call

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
    fallback_used: bool = False

    def add_llm_call(self, llm_usage: dict, call_ms: float) -> None:
        """Accumulate a single _call_llm_sync result."""
        self.prompt_tokens += llm_usage.get("prompt_tokens", 0)
        self.completion_tokens += llm_usage.get("completion_tokens", 0)
        self.thinking_tokens += llm_usage.get("thinking_tokens", 0)
        self.llm_ms += call_ms
        self.llm_calls += 1
        used = llm_usage.get("model", "")
        if used and used != self.model:
            self.fallback_used = True


DOC_SCOPE_VENDOR = "vendor_specific"
DOC_SCOPE_PROTOCOL = "industry_protocol"
DOC_SCOPE_DEVICE_FAMILY = "device_family"
DOC_SCOPE_UNKNOWN = "unknown"

_PROTOCOL_KEYWORDS = frozenset({
    "cgi", "onvif", "rtsp", "sip", "isapi", "modbus", "bacnet", "opc",
    "mqtt", "snmp", "psia", "gb/t", "gb28181", "wsdl", "soap",
    "common gateway interface", "generic", "protocol specification",
})


def detect_doc_scope(product_name: str, chunk_contents: list[str]) -> str:
    """Detect whether documentation describes a vendor-specific API or a generic protocol."""
    name_lower = product_name.lower()
    if any(kw in name_lower for kw in _PROTOCOL_KEYWORDS):
        return DOC_SCOPE_PROTOCOL

    full_text_lower = " ".join(chunk_contents[:20]).lower()
    protocol_signals = sum(1 for kw in _PROTOCOL_KEYWORDS if kw in full_text_lower)
    vendor_signals = sum(
        1 for kw in ("api key", "api_key", "sdk", "cloud", "saas", "platform", "dashboard")
        if kw in full_text_lower
    )
    if protocol_signals >= 3 and vendor_signals < 2:
        return DOC_SCOPE_PROTOCOL
    if vendor_signals >= 2:
        return DOC_SCOPE_VENDOR
    return DOC_SCOPE_UNKNOWN


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
    doc_scope: str = DOC_SCOPE_UNKNOWN
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

GROUNDING RULES (apply to ALL sections below):
- NEVER invent information. Every endpoint path, field name, error code, and parameter
  MUST come directly from the documentation text you are given.
- If the documentation does not describe something, leave the field empty or omit the
  entry entirely. Do NOT guess or extrapolate.
- Use EXACT endpoint paths as they appear in the documentation. Do NOT normalize,
  shorten, or modify them (e.g. if the doc says "/api/v1/cameras", write exactly that).
- Cross-reference between sections: every api_call in phases must appear in
  endpoint_coverage; every model in data_models.used_in must reference a real phase
  api_call; every error_catalog.phase must match a real phase_name.

Analyze the document and return a JSON object with ALL of the following sections:

## 1. phases
An ordered array of integration steps. Each step:
- phase_name: "setup" | "authentication" | "initialization" | "operation" | "cleanup" | "other"
- step_order: integer (global ordering across all phases)
- action: what the developer does (human-readable)
- api_call: the endpoint path WITHOUT the HTTP method prefix (e.g. "/auth/token", "/v1/login", "rpc Login"). The HTTP method goes ONLY in http_method. Empty string if no API call.
- http_method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE" | "" (empty if not HTTP)
- content_type: request content type (e.g. "application/json", "multipart/form-data"). Empty string if not applicable.
- inputs: array of what this step needs (from previous steps or external config)
- outputs: array of what this step produces (tokens, session IDs, object IDs)
- output_used_by: array of later step actions that consume this output
- is_required: boolean
- notes: unique details, gotchas, quirks specific to THIS API
- request_example: minimal but complete request body/params as a string (JSON, form fields, or query params). Empty string if no request body.
- response_example: key fields of the response as a string (JSON with important fields). Empty string if unknown.

IMPORTANT for phases:
- api_call must contain ONLY the path, never the HTTP method (e.g. "/api/v1/cameras", NOT "POST /api/v1/cameras").
  The HTTP method belongs exclusively in the http_method field.
- api_call must use the FULL path exactly as in the docs (e.g. "/api/v1/cameras", NOT "/cameras").
- inputs and outputs MUST use consistent names across phases — if phase A outputs "session_token",
  phase B that needs it must list "session_token" in inputs (exact string match).
- output_used_by must reference real action names from later phases (exact match).

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
Array of "A must happen before B" relationships. Include BOTH:
- Explicit dependencies (e.g. login returns a token required by all other calls)
- Implicit data dependencies (e.g. if endpoint B requires an ID/parameter that can only
  be obtained from the response of endpoint A, that is a dependency even if the docs
  don't state it explicitly)

For each dependency:
- from_action: action name (must match a phase action)
- to_action: action name (must match a phase action)
- data_flow: what data passes between them (e.g. "circle_id", "device_id", "access_token")
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

CRITICAL code_skeleton rules:
- Every endpoint path in code_skeleton MUST exist in your phases array above.
- NEVER invent endpoint paths. If you are unsure about a path, OMIT it.
- NEVER fabricate request/response field names. Use ONLY field names from the docs.
- If the documentation is incomplete (e.g. no response schema), add a comment
  "# TODO: response schema not documented" instead of guessing.

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
  "missing_enum_values" — a field that semantically represents a finite set of choices (command names, event types, status codes, device types) is typed as plain "string" or "integer" without listing the allowed values
  "missing_pagination_docs" — list endpoint without pagination description
  "version_mismatch" — documentation references API version that doesn't match the described behavior
  "undocumented_header" — header used in examples but never described
  "incomplete_example" — code example is truncated, missing imports, or uses unexplained placeholders
  "stale_url" — URL in documentation that appears non-functional (http instead of https, placeholder domain)
  "missing_rate_limit_docs" — rate limiting mentioned but specific limits not documented

- severity: "critical" | "error" | "warning" | "info"
  critical: contradictions that make integration impossible without experimentation (contradictory_params, phantom_endpoint with conflicting docs)
  error: API integration WILL fail without this info (phantom_endpoint, missing_auth_docs, broken_reference)
  warning: code will be incorrect/fragile (missing_request_body, missing_response_schema, missing_error_docs, incomplete_example, missing_enum_values)
  info: inconvenience or potential issue (ambiguous_type, stale_url, version_mismatch, undocumented_header, missing_pagination_docs, missing_rate_limit_docs)

- description: what the issue is
- affected_entity: which endpoint/model/section is affected
- suggestion: how to resolve it

IMPORTANT: Do NOT repeat the same issue multiple times. Each unique (description, affected_entity)
pair should appear ONLY ONCE in the array. If the same problem affects multiple endpoints,
list them together in one entry (e.g. affected_entity: "All endpoints").

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

IMPORTANT for data_models:
- used_in array must contain EXACT api_call strings from your phases (e.g. "/api/v1/cameras", path only, no HTTP method).
- Include ALL fields mentioned in the documentation, even optional ones.
- For fields with enum constraints, list ALL enum values found in docs.

## 7. error_catalog
Array of error responses the API can return:
- http_status: integer (e.g. 400, 401, 403, 404, 409, 429, 500, 503)
- error_code: API-specific error code string if any (e.g. "CAMERA_OFFLINE", "TOKEN_EXPIRED"). Empty string if none.
- meaning: what this error means in context of this API
- phase: which phase_name this error is most likely in ("authentication", "operation", etc.)
- recovery_action: "retry" | "re_auth" | "abort" | "wait" | "other"
- retry_after_seconds: integer or null (e.g. 60 for rate limiting)

Extract ALL error codes/statuses mentioned anywhere in the documentation.

IMPORTANT for error_catalog:
- phase must be one of the phase_name values you used in your phases array.
- Collect errors from ALL sections of the documentation, not just a dedicated error section.
- If an endpoint description mentions "returns 404 if not found", that is an error_catalog entry.
- If authentication is present, include a 401 entry with recovery_action "re_auth".

## 8. prerequisites
Array of things a developer needs BEFORE making any API call:
- name: identifier (e.g. "BASE_URL", "API_KEY", "CLIENT_CERTIFICATE", "SDK_LIBRARY")
- type: "url" | "secret" | "file" | "enum" | "string" | "sdk"
- description: what it is and why it's needed
- example_value: a realistic example (use placeholder domains like "example.com" for URLs, "your-api-key-here" for secrets)
- how_to_obtain: where/how the developer gets this (admin panel, registration, download, etc.)

IMPORTANT for prerequisites:
- Each prerequisite name should appear in at least one phase's inputs array.
- example_value must be realistic (e.g. "https://vms.example.com:8080", not "xxx").

## 9. data_access_patterns
Array of patterns for retrieving collections/streams of data:
- pattern_type: "pagination_offset" | "pagination_cursor" | "streaming_sse" | "websocket" | "long_polling" | "batch" | "callback_webhook" | "none"
- endpoint: which endpoint uses this pattern
- mechanism: how it works (parameter names, header names, response fields for next page, etc.)
- code_hint: 2-3 line Python code showing the pattern

If the API has list endpoints but pagination is not documented, still include an entry
with pattern_type "none" and note it in source_doc_issues as "missing_pagination_docs".

IMPORTANT for data_access_patterns:
- endpoint must match an api_call from your phases array (exact path).
- code_hint must use the same endpoint path as in the phase.

## 10. endpoint_coverage
Array assessing documentation completeness for EACH endpoint found in the docs:
- endpoint: the endpoint path (e.g. "/api/v1/cameras")
- method: HTTP method (e.g. "POST")
- has_request_body_docs: boolean — is the request body/params described?
  For methods that normally have no body (GET, DELETE, HEAD, OPTIONS) set this to true
  if query parameters are documented, OR if the method genuinely needs no params.
  Only set false when the method SHOULD have documented params/body but doesn't.
- has_response_docs: boolean — is the response format described?
- has_error_docs: boolean — are error responses described?
- has_example: boolean — is there ANY code example, curl command, SDK sample, or
  auto-generated code stub (e.g. "Usage and SDK Samples" sections, Swagger/OpenAPI
  generated examples)? Set true even for boilerplate/generated examples.
- completeness: float 0.0-1.0 — compute as follows:
  * For methods with a request body (POST, PUT, PATCH): average of ALL 4 boolean fields.
  * For methods without a body (GET, DELETE, HEAD, OPTIONS): average of has_response_docs,
    has_error_docs, and has_example ONLY (3 fields). Do NOT penalise for missing request
    body docs when the method inherently has no body.
- missing: array of strings describing what's missing (e.g. ["response_schema", "error_codes", "example"])

Be honest and strict in this assessment. This helps developers know which parts
of the documentation to trust and where they need to be careful.

IMPORTANT for endpoint_coverage:
- Use the EXACT endpoint paths as they appear in the documentation.
- Every api_call from your phases must have a matching endpoint_coverage entry.
- Do NOT normalize, shorten, or modify endpoint paths.

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
IMPORTANT: Do NOT use parentheses (), curly braces {{}}, or square brackets [] inside
edge labels or node labels — these are Mermaid syntax characters and will cause parse errors.
Replace them with nothing or rephrase (e.g. "POST /login credentials" instead of "POST /login (credentials)").
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
- NEVER invent new endpoints, data models, or error codes during merge.
  Only combine what already exists in the individual analyses.
- Ensure cross-referential integrity: every data_models.used_in must match a phase api_call,
  every error_catalog.phase must match a phase_name, every data_access_patterns.endpoint
  must match a phase api_call.

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

IMPORTANT correction rules:
- If an error says an endpoint/entity is "not found in source documentation", REMOVE it
  entirely rather than trying to fix it. Only use data explicitly present in the docs.
- If an error says a reference does not match (e.g. used_in, phase, output_used_by),
  fix it to match an existing entry or remove the reference.
- NEVER invent new endpoints, field names, or error codes to fix a validation error.

Return the corrected full JSON object with the same structure (phases, unique_patterns, \
dependency_chains, code_skeleton, source_doc_issues, data_models, error_catalog, \
prerequisites, data_access_patterns, endpoint_coverage, integration_data_flows).

Return ONLY valid JSON. Do NOT include any text outside the JSON object.
"""


# ---------------------------------------------------------------------------
# LLM calls (sync — for Celery workers)
# ---------------------------------------------------------------------------

def _call_llm_sync(
    system: str,
    user: str,
    *,
    json_mode: bool = True,
    model: str | None = None,
) -> tuple[str, dict, float]:
    """Synchronous LLM call with automatic fallback to a lighter model.

    Tries the primary model (``settings.lifecycle_analysis_model``) with retries.
    If all retries are exhausted on a retryable error (429/5xx/timeout) and a
    fallback model is configured, transparently retries with the fallback model.

    Returns (response_text, usage_dict, llm_ms).
    usage_dict includes prompt_tokens, completion_tokens, thinking_tokens, and
    the ``model`` that actually produced the response.
    """
    primary_model = model or settings.lifecycle_analysis_model
    fallback_model = settings.lifecycle_analysis_fallback_model
    url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.gemini_api_key}",
    }

    _retryable_statuses = {429, 500, 502, 503, 504}

    def _is_retryable(exc: Exception) -> bool:
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code in _retryable_statuses
        return isinstance(exc, (httpx.ConnectError, httpx.ReadTimeout))

    def _do_call(use_model: str) -> dict:
        payload: dict = {
            "model": use_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
            "max_tokens": settings.lifecycle_analysis_max_output_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        with httpx.Client(timeout=httpx.Timeout(180.0, connect=10.0)) as client:
            def _do_request():
                resp = client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                return resp.json()

            return retry_call(
                _do_request,
                max_retries=3,
                base_delay=5.0,
                max_delay=30.0,
                is_retryable=_is_retryable,
                label=f"lifecycle_llm[{use_model}]",
            )

    t0 = time.perf_counter()
    used_model = primary_model
    try:
        data = _do_call(primary_model)
    except Exception as primary_exc:
        can_fallback = (
            fallback_model
            and fallback_model != primary_model
            and _is_retryable(primary_exc)
        )
        if not can_fallback:
            raise
        logger.warning(
            "Primary lifecycle model exhausted retries, falling back",
            extra={
                "primary_model": primary_model,
                "fallback_model": fallback_model,
                "error": str(primary_exc)[:300],
            },
        )
        used_model = fallback_model
        data = _do_call(fallback_model)

    llm_ms = round((time.perf_counter() - t0) * 1000, 1)

    text = data["choices"][0]["message"]["content"].strip()
    raw_usage = data.get("usage", {})

    usage = {
        "prompt_tokens": raw_usage.get("prompt_tokens", 0),
        "completion_tokens": raw_usage.get("completion_tokens", 0),
        "thinking_tokens": raw_usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0)
                           or raw_usage.get("thinking_tokens", 0),
        "model": used_model,
    }

    if used_model != primary_model:
        logger.info(
            "Lifecycle LLM call completed with fallback model",
            extra={"primary_model": primary_model, "used_model": used_model, "llm_ms": llm_ms},
        )

    return text, usage, llm_ms


_NO_BODY_METHODS = frozenset({"GET", "DELETE", "HEAD", "OPTIONS"})

# Weights: response docs matter most, then request, then errors, then examples.
_W_RESPONSE = 0.35
_W_REQUEST = 0.25
_W_ERRORS = 0.20
_W_EXAMPLE = 0.20

# For no-body methods the request weight is redistributed.
_W_RESPONSE_NB = 0.40
_W_ERRORS_NB = 0.30
_W_EXAMPLE_NB = 0.30


def _recalc_endpoint_completeness(
    coverage: list[dict],
    *,
    has_global_error_catalog: bool = False,
    doc_scope: str = DOC_SCOPE_UNKNOWN,
) -> list[dict]:
    """Recalculate completeness scores with weighted criteria.

    If the product has a global error_catalog but per-endpoint error docs are
    missing, grant partial credit (0.5) for has_error_docs.

    For industry_protocol doc_scope, errors and examples carry less weight
    because protocol specs intentionally leave implementation details to vendors.
    """
    is_protocol = doc_scope == DOC_SCOPE_PROTOCOL

    result = []
    for entry in coverage:
        if not isinstance(entry, dict):
            result.append(entry)
            continue
        entry = dict(entry)
        method = (entry.get("method") or "").upper()
        resp = 1.0 if entry.get("has_response_docs") else 0.0
        errs_raw = entry.get("has_error_docs")
        if errs_raw:
            errs = 1.0
        elif has_global_error_catalog:
            errs = 0.5
        else:
            errs = 0.0
        ex = 1.0 if entry.get("has_example") else 0.0

        if method in _NO_BODY_METHODS:
            if is_protocol:
                score = resp * 0.50 + errs * 0.25 + ex * 0.25
            else:
                score = resp * _W_RESPONSE_NB + errs * _W_ERRORS_NB + ex * _W_EXAMPLE_NB
        else:
            req = 1.0 if entry.get("has_request_body_docs") else 0.0
            if is_protocol:
                score = req * 0.30 + resp * 0.40 + errs * 0.15 + ex * 0.15
            else:
                score = req * _W_REQUEST + resp * _W_RESPONSE + errs * _W_ERRORS + ex * _W_EXAMPLE
        entry["completeness"] = round(score, 2)
        result.append(entry)
    return result


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


_MERMAID_EDGE_LABEL_RE = re.compile(r"(\-\->|===|~~~|\-\.\->?)\|([^|]+)\|")
_MERMAID_ALT_EDGE_RE = re.compile(r" --\s+([^-][^>]*?)\s*-->")
_MERMAID_NODE_LABEL_RE = re.compile(r"\[([^\]]+)\]")


def _sanitize_mermaid(diagram: str) -> str:
    """Remove Mermaid-breaking characters from edge and node labels."""
    def _strip(s: str) -> str:
        for ch in '(){}|<>"':
            s = s.replace(ch, "")
        return s

    def _clean_edge(m: re.Match) -> str:
        arrow, label = m.group(1), m.group(2)
        return f"{arrow}|{_strip(label)}|"

    def _clean_alt_edge(m: re.Match) -> str:
        return f" -->|{_strip(m.group(1).strip())}|"

    def _clean_node(m: re.Match) -> str:
        return f"[{_strip(m.group(1))}]"

    result = _MERMAID_EDGE_LABEL_RE.sub(_clean_edge, diagram)
    result = _MERMAID_ALT_EDGE_RE.sub(_clean_alt_edge, result)
    result = _MERMAID_NODE_LABEL_RE.sub(_clean_node, result)
    return result


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

    phases = [p for p in result.phases if isinstance(p, dict)]
    if not phases:
        lifecycle_errors.append("All phase entries are malformed (expected dicts). Re-extract phases.")
        return lifecycle_errors, doc_issues

    known_endpoints = _extract_endpoints_from_chunks(chunk_contents)

    phase_actions = {p.get("action", "") for p in phases}

    for phase in phases:
        api_call = phase.get("api_call", "")
        if api_call and "/" in api_call:
            normalized = _normalize_endpoint(api_call)
            if known_endpoints and not any(_endpoints_match(normalized, ep) for ep in known_endpoints):
                lifecycle_errors.append(
                    f"Phase '{phase.get('action')}' references endpoint '{api_call}' "
                    f"which was not found in the source documentation."
                )

    has_auth_phase = any(
        p.get("phase_name") in ("authentication", "setup")
        and any(kw in (p.get("action", "") + p.get("notes", "")).lower()
                for kw in ("auth", "login", "token", "key", "credential", "session"))
        for p in phases
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
        if not isinstance(dep, dict):
            continue
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
        for p in phases:
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
            if known_endpoints and not any(_endpoints_match(ep_norm, ke) for ke in known_endpoints):
                phase_ep_calls = {
                    _normalize_endpoint(p["api_call"])
                    for p in phases if p.get("api_call")
                }
                if not any(_endpoints_match(ep_norm, pe) for pe in phase_ep_calls):
                    lifecycle_errors.append(
                        f"code_skeleton references endpoint '{ep_match.strip()}' "
                        f"not found in phases or source documentation."
                    )

    # --- New validations for enhanced analysis ---

    if known_endpoints and result.endpoint_coverage:
        covered = {_normalize_endpoint(ec.get("endpoint", ""))
                   for ec in result.endpoint_coverage if isinstance(ec, dict) and ec.get("endpoint")}
        matched = sum(1 for ke in known_endpoints if any(_endpoints_match(ke, ce) for ce in covered))
        coverage_ratio = matched / len(known_endpoints)
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
    for phase in phases:
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
        components = [c for c in idf.get("components", []) if isinstance(c, dict)]
        flows = [f for f in idf.get("flows", []) if isinstance(f, dict)]
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

    # --- Cross-section validation (capped at 10 errors to avoid overloading correction) ---
    cross_errors: list[str] = []
    phase_api_calls = {_normalize_endpoint(p["api_call"]) for p in phases if p.get("api_call")}
    phase_names_set = {p.get("phase_name", "") for p in phases}

    # data_models.used_in vs phases
    for model in result.data_models:
        if not isinstance(model, dict):
            continue
        for ref in model.get("used_in", []):
            if ref and "/" in ref:
                ref_norm = _normalize_endpoint(ref)
                if not any(_endpoints_match(ref_norm, pa) for pa in phase_api_calls):
                    cross_errors.append(
                        f"data_models '{model.get('model_name', '?')}' references "
                        f"used_in '{ref}' which does not match any phase api_call."
                    )

    # error_catalog.phase vs phase_names
    for err in result.error_catalog:
        if not isinstance(err, dict):
            continue
        err_phase = err.get("phase", "")
        if err_phase and err_phase not in phase_names_set:
            cross_errors.append(
                f"error_catalog entry (HTTP {err.get('http_status', '?')}) references "
                f"phase '{err_phase}' not found among extracted phase_names."
            )

    # Auth phases should have 401 in error_catalog
    has_auth_related = any(
        p.get("phase_name") in ("authentication", "setup")
        for p in phases
    )
    if has_auth_related and result.error_catalog:
        has_401 = any(e.get("http_status") == 401 for e in result.error_catalog if isinstance(e, dict))
        if not has_401:
            cross_errors.append(
                "Authentication phases exist but error_catalog has no HTTP 401 entry. "
                "Add a 401 Unauthorized error with recovery_action 're_auth'."
            )

    # data_access_patterns.endpoint vs phases
    for pat in result.data_access_patterns:
        if not isinstance(pat, dict):
            continue
        pat_ep = pat.get("endpoint", "")
        if pat_ep and "/" in pat_ep:
            pat_norm = _normalize_endpoint(pat_ep)
            if not any(_endpoints_match(pat_norm, pa) for pa in phase_api_calls):
                cross_errors.append(
                    f"data_access_patterns entry '{pat.get('pattern_type', '?')}' references "
                    f"endpoint '{pat_ep}' not found in phases."
                )

    # endpoint_coverage completeness vs phases
    if result.endpoint_coverage and phase_api_calls:
        coverage_eps = {_normalize_endpoint(ec.get("endpoint", ""))
                        for ec in result.endpoint_coverage if isinstance(ec, dict) and ec.get("endpoint")}
        for pa in phase_api_calls:
            if not any(_endpoints_match(pa, ce) for ce in coverage_eps):
                cross_errors.append(
                    f"Phase endpoint '{pa}' is missing from endpoint_coverage. "
                    f"Add a coverage entry for it."
                )

    # unique_patterns rate_limit vs error_catalog 429
    if result.unique_patterns:
        mentions_rate_limit = any(
            "rate" in (p.get("pattern", "") + p.get("description", "")).lower()
            for p in result.unique_patterns if isinstance(p, dict)
        )
        if mentions_rate_limit and result.error_catalog:
            has_429 = any(e.get("http_status") == 429 for e in result.error_catalog if isinstance(e, dict))
            if not has_429:
                cross_errors.append(
                    "unique_patterns mentions rate limiting but error_catalog has no "
                    "HTTP 429 entry. Add a 429 error with recovery_action 'wait'."
                )

    # phases output_used_by should reference real actions
    for phase in phases:
        for ref_action in phase.get("output_used_by", []):
            if ref_action and ref_action not in phase_actions:
                cross_errors.append(
                    f"Phase '{phase.get('action', '?')}' output_used_by references "
                    f"'{ref_action}' which is not found among phase actions."
                )

    lifecycle_errors.extend(cross_errors[:10])

    # Detect string fields that should be enums (missing_enum_values)
    _ENUM_HINT_NAMES = {"command_name", "command", "event_type", "type", "status",
                        "action", "mode", "state", "direction", "severity", "role"}
    for model in result.data_models:
        if not isinstance(model, dict):
            continue
        for fld in model.get("fields", []):
            if not isinstance(fld, dict):
                continue
            fname = (fld.get("name") or "").lower()
            ftype = (fld.get("type") or "").lower()
            constraints = fld.get("constraints") or ""
            if (fname in _ENUM_HINT_NAMES
                    and ftype in ("string", "integer", "int")
                    and "enum" not in constraints.lower()
                    and not constraints.strip()):
                doc_issues.append(DocIssue(
                    issue_type="missing_enum_values",
                    severity="warning",
                    description=(
                        f"Field '{fld.get('name')}' in model '{model.get('model_name', '?')}' "
                        f"is typed as '{fld.get('type')}' but likely represents a finite set of "
                        f"choices. The allowed values are not documented."
                    ),
                    affected_entity=model.get("model_name"),
                    suggestion=f"Document all valid values for '{fld.get('name')}' as an enum constraint.",
                ))

    for issue in result.source_doc_issues:
        doc_issues.append(DocIssue(
            issue_type=issue.get("issue_type", "other"),
            severity=issue.get("severity", "warning"),
            description=issue.get("description", ""),
            affected_entity=issue.get("affected_entity"),
            suggestion=issue.get("suggestion"),
        ))

    # Deduplicate doc_issues by (description, affected_entity)
    seen_doc_issues: set[str] = set()
    unique_doc_issues: list[DocIssue] = []
    for di in doc_issues:
        key = (di.description or "").strip().lower() + "|" + (di.affected_entity or "").strip().lower()
        if key not in seen_doc_issues:
            seen_doc_issues.add(key)
            unique_doc_issues.append(di)

    return lifecycle_errors, unique_doc_issues


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------

def _extract_lifecycle(
    doc_text: str,
    usage: LifecycleUsage,
    *,
    doc_scope: str = DOC_SCOPE_UNKNOWN,
) -> LifecycleResult:
    """Single LLM call to extract lifecycle from document text."""
    logger.info("Lifecycle extraction LLM call starting",
                extra={"doc_len": len(doc_text), "model": settings.lifecycle_analysis_model})
    raw, llm_usage, call_ms = _call_llm_sync(_EXTRACTION_PROMPT, doc_text)
    usage.add_llm_call(llm_usage, call_ms)
    logger.info("Lifecycle extraction LLM call completed",
                extra={"call_ms": call_ms,
                        "prompt_tokens": llm_usage.get("prompt_tokens", 0),
                        "completion_tokens": llm_usage.get("completion_tokens", 0),
                        "model": llm_usage.get("model", ""),
                        "response_len": len(raw) if raw else 0})

    parsed = _parse_lifecycle_json(raw)
    if parsed is None:
        return LifecycleResult(
            validation_issues=[{"error": "Failed to parse LLM response as JSON"}],
            usage=usage,
        )

    return _lifecycle_from_parsed(parsed, usage, doc_scope=doc_scope)


def _dedup_source_doc_issues(issues: list) -> list[dict]:
    """Deduplicate source_doc_issues by (description, affected_entity)."""
    seen: set[str] = set()
    result: list[dict] = []
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        key = (issue.get("description", "").strip().lower()
               + "|" + (issue.get("affected_entity") or "").strip().lower())
        if key not in seen:
            seen.add(key)
            result.append(issue)
    return result


def _lifecycle_from_parsed(
    parsed: dict,
    usage: LifecycleUsage,
    fallback: LifecycleResult | None = None,
    *,
    doc_scope: str = DOC_SCOPE_UNKNOWN,
) -> LifecycleResult:
    """Build LifecycleResult from parsed JSON, with optional fallback for corrections."""
    fb = fallback or LifecycleResult()
    idf = parsed.get("integration_data_flows", fb.integration_data_flows)
    if isinstance(idf, dict) and idf.get("diagram_mermaid"):
        idf["diagram_mermaid"] = _sanitize_mermaid(idf["diagram_mermaid"])

    error_catalog = parsed.get("error_catalog", fb.error_catalog)
    has_global_errors = bool(error_catalog)

    return LifecycleResult(
        phases=parsed.get("phases", fb.phases),
        unique_patterns=parsed.get("unique_patterns", fb.unique_patterns),
        dependency_chains=parsed.get("dependency_chains", fb.dependency_chains),
        code_skeleton=parsed.get("code_skeleton", fb.code_skeleton),
        source_doc_issues=_dedup_source_doc_issues(parsed.get("source_doc_issues", fb.source_doc_issues)),
        data_models=parsed.get("data_models", fb.data_models),
        error_catalog=error_catalog,
        prerequisites=parsed.get("prerequisites", fb.prerequisites),
        data_access_patterns=parsed.get("data_access_patterns", fb.data_access_patterns),
        endpoint_coverage=_recalc_endpoint_completeness(
            parsed.get("endpoint_coverage", fb.endpoint_coverage),
            has_global_error_catalog=has_global_errors,
            doc_scope=doc_scope,
        ),
        integration_data_flows=idf,
        doc_scope=doc_scope or fb.doc_scope,
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
    usage.add_llm_call(llm_usage, call_ms)

    parsed = _parse_lifecycle_json(raw)
    if parsed is None:
        return previous

    return _lifecycle_from_parsed(parsed, usage, fallback=previous, doc_scope=previous.doc_scope)


def _build_grounded_skeleton(result: LifecycleResult, language: str = "python") -> str:
    """Build a deterministic code skeleton from validated phases and metadata.

    Used as a fallback when LLM-generated skeleton fails validation.
    Supports: python, csharp, cpp, go, curl, java, javascript.
    """
    builder = _GROUNDED_SKELETON_BUILDERS.get(language, _build_grounded_skeleton_python)
    return builder(result)


def _prereq_vars(result: LifecycleResult) -> list[tuple[str, str]]:
    """Extract (VAR_NAME, example_value) pairs from prerequisites."""
    pairs = []
    for prereq in result.prerequisites:
        name = prereq.get("name", "UNKNOWN").upper().replace(" ", "_")
        example = prereq.get("example_value", "...")
        pairs.append((name, example))
    return pairs


def _base_url_var(result: LifecycleResult) -> str | None:
    url_prereq = next(
        (p for p in result.prerequisites if p.get("type") == "url"),
        None,
    )
    return url_prereq["name"].upper().replace(" ", "_") if url_prereq else None


def _sorted_phases(result: LifecycleResult) -> list[dict]:
    return sorted(result.phases, key=lambda p: p.get("step_order", 999))


def _retry_codes(result: LifecycleResult) -> list[int]:
    return sorted({
        e.get("http_status") for e in result.error_catalog
        if e.get("recovery_action") in ("retry", "wait") and e.get("http_status")
    })


def _phase_parts(phase: dict) -> tuple[str, str, str, str]:
    """Return (action, method, endpoint, req_example) for a phase."""
    api_call = phase.get("api_call", "")
    action = phase.get("action", "")
    method = phase.get("http_method", "GET").upper() or "GET"
    parts = api_call.strip().split()
    endpoint = parts[-1] if parts else api_call
    req_example = phase.get("request_example", "")
    return action, method, endpoint, req_example


# --- Python ---
def _build_grounded_skeleton_python(result: LifecycleResult) -> str:
    lines: list[str] = ["import httpx", ""]
    for name, example in _prereq_vars(result):
        lines.append(f'{name} = "{example}"')
    if result.prerequisites:
        lines.append("")

    lines.append("client = httpx.Client(")
    base = _base_url_var(result)
    if base:
        lines.append(f"    base_url={base},")
    lines.append("    timeout=30.0,")
    lines.append(")")
    lines.append("headers: dict[str, str] = {}")
    lines.append("")

    for phase in _sorted_phases(result):
        if not phase.get("api_call"):
            lines.append(f"# Step {phase.get('step_order', '?')}: {phase.get('action', '?')}")
            if phase.get("notes"):
                lines.append(f"# Note: {phase['notes']}")
            lines.append("")
            continue

        action, method, endpoint, req_example = _phase_parts(phase)
        lines.append(f"# Step {phase.get('step_order', '?')}: {action}")
        if phase.get("notes"):
            lines.append(f"# {phase['notes']}")

        call_kwargs = [f'"{endpoint}"', "headers=headers"]
        if req_example and method in ("POST", "PUT", "PATCH"):
            call_kwargs.append(f"json={req_example}")

        lines.append(f"response = client.{method.lower()}({', '.join(call_kwargs)})")
        lines.append("response.raise_for_status()")

        outputs = phase.get("outputs", [])
        if outputs:
            lines.append("data = response.json()")
            suffix = "" if phase.get("response_example") else "  # TODO: verify field name"
            for out in outputs[:3]:
                var = out.lower().replace(" ", "_").replace("-", "_")
                lines.append(f'{var} = data.get("{out}"){suffix}')

        if phase.get("phase_name") == "authentication":
            lines.append('headers["Authorization"] = f"Bearer {data.get(\'token\', \'\')}"')
        lines.append("")

    codes = _retry_codes(result)
    if codes:
        lines.append(f"# Retryable HTTP status codes: {codes}")
        lines.append("")
    lines.append("client.close()")
    return "\n".join(lines)


# --- C# ---
def _build_grounded_skeleton_csharp(result: LifecycleResult) -> str:
    lines = [
        "using System;",
        "using System.Net.Http;",
        "using System.Net.Http.Headers;",
        "using System.Text;",
        "using System.Text.Json;",
        "",
        "class Program",
        "{",
        "    static async Task Main(string[] args)",
        "    {",
    ]
    for name, example in _prereq_vars(result):
        lines.append(f'        var {name} = "{example}";')
    lines.append("")

    base = _base_url_var(result)
    if base:
        lines.append(f"        using var client = new HttpClient {{ BaseAddress = new Uri({base}) }};")
    else:
        lines.append("        using var client = new HttpClient();")
    lines.append("        client.Timeout = TimeSpan.FromSeconds(30);")
    lines.append("")

    for phase in _sorted_phases(result):
        if not phase.get("api_call"):
            lines.append(f"        // Step {phase.get('step_order', '?')}: {phase.get('action', '?')}")
            lines.append("")
            continue

        action, method, endpoint, req_example = _phase_parts(phase)
        lines.append(f"        // Step {phase.get('step_order', '?')}: {action}")

        cs_method = {"GET": "GetAsync", "POST": "PostAsync", "PUT": "PutAsync",
                     "DELETE": "DeleteAsync", "PATCH": "PatchAsync"}.get(method, "SendAsync")

        if req_example and method in ("POST", "PUT", "PATCH"):
            lines.append(f'        var content = new StringContent(@"{req_example}", Encoding.UTF8, "application/json");')
            lines.append(f'        var response = await client.{cs_method}("{endpoint}", content);')
        else:
            lines.append(f'        var response = await client.{cs_method}("{endpoint}");')
        lines.append("        response.EnsureSuccessStatusCode();")

        outputs = phase.get("outputs", [])
        if outputs:
            lines.append("        var json = await response.Content.ReadAsStringAsync();")
            lines.append("        var data = JsonSerializer.Deserialize<JsonElement>(json);")
            for out in outputs[:3]:
                var = out[0].lower() + out[1:].replace(" ", "").replace("-", "")
                lines.append(f'        var {var} = data.GetProperty("{out}");')

        if phase.get("phase_name") == "authentication":
            lines.append('        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", data.GetProperty("token").GetString());')
        lines.append("")

    lines.append("    }")
    lines.append("}")
    return "\n".join(lines)


# --- C++ ---
def _build_grounded_skeleton_cpp(result: LifecycleResult) -> str:
    lines = [
        "#include <iostream>",
        "#include <string>",
        "#include <curl/curl.h>",
        '#include <nlohmann/json.hpp>',
        "",
        "using json = nlohmann::json;",
        "",
        "static size_t write_callback(void* contents, size_t size, size_t nmemb, std::string* out) {",
        "    out->append(static_cast<char*>(contents), size * nmemb);",
        "    return size * nmemb;",
        "}",
        "",
        "int main() {",
        "    curl_global_init(CURL_GLOBAL_DEFAULT);",
        "    CURL* curl = curl_easy_init();",
        "    if (!curl) return 1;",
        "",
    ]
    for name, example in _prereq_vars(result):
        lines.append(f'    std::string {name} = "{example}";')
    lines.append('    std::string auth_header;')
    lines.append("")

    base = _base_url_var(result)
    base_expr = base if base else '""'

    for phase in _sorted_phases(result):
        if not phase.get("api_call"):
            lines.append(f"    // Step {phase.get('step_order', '?')}: {phase.get('action', '?')}")
            lines.append("")
            continue

        action, method, endpoint, req_example = _phase_parts(phase)
        lines.append(f"    // Step {phase.get('step_order', '?')}: {action}")
        lines.append("    {")
        lines.append("        std::string response_body;")
        lines.append(f'        curl_easy_setopt(curl, CURLOPT_URL, ({base_expr} + "{endpoint}").c_str());')
        if method != "GET":
            lines.append(f'        curl_easy_setopt(curl, CURLOPT_CUSTOMREQUEST, "{method}");')
        lines.append("        curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_callback);")
        lines.append("        curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response_body);")
        lines.append("        struct curl_slist* headers = nullptr;")
        lines.append('        headers = curl_slist_append(headers, "Content-Type: application/json");')
        lines.append("        if (!auth_header.empty())")
        lines.append('            headers = curl_slist_append(headers, ("Authorization: " + auth_header).c_str());')
        if req_example and method in ("POST", "PUT", "PATCH"):
            lines.append(f'        curl_easy_setopt(curl, CURLOPT_POSTFIELDS, R"({req_example})");')
        lines.append("        curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);")
        lines.append("        CURLcode res = curl_easy_perform(curl);")
        lines.append("        curl_slist_free_all(headers);")
        lines.append('        if (res != CURLE_OK) { std::cerr << curl_easy_strerror(res) << std::endl; return 1; }')

        outputs = phase.get("outputs", [])
        if outputs:
            lines.append("        auto data = json::parse(response_body);")
            for out in outputs[:3]:
                var = out.lower().replace(" ", "_").replace("-", "_")
                lines.append(f'        auto {var} = data.value("{out}", "");')

        if phase.get("phase_name") == "authentication":
            lines.append('        auth_header = "Bearer " + data.value("token", "");')
        lines.append("    }")
        lines.append("")

    lines.append("    curl_easy_cleanup(curl);")
    lines.append("    curl_global_cleanup();")
    lines.append("    return 0;")
    lines.append("}")
    return "\n".join(lines)


# --- Go ---
def _build_grounded_skeleton_go(result: LifecycleResult) -> str:
    lines = [
        "package main",
        "",
        "import (",
        '\t"bytes"',
        '\t"encoding/json"',
        '\t"fmt"',
        '\t"io"',
        '\t"net/http"',
        '\t"time"',
        ")",
        "",
        "func main() {",
    ]
    for name, example in _prereq_vars(result):
        lines.append(f'\t{name} := "{example}"')
    lines.append(f"\tclient := &http.Client{{Timeout: 30 * time.Second}}")
    lines.append(f'\tauthToken := ""')
    base = _base_url_var(result)
    base_expr = base if base else '""'
    lines.append("")

    for phase in _sorted_phases(result):
        if not phase.get("api_call"):
            lines.append(f"\t// Step {phase.get('step_order', '?')}: {phase.get('action', '?')}")
            lines.append("")
            continue

        action, method, endpoint, req_example = _phase_parts(phase)
        lines.append(f"\t// Step {phase.get('step_order', '?')}: {action}")

        if req_example and method in ("POST", "PUT", "PATCH"):
            lines.append(f'\tbody := bytes.NewBufferString(`{req_example}`)')
            lines.append(f'\treq, err := http.NewRequest("{method}", {base_expr}+"{endpoint}", body)')
        else:
            lines.append(f'\treq, err := http.NewRequest("{method}", {base_expr}+"{endpoint}", nil)')
        lines.append('\tif err != nil { panic(err) }')
        lines.append('\treq.Header.Set("Content-Type", "application/json")')
        lines.append('\tif authToken != "" { req.Header.Set("Authorization", "Bearer "+authToken) }')
        lines.append("\tresp, err := client.Do(req)")
        lines.append("\tif err != nil { panic(err) }")
        lines.append("\tdefer resp.Body.Close()")
        lines.append('\trespBody, _ := io.ReadAll(resp.Body)')

        outputs = phase.get("outputs", [])
        if outputs:
            lines.append("\tvar data map[string]interface{}")
            lines.append("\tjson.Unmarshal(respBody, &data)")
            for out in outputs[:3]:
                var = out.lower().replace(" ", "_").replace("-", "_")
                lines.append(f'\t{var} := data["{out}"]')

        if phase.get("phase_name") == "authentication":
            lines.append('\tauthToken = fmt.Sprintf("%v", data["token"])')
        lines.append("")

    lines.append("}")
    return "\n".join(lines)


# --- cURL ---
def _build_grounded_skeleton_curl(result: LifecycleResult) -> str:
    lines = ["#!/bin/bash", "set -euo pipefail", ""]
    for name, example in _prereq_vars(result):
        lines.append(f'{name}="{example}"')
    lines.append('TOKEN=""')
    base = _base_url_var(result)
    base_var = f"${{{base}}}" if base else ""
    lines.append("")

    for phase in _sorted_phases(result):
        if not phase.get("api_call"):
            lines.append(f"# Step {phase.get('step_order', '?')}: {phase.get('action', '?')}")
            lines.append("")
            continue

        action, method, endpoint, req_example = _phase_parts(phase)
        lines.append(f"# Step {phase.get('step_order', '?')}: {action}")
        parts = [
            "RESPONSE=$(curl -s",
            f'  -X {method}',
            f'  "{base_var}{endpoint}"',
            '  -H "Content-Type: application/json"',
            '  -H "Authorization: Bearer $TOKEN"',
        ]
        if req_example and method in ("POST", "PUT", "PATCH"):
            parts.append(f"  -d '{req_example}'")
        parts.append(")")
        lines.extend(parts)

        outputs = phase.get("outputs", [])
        for out in outputs[:3]:
            var = out.upper().replace(" ", "_").replace("-", "_")
            lines.append(f'{var}=$(echo "$RESPONSE" | jq -r \'.{out}\')')

        if phase.get("phase_name") == "authentication":
            lines.append("TOKEN=$(echo \"$RESPONSE\" | jq -r '.token')")
        lines.append("")

    return "\n".join(lines)


# --- Java ---
def _build_grounded_skeleton_java(result: LifecycleResult) -> str:
    lines = [
        "import java.net.URI;",
        "import java.net.http.HttpClient;",
        "import java.net.http.HttpRequest;",
        "import java.net.http.HttpResponse;",
        "import java.time.Duration;",
        "import com.google.gson.JsonParser;",
        "",
        "public class ApiClient {",
        "    public static void main(String[] args) throws Exception {",
    ]
    for name, example in _prereq_vars(result):
        lines.append(f'        String {name} = "{example}";')
    lines.append('        String authToken = "";')
    lines.append("        var client = HttpClient.newBuilder()")
    lines.append("            .connectTimeout(Duration.ofSeconds(30))")
    lines.append("            .build();")
    base = _base_url_var(result)
    lines.append("")

    for phase in _sorted_phases(result):
        if not phase.get("api_call"):
            lines.append(f"        // Step {phase.get('step_order', '?')}: {phase.get('action', '?')}")
            lines.append("")
            continue

        action, method, endpoint, req_example = _phase_parts(phase)
        base_expr = f"{base} + " if base else ""
        lines.append(f"        // Step {phase.get('step_order', '?')}: {action}")
        lines.append(f"        var req{phase.get('step_order', 0)} = HttpRequest.newBuilder()")
        lines.append(f'            .uri(URI.create({base_expr}"{endpoint}"))')
        lines.append('            .header("Content-Type", "application/json")')
        lines.append('            .header("Authorization", "Bearer " + authToken)')
        if req_example and method in ("POST", "PUT", "PATCH"):
            lines.append(f'            .method("{method}", HttpRequest.BodyPublishers.ofString("{req_example}"))')
        else:
            lines.append(f"            .{method}()")
        lines.append("            .build();")
        lines.append(f"        var resp{phase.get('step_order', 0)} = client.send(req{phase.get('step_order', 0)}, HttpResponse.BodyHandlers.ofString());")

        outputs = phase.get("outputs", [])
        if outputs:
            lines.append(f"        var json{phase.get('step_order', 0)} = JsonParser.parseString(resp{phase.get('step_order', 0)}.body()).getAsJsonObject();")
            for out in outputs[:3]:
                var = out[0].lower() + out[1:].replace(" ", "").replace("-", "")
                lines.append(f'        var {var} = json{phase.get("step_order", 0)}.get("{out}");')

        if phase.get("phase_name") == "authentication":
            lines.append(f'        authToken = json{phase.get("step_order", 0)}.get("token").getAsString();')
        lines.append("")

    lines.append("    }")
    lines.append("}")
    return "\n".join(lines)


# --- JavaScript ---
def _build_grounded_skeleton_javascript(result: LifecycleResult) -> str:
    lines = ["// Using fetch API (Node 18+ / Browser)", ""]
    for name, example in _prereq_vars(result):
        lines.append(f'const {name} = "{example}";')
    lines.append('let authToken = "";')
    base = _base_url_var(result)
    lines.append("")
    lines.append("async function main() {")

    for phase in _sorted_phases(result):
        if not phase.get("api_call"):
            lines.append(f"  // Step {phase.get('step_order', '?')}: {phase.get('action', '?')}")
            lines.append("")
            continue

        action, method, endpoint, req_example = _phase_parts(phase)
        base_expr = f"${{{base}}}" if base else ""
        lines.append(f"  // Step {phase.get('step_order', '?')}: {action}")
        fetch_opts = [f'    method: "{method}"']
        fetch_opts.append("    headers: {")
        fetch_opts.append('      "Content-Type": "application/json",')
        fetch_opts.append('      "Authorization": `Bearer ${authToken}`,')
        fetch_opts.append("    },")
        if req_example and method in ("POST", "PUT", "PATCH"):
            fetch_opts.append(f"    body: JSON.stringify({req_example}),")
        lines.append(f"  const resp = await fetch(`{base_expr}{endpoint}`, {{")
        lines.extend(fetch_opts)
        lines.append("  });")
        lines.append("  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);")

        outputs = phase.get("outputs", [])
        if outputs:
            lines.append("  const data = await resp.json();")
            for out in outputs[:3]:
                var = out.replace(" ", "_").replace("-", "_")
                lines.append(f'  const {var} = data.{out};')

        if phase.get("phase_name") == "authentication":
            lines.append("  authToken = data.token;")
        lines.append("")

    lines.append("}")
    lines.append("")
    lines.append("main().catch(console.error);")
    return "\n".join(lines)


_GROUNDED_SKELETON_BUILDERS: dict[str, callable] = {
    "python": _build_grounded_skeleton_python,
    "csharp": _build_grounded_skeleton_csharp,
    "cpp": _build_grounded_skeleton_cpp,
    "go": _build_grounded_skeleton_go,
    "curl": _build_grounded_skeleton_curl,
    "java": _build_grounded_skeleton_java,
    "javascript": _build_grounded_skeleton_javascript,
}


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
            try:
                result = _retry_with_corrections(result, lifecycle_errors, result.usage)
            except Exception:
                logger.warning(
                    "Correction LLM call failed, accepting result with validation issues",
                    exc_info=True,
                )
                break

    result.validation_issues = [{"error": e} for e in last_errors]
    result.validation_retries = max_retries

    skeleton_errors = [e for e in last_errors if "code_skeleton" in e.lower()]
    if skeleton_errors and result.phases:
        grounded = _build_grounded_skeleton(result)
        if grounded.strip():
            result.code_skeleton = grounded
            logger.info("Replaced invalid LLM skeleton with grounded skeleton")

    return result, all_doc_issues


# ---------------------------------------------------------------------------
# Batch splitting helpers (for large documents)
# ---------------------------------------------------------------------------

_SHARED_HEADING_KEYWORDS = frozenset({
    "auth", "authentication", "authorization", "login", "overview",
    "introduction", "getting started", "general", "error", "errors",
    "error code", "status code", "prerequisites", "setup", "configuration",
    "common", "glossary", "appendix", "rate limit", "pagination",
})


def _is_shared_heading(heading: str) -> bool:
    """Heuristically detect headings that should be shared across all batches."""
    h_lower = heading.lower().strip()
    return any(kw in h_lower for kw in _SHARED_HEADING_KEYWORDS)


def _group_chunks_by_top_heading(chunks) -> dict[str, list]:
    """Group chunks by their top-level heading, preserving order."""
    sections: dict[str, list] = {}
    for c in chunks:
        top = c.heading_path.split(" > ")[0] if " > " in c.heading_path else c.heading_path
        sections.setdefault(top, []).append(c)
    return sections


def _split_chunks_into_batches(
    chunks,
    target_tokens: int,
) -> list[list]:
    """Split chunks into batches by top-level heading boundaries.

    Shared headings (auth, errors, overview) are prepended to every batch so
    each batch has enough context for a standalone lifecycle extraction.
    """
    sections = _group_chunks_by_top_heading(chunks)

    shared_chunks: list = []
    content_sections: list[tuple[str, list]] = []
    for heading, section_chunks in sections.items():
        if _is_shared_heading(heading):
            shared_chunks.extend(section_chunks)
        else:
            content_sections.append((heading, section_chunks))

    if not content_sections:
        return [list(chunks)]

    shared_tokens = sum(_estimate_tokens(c.content) for c in shared_chunks)

    batches: list[list] = []
    current_batch: list = []
    current_tokens = 0

    for _heading, section_chunks in content_sections:
        section_tokens = sum(_estimate_tokens(c.content) for c in section_chunks)

        if current_batch and current_tokens + section_tokens > target_tokens:
            batches.append(list(shared_chunks) + current_batch)
            current_batch = []
            current_tokens = 0

        current_batch.extend(section_chunks)
        current_tokens += section_tokens

    if current_batch:
        batches.append(list(shared_chunks) + current_batch)

    if len(batches) == 1 and shared_tokens + current_tokens <= target_tokens * 1.5:
        return [list(chunks)]

    logger.info(
        "Split document into %d batches (shared: %d chunks / ~%d tokens, content sections: %d)",
        len(batches), len(shared_chunks), shared_tokens, len(content_sections),
    )
    return batches


# ---------------------------------------------------------------------------
# Single extraction (core logic for one chunk set)
# ---------------------------------------------------------------------------

def _analyze_chunk_set(
    chunks,
    usage: LifecycleUsage,
    *,
    validate: bool = True,
    max_retries: int | None = None,
    doc_scope: str = DOC_SCOPE_UNKNOWN,
) -> tuple[LifecycleResult, list[DocIssue]]:
    """Extract lifecycle from a set of chunks (single LLM call path).

    Handles summarization for oversized chunk sets, extraction, and
    optional validation+correction.
    """
    if max_retries is None:
        max_retries = settings.lifecycle_validation_max_retries

    chunk_contents = [c.content for c in chunks]
    doc_text_parts = [f"## {c.heading_path}\n{c.content}" for c in chunks]
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
            usage.add_llm_call(llm_usage, call_ms)
            summaries.append(f"## {heading}\n{raw}")

        doc_text = "\n\n".join(summaries)

    result = _extract_lifecycle(doc_text, usage, doc_scope=doc_scope)

    if validate:
        result, doc_issues = _validate_and_correct(result, chunk_contents, max_retries)
    else:
        doc_issues = []

    return result, doc_issues


# ---------------------------------------------------------------------------
# Public API: per-document analysis
# ---------------------------------------------------------------------------

def analyze_document_lifecycle_sync(
    document_id: int,
    session,
) -> list[tuple[LifecycleResult, list[DocIssue]]]:
    """Analyze a single document and extract its API lifecycle.

    For small documents (< lifecycle_batch_min_chunks), returns a single
    lifecycle result. For large documents, splits into batches by top-level
    heading boundaries, extracts a lifecycle per batch, then merges.

    Returns a list of (LifecycleResult, DocIssues) tuples:
    - Small docs: 1 element
    - Large docs: N batch results + 1 merged result (last element)
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
        return [(
            LifecycleResult(
                validation_issues=[{"error": "No chunks found for document"}],
                usage=usage,
            ),
            [],
        )]

    # Detect doc_scope from product name and chunk contents
    from app.models import Document, Product
    doc_row = session.execute(
        sa_select(Document.product_id).where(Document.id == document_id)
    ).scalar_one_or_none()
    product_name = ""
    if doc_row:
        product_name = (session.execute(
            sa_select(Product.name).where(Product.id == doc_row)
        ).scalar_one_or_none() or "")
    chunk_contents_for_scope = [c.content for c in chunks[:20]]
    scope = detect_doc_scope(product_name, chunk_contents_for_scope)
    logger.info("Detected doc_scope=%s for document %d (product=%s)",
                scope, document_id, product_name)

    # --- Small document: single extraction (existing behavior) ---
    if len(chunks) < settings.lifecycle_batch_min_chunks:
        result, doc_issues = _analyze_chunk_set(chunks, usage, doc_scope=scope)
        usage.analysis_ms = round((time.perf_counter() - t0) * 1000, 1)
        usage.total_tokens = usage.prompt_tokens + usage.completion_tokens
        result.usage = usage
        return [(result, doc_issues)]

    # --- Large document: chunked extraction + merge ---
    batches = _split_chunks_into_batches(chunks, settings.lifecycle_batch_target_tokens)

    if len(batches) <= 1:
        result, doc_issues = _analyze_chunk_set(chunks, usage, doc_scope=scope)
        usage.analysis_ms = round((time.perf_counter() - t0) * 1000, 1)
        usage.total_tokens = usage.prompt_tokens + usage.completion_tokens
        result.usage = usage
        return [(result, doc_issues)]

    logger.info(
        "Large document %d: chunked extraction with %d batches (%d total chunks)",
        document_id, len(batches), len(chunks),
    )

    batch_results: list[tuple[LifecycleResult, list[DocIssue]]] = []
    all_chunk_contents = [c.content for c in chunks]

    for i, batch in enumerate(batches):
        logger.info("Extracting batch %d/%d (%d chunks)", i + 1, len(batches), len(batch))
        result, doc_issues = _analyze_chunk_set(
            batch, usage, validate=True, max_retries=1, doc_scope=scope,
        )
        if result.phases:
            batch_results.append((result, doc_issues))
        else:
            logger.warning("Batch %d/%d produced no phases, skipping", i + 1, len(batches))

    if not batch_results:
        usage.analysis_ms = round((time.perf_counter() - t0) * 1000, 1)
        return [(
            LifecycleResult(
                validation_issues=[{"error": "No batches produced lifecycle phases"}],
                usage=usage,
            ),
            [],
        )]

    if len(batch_results) == 1:
        r, di = batch_results[0]
        usage.analysis_ms = round((time.perf_counter() - t0) * 1000, 1)
        usage.total_tokens = usage.prompt_tokens + usage.completion_tokens
        r.usage = usage
        return [(r, di)]

    # Merge all batch results into a unified lifecycle
    merge_data = [_result_to_merge_dict(r) for r, _ in batch_results]

    if len(merge_data) <= _MERGE_BATCH_SIZE:
        merged = _merge_batch(merge_data, usage, doc_scope=scope)
    else:
        merged = _hierarchical_merge(merge_data, usage, doc_scope=scope)

    if merged is None:
        merged = batch_results[0][0]
        merged.validation_issues.append({"error": "Batch merge failed, using first batch only"})

    merged.doc_scope = scope

    merged, merge_issues = _validate_and_correct(
        merged, all_chunk_contents, settings.lifecycle_validation_max_retries,
    )

    usage.analysis_ms = round((time.perf_counter() - t0) * 1000, 1)
    usage.total_tokens = usage.prompt_tokens + usage.completion_tokens
    merged.usage = usage

    all_results = list(batch_results)
    all_doc_issues: list[DocIssue] = []
    for _, di in batch_results:
        all_doc_issues.extend(di)
    all_doc_issues.extend(merge_issues)

    all_results.append((merged, all_doc_issues))

    logger.info(
        "Chunked extraction complete: %d batches, merged lifecycle has %d phases, %d endpoints",
        len(batch_results),
        len(merged.phases),
        len(merged.endpoint_coverage),
    )

    return all_results


# ---------------------------------------------------------------------------
# Merge helpers
# ---------------------------------------------------------------------------

_MERGE_BATCH_SIZE = 10


def _has_skeleton_errors(lc) -> bool:
    """Check if a lifecycle ORM object has skeleton-related validation issues."""
    for issue in (lc.validation_issues or []):
        if "code_skeleton" in issue.get("error", "").lower():
            return True
    return False


def _lc_to_merge_dict(lc) -> dict:
    """Convert an ApiLifecycle ORM object to a dict suitable for the merge prompt.

    Excludes code_skeleton if it had unresolved validation errors to prevent
    propagating hallucinated endpoints into the merged product lifecycle.
    """
    skeleton = "" if _has_skeleton_errors(lc) else (lc.code_skeleton or "")
    return {
        "document_id": lc.document_id,
        "phases": lc.phases or [],
        "unique_patterns": lc.unique_patterns or [],
        "dependency_chains": lc.dependency_chains or [],
        "code_skeleton": skeleton,
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


def _merge_batch(
    batch_data: list[dict],
    usage: LifecycleUsage,
    *,
    doc_scope: str = DOC_SCOPE_UNKNOWN,
) -> LifecycleResult | None:
    """Merge a single batch of lifecycle dicts via one LLM call."""
    merge_prompt = _MERGE_PROMPT.format(
        count=len(batch_data),
        lifecycles_json=json.dumps(batch_data, indent=2, ensure_ascii=False),
    )

    raw, llm_usage, call_ms = _call_llm_sync(
        "You are an API integration analyst. Merge multiple lifecycle analyses into one.",
        merge_prompt,
    )
    usage.add_llm_call(llm_usage, call_ms)

    parsed = _parse_lifecycle_json(raw)
    if parsed is None:
        return None

    return _lifecycle_from_parsed(parsed, usage, doc_scope=doc_scope)


def _hierarchical_merge(
    all_data: list[dict],
    usage: LifecycleUsage,
    *,
    doc_scope: str = DOC_SCOPE_UNKNOWN,
) -> LifecycleResult | None:
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

            result = _merge_batch(batch, usage, doc_scope=doc_scope)
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
    return _lifecycle_from_parsed(final, usage, doc_scope=doc_scope)


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
    from app.models import ApiLifecycle, Product

    t0 = time.perf_counter()
    usage = LifecycleUsage(model=settings.lifecycle_analysis_model)

    doc_lifecycles = session.execute(
        sa_select(ApiLifecycle)
        .where(
            ApiLifecycle.product_id == product_id,
            ApiLifecycle.document_id.isnot(None),
            ApiLifecycle.batch_index.is_(None),
            ApiLifecycle.status == "ready",
        )
    ).scalars().all()

    if not doc_lifecycles:
        return LifecycleResult(
            validation_issues=[{"error": "No document-level lifecycles found for product"}],
            usage=usage,
        ), []

    # Detect doc_scope from product name and chunks
    product_name = (session.execute(
        sa_select(Product.name).where(Product.id == product_id)
    ).scalar_one_or_none() or "")
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
    scope = detect_doc_scope(product_name, all_chunk_contents[:20])
    logger.info("Product merge doc_scope=%s for product %d (%s)", scope, product_id, product_name)

    if len(doc_lifecycles) == 1:
        lc = doc_lifecycles[0]
        error_catalog = lc.error_catalog or []
        result = LifecycleResult(
            phases=lc.phases or [],
            unique_patterns=lc.unique_patterns or [],
            dependency_chains=lc.dependency_chains or [],
            code_skeleton=lc.code_skeleton or "",
            data_models=lc.data_models or [],
            error_catalog=error_catalog,
            prerequisites=lc.prerequisites or [],
            data_access_patterns=lc.data_access_patterns or [],
            endpoint_coverage=_recalc_endpoint_completeness(
                lc.endpoint_coverage or [],
                has_global_error_catalog=bool(error_catalog),
                doc_scope=scope,
            ),
            integration_data_flows=lc.integration_data_flows or {},
            doc_scope=scope,
            usage=usage,
        )
        usage.analysis_ms = round((time.perf_counter() - t0) * 1000, 1)
        return result, []

    lifecycles_data = [_lc_to_merge_dict(lc) for lc in doc_lifecycles]

    if len(lifecycles_data) <= _MERGE_BATCH_SIZE:
        result = _merge_batch(lifecycles_data, usage, doc_scope=scope)
    else:
        logger.info(
            "Starting hierarchical merge for product %d: %d documents",
            product_id, len(lifecycles_data),
        )
        result = _hierarchical_merge(lifecycles_data, usage, doc_scope=scope)

    if result is None:
        return LifecycleResult(
            validation_issues=[{"error": "Failed to parse merged lifecycle JSON"}],
            usage=usage,
        ), []

    result.doc_scope = scope

    result, doc_issues = _validate_and_correct(
        result, all_chunk_contents, settings.lifecycle_validation_max_retries,
    )

    usage.analysis_ms = round((time.perf_counter() - t0) * 1000, 1)
    usage.total_tokens = usage.prompt_tokens + usage.completion_tokens
    result.usage = usage

    return result, doc_issues


# ---------------------------------------------------------------------------
# Code skeleton language conversion
# ---------------------------------------------------------------------------

SUPPORTED_SKELETON_LANGUAGES = ("python", "csharp", "cpp", "go", "curl", "java", "javascript")

_SKELETON_LANG_META: dict[str, dict[str, str]] = {
    "python": {"label": "Python", "lib": "httpx"},
    "csharp": {"label": "C#", "lib": "HttpClient (System.Net.Http)"},
    "cpp": {"label": "C++", "lib": "libcurl or cpr"},
    "go": {"label": "Go", "lib": "net/http"},
    "curl": {"label": "cURL", "lib": "curl CLI"},
    "java": {"label": "Java", "lib": "java.net.http.HttpClient (Java 11+)"},
    "javascript": {"label": "JavaScript", "lib": "fetch API"},
}

_SKELETON_CONVERT_PROMPT = """\
You are an expert polyglot programmer. Convert the following Python (httpx) API integration \
skeleton into idiomatic {label} code using {lib}.

Requirements:
- Preserve the EXACT same API endpoints, HTTP methods, headers, request bodies, and response parsing.
- Use idiomatic patterns for {label}: proper error handling, resource cleanup, naming conventions.
- Keep all comments that explain non-obvious steps.
- Do NOT add, remove, or change any API calls — this is a 1:1 translation.
- Output ONLY the code, no markdown fences, no explanations.

{extra_instructions}

Python skeleton to convert:

{skeleton}
"""

_SKELETON_EXTRA_INSTRUCTIONS: dict[str, str] = {
    "python": "",
    "csharp": "Use async/await with HttpClient. Use System.Text.Json for JSON serialization. "
              "Wrap in a static async Task Main. Dispose HttpClient properly.",
    "cpp": "Use libcurl (C API) with proper RAII cleanup via curl_easy_cleanup. "
           "Parse JSON with nlohmann/json or rapidjson. Include all necessary #includes.",
    "go": "Use net/http standard library. Use encoding/json for JSON. "
          "Always check and handle errors. Use defer for cleanup. Follow Go naming conventions.",
    "curl": "Output a bash script using curl CLI. Use -X for method, -H for headers, -d for body. "
            "Use jq to parse JSON responses and extract fields. Add -s (silent) flag. "
            "Use variables for tokens and base URLs.",
    "java": "Use java.net.http.HttpClient (Java 11+). Use HttpRequest/HttpResponse. "
            "Parse JSON with com.google.gson.Gson or org.json. Use try-with-resources.",
    "javascript": "Use the fetch API (browser/Node 18+). Use async/await. "
                  "Parse responses with response.json(). Use try/catch for error handling.",
}


def convert_skeleton_sync(python_skeleton: str, target_language: str) -> str:
    """Convert a Python httpx skeleton to another language via LLM.

    Returns the converted code as a string.
    Raises ValueError for unsupported languages.
    """
    if target_language not in SUPPORTED_SKELETON_LANGUAGES:
        raise ValueError(f"Unsupported language: {target_language}")

    if target_language == "python":
        return python_skeleton

    meta = _SKELETON_LANG_META[target_language]
    prompt = _SKELETON_CONVERT_PROMPT.format(
        label=meta["label"],
        lib=meta["lib"],
        extra_instructions=_SKELETON_EXTRA_INSTRUCTIONS.get(target_language, ""),
        skeleton=python_skeleton,
    )

    text, usage, llm_ms = _call_llm_sync(
        system="You are a code translator. Output only code, no markdown.",
        user=prompt,
        json_mode=False,
    )

    code = text.strip()
    if code.startswith("```"):
        first_nl = code.index("\n") if "\n" in code else len(code)
        code = code[first_nl + 1:]
    if code.endswith("```"):
        code = code[:-3].rstrip()

    logger.info(
        "Skeleton converted to %s in %.0fms (%d prompt + %d completion tokens)",
        target_language, llm_ms,
        usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0),
    )
    return code
