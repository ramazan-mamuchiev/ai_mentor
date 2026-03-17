"""Swagger/OpenAPI -> Markdown converter.

Supports OpenAPI 2.0 (Swagger) and 3.x specifications in JSON and YAML.
Resolves $ref references, renders security schemes, models, and endpoints.
"""

import json
import logging
import os
import pathlib
import time

import yaml

logger = logging.getLogger(__name__)

_SWAGGER_EXTENSIONS = {".yaml", ".yml", ".json"}
_SWAGGER_NAMES = {"swagger", "openapi", "paths", "info"}


def is_swagger_file(path: str) -> bool:
    """Check if a file looks like a Swagger/OpenAPI spec."""
    p = pathlib.Path(path)
    if p.suffix.lower() not in _SWAGGER_EXTENSIONS:
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read(4096)
        if p.suffix.lower() == ".json":
            data = json.loads(raw if raw.rstrip().endswith("}") else raw + "}")
        else:
            data = yaml.safe_load(raw)
        if isinstance(data, dict):
            return bool(set(data.keys()) & _SWAGGER_NAMES)
    except Exception:
        pass
    return False


def _parse_openapi(file_path: str) -> dict:
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    if file_path.lower().endswith(".json"):
        return json.loads(content)
    return yaml.safe_load(content)


def _parse_openapi_text(text: str, content_type: str = "") -> dict | None:
    """Parse raw text as OpenAPI spec. Returns dict or None."""
    data = None
    if "json" in content_type or text.lstrip().startswith("{"):
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            pass
    if data is None:
        try:
            data = yaml.safe_load(text)
        except Exception:
            pass
    if isinstance(data, dict) and (set(data.keys()) & _SWAGGER_NAMES):
        return data
    return None


def _resolve_ref(spec: dict, ref: str) -> dict | None:
    if not ref.startswith("#/"):
        return None
    parts = ref[2:].split("/")
    node = spec
    for p in parts:
        if isinstance(node, dict):
            node = node.get(p)
        else:
            return None
    return node if isinstance(node, dict) else None


def _type_str(schema: dict, spec: dict | None = None) -> str:
    if not schema:
        return ""
    if "$ref" in schema:
        ref = schema["$ref"]
        name = ref.rsplit("/", 1)[-1]
        return f"[{name}](#{name.lower()})"
    t = schema.get("type", "")
    fmt = schema.get("format", "")
    if t == "array":
        items = schema.get("items", {})
        return f"array of {_type_str(items, spec)}"
    if schema.get("enum"):
        vals = ", ".join(str(v) for v in schema["enum"])
        base = f"{t} ({fmt})" if fmt else t
        return f"{base} (enum: {vals})"
    if fmt:
        return f"{t} ({fmt})"
    return t


def _openapi_to_markdown(spec: dict) -> str:
    is_v3 = spec.get("openapi", "").startswith("3")
    info = spec.get("info", {})
    title = info.get("title", "API")
    version = info.get("version", "")
    description = info.get("description", "")

    lines: list[str] = []
    lines.append(f"# {title} v{version}")
    lines.append("")
    if description:
        lines.append(description)
        lines.append("")

    host = spec.get("host", "")
    base_path = spec.get("basePath", "")
    if is_v3:
        servers = spec.get("servers", [])
        if servers:
            lines.append(f"**Server:** {servers[0].get('url', '')}")
            lines.append("")
    elif host:
        schemes = spec.get("schemes", ["https"])
        lines.append(f"**Base URL:** {schemes[0]}://{host}{base_path}")
        lines.append("")

    contact = info.get("contact", {})
    if contact.get("email"):
        lines.append(f"**Contact:** {contact['email']}")
        lines.append("")

    tags_info = {t["name"]: t.get("description", "") for t in spec.get("tags", [])}

    paths = spec.get("paths", {})
    endpoints_by_tag: dict[str, list[tuple[str, str, dict]]] = {}
    for path_str, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method in ("get", "post", "put", "patch", "delete", "options", "head"):
            op = path_item.get(method)
            if not op:
                continue
            op_tags = op.get("tags", ["default"])
            for tag in op_tags:
                endpoints_by_tag.setdefault(tag, []).append((method, path_str, op))

    lines.append("---")
    lines.append("")

    for tag, endpoints in endpoints_by_tag.items():
        tag_desc = tags_info.get(tag, "")
        lines.append(f"## {tag}")
        lines.append("")
        if tag_desc:
            lines.append(tag_desc)
            lines.append("")

        for method, path_str, op in endpoints:
            summary = op.get("summary", "")
            desc = op.get("description", "")
            lines.append(f"### {method.upper()} {path_str}")
            lines.append("")
            if summary:
                lines.append(f"**{summary}**")
                lines.append("")
            if desc and desc != summary:
                lines.append(desc)
                lines.append("")

            params = list(op.get("parameters", []))
            if is_v3 and op.get("requestBody"):
                rb = op["requestBody"]
                rb_desc = rb.get("description", "Request body")
                content = rb.get("content", {})
                for ct_val in content.values():
                    schema = ct_val.get("schema", {})
                    params.append({
                        "name": "body",
                        "in": "body",
                        "description": rb_desc,
                        "required": rb.get("required", False),
                        "_schema": schema,
                    })

            if params:
                lines.append("| Parameter | In | Type | Required | Description |")
                lines.append("|---|---|---|---|---|")
                for p in params:
                    name = p.get("name", "")
                    loc = p.get("in", "")
                    required = "yes" if p.get("required") else "no"
                    p_desc = p.get("description", "")
                    if "schema" in p:
                        p_type = _type_str(p["schema"], spec)
                    elif "_schema" in p:
                        p_type = _type_str(p["_schema"], spec)
                    else:
                        raw_type = p.get("type", "")
                        raw_fmt = p.get("format", "")
                        p_type = f"{raw_type} ({raw_fmt})" if raw_fmt else raw_type
                    lines.append(f"| {name} | {loc} | {p_type} | {required} | {p_desc} |")
                lines.append("")

            responses = op.get("responses", {})
            if responses:
                resp_parts = []
                for code, resp in sorted(responses.items()):
                    r_desc = resp.get("description", "") if isinstance(resp, dict) else ""
                    resp_parts.append(f"{code} ({r_desc})")
                lines.append(f"**Responses:** {', '.join(resp_parts)}")
                lines.append("")

            security = op.get("security", [])
            if security:
                sec_names = []
                for s in security:
                    if isinstance(s, dict):
                        sec_names.extend(s.keys())
                if sec_names:
                    lines.append(f"**Security:** {', '.join(sec_names)}")
                    lines.append("")

    defs = spec.get("definitions") or {}
    if is_v3:
        defs = spec.get("components", {}).get("schemas", {})

    if defs:
        lines.append("---")
        lines.append("")
        lines.append("## Models")
        lines.append("")

        for model_name, model_schema in sorted(defs.items()):
            lines.append(f"### {model_name}")
            lines.append("")
            model_desc = model_schema.get("description", "")
            if model_desc:
                lines.append(model_desc)
                lines.append("")

            props = model_schema.get("properties", {})
            required_fields = set(model_schema.get("required", []))
            if props:
                lines.append("| Field | Type | Required | Description |")
                lines.append("|---|---|---|---|")
                for field_name, field_schema in props.items():
                    f_type = _type_str(field_schema, spec)
                    f_desc = field_schema.get("description", "")
                    example = field_schema.get("example")
                    if example is not None and not f_desc:
                        f_desc = f"example: {example}"
                    elif example is not None:
                        f_desc += f" (example: {example})"
                    f_req = "yes" if field_name in required_fields else ""
                    lines.append(f"| {field_name} | {f_type} | {f_req} | {f_desc} |")
                lines.append("")

    sec_defs = spec.get("securityDefinitions") or {}
    if is_v3:
        sec_defs = spec.get("components", {}).get("securitySchemes", {})
    if sec_defs:
        lines.append("---")
        lines.append("")
        lines.append("## Security Schemes")
        lines.append("")
        for sec_name, sec_schema in sec_defs.items():
            sec_type = sec_schema.get("type", "")
            sec_in = sec_schema.get("in", "")
            sec_param = sec_schema.get("name", "")
            lines.append(f"- **{sec_name}**: {sec_type} (in: {sec_in}, name: {sec_param})")
        lines.append("")

    return "\n".join(lines)


def convert_swagger_file(file_path: str) -> tuple[str, dict]:
    """Convert a Swagger/OpenAPI file to Markdown.

    Returns (markdown_text, metadata).
    """
    t0 = time.perf_counter()
    file_size = os.path.getsize(file_path)

    logger.info(
        "Swagger conversion started",
        extra={"file": os.path.basename(file_path), "file_size_bytes": file_size},
    )

    spec = _parse_openapi(file_path)
    md_text = _openapi_to_markdown(spec)

    info = spec.get("info", {})
    endpoints_count = sum(
        len([m for m in ("get", "post", "put", "patch", "delete", "options", "head") if m in ops])
        for ops in spec.get("paths", {}).values()
        if isinstance(ops, dict)
    )
    models_count = len(
        spec.get("definitions") or spec.get("components", {}).get("schemas", {}) or {}
    )

    total_ms = round((time.perf_counter() - t0) * 1000, 1)

    metadata = {
        "api_title": info.get("title", ""),
        "api_version": info.get("version", ""),
        "swagger_version": spec.get("swagger", spec.get("openapi", "")),
        "endpoints": endpoints_count,
        "models": models_count,
        "file_size_bytes": file_size,
        "total_ms": total_ms,
    }

    logger.info(
        "Swagger conversion completed",
        extra={
            "file": os.path.basename(file_path),
            "endpoints": endpoints_count, "models": models_count,
            "total_ms": total_ms, "md_length": len(md_text),
        },
    )

    return md_text, metadata


def convert_swagger_text(text: str, content_type: str = "") -> tuple[str, dict] | None:
    """Convert raw Swagger/OpenAPI text to Markdown.

    Returns (markdown_text, metadata) or None if text is not a valid spec.
    """
    spec = _parse_openapi_text(text, content_type)
    if spec is None:
        return None

    md_text = _openapi_to_markdown(spec)

    info = spec.get("info", {})
    endpoints_count = sum(
        len([m for m in ("get", "post", "put", "patch", "delete", "options", "head") if m in ops])
        for ops in spec.get("paths", {}).values()
        if isinstance(ops, dict)
    )
    models_count = len(
        spec.get("definitions") or spec.get("components", {}).get("schemas", {}) or {}
    )

    metadata = {
        "api_title": info.get("title", ""),
        "api_version": info.get("version", ""),
        "swagger_version": spec.get("swagger", spec.get("openapi", "")),
        "endpoints": endpoints_count,
        "models": models_count,
    }

    return md_text, metadata
