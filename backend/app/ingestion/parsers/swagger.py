"""Swagger/OpenAPI parser: one chunk per API endpoint."""

import json

import yaml

from app.ingestion.chunker import Section


def parse_swagger(text: str, file_path: str = "") -> list[Section]:
    """Parse OpenAPI/Swagger spec into sections (one per endpoint + models)."""
    spec = _load_spec(text, file_path)
    if not spec:
        return []

    sections: list[Section] = []
    info = spec.get("info", {})
    title = info.get("title", "API")
    version = info.get("version", "")

    overview_parts = [f"# {title} v{version}"]
    if info.get("description"):
        overview_parts.append(info["description"])
    sections.append(Section(
        heading_path=title,
        heading_level=1,
        content="\n\n".join(overview_parts),
    ))

    paths = spec.get("paths", {})
    for path_str, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method in ("get", "post", "put", "patch", "delete", "options", "head"):
            op = path_item.get(method)
            if not op:
                continue
            endpoint_heading = f"{method.upper()} {path_str}"
            content = _format_endpoint(method, path_str, op, spec)
            tags = op.get("tags", ["default"])
            heading_path = f"{title} > {tags[0]} > {endpoint_heading}"
            sections.append(Section(
                heading_path=heading_path,
                heading_level=3,
                content=content,
            ))

    defs = spec.get("definitions") or spec.get("components", {}).get("schemas", {})
    if defs:
        for model_name, model_schema in defs.items():
            content = _format_model(model_name, model_schema, spec)
            sections.append(Section(
                heading_path=f"{title} > Models > {model_name}",
                heading_level=3,
                content=content,
            ))

    return sections


def _load_spec(text: str, file_path: str) -> dict | None:
    try:
        if file_path.lower().endswith(".json") or text.lstrip().startswith("{"):
            return json.loads(text)
        return yaml.safe_load(text)
    except Exception:
        return None


def _type_str(schema: dict) -> str:
    if not schema:
        return ""
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]
    t = schema.get("type", "")
    fmt = schema.get("format", "")
    if t == "array":
        items = schema.get("items", {})
        return f"array of {_type_str(items)}"
    if schema.get("enum"):
        return f"{t} (enum: {', '.join(str(v) for v in schema['enum'])})"
    return f"{t} ({fmt})" if fmt else t


def _format_endpoint(method: str, path: str, op: dict, spec: dict) -> str:
    lines = [f"### {method.upper()} {path}"]

    if op.get("summary"):
        lines.append(f"\n**{op['summary']}**")
    if op.get("description") and op["description"] != op.get("summary"):
        lines.append(f"\n{op['description']}")

    is_v3 = spec.get("openapi", "").startswith("3")

    params = list(op.get("parameters", []))
    if is_v3 and op.get("requestBody"):
        rb = op["requestBody"]
        for ct, ct_val in rb.get("content", {}).items():
            schema = ct_val.get("schema", {})
            params.append({
                "name": "body",
                "in": "body",
                "description": rb.get("description", "Request body"),
                "required": rb.get("required", False),
                "schema": schema,
            })

    if params:
        lines.append("\n| Parameter | In | Type | Required | Description |")
        lines.append("|---|---|---|---|---|")
        for p in params:
            name = p.get("name", "")
            loc = p.get("in", "")
            required = "yes" if p.get("required") else "no"
            desc = p.get("description", "")
            p_type = _type_str(p.get("schema", {})) if "schema" in p else p.get("type", "")
            lines.append(f"| {name} | {loc} | {p_type} | {required} | {desc} |")

    responses = op.get("responses", {})
    if responses:
        resp_parts = []
        for code, resp in sorted(responses.items()):
            r_desc = resp.get("description", "") if isinstance(resp, dict) else ""
            resp_parts.append(f"{code} ({r_desc})")
        lines.append(f"\n**Responses:** {', '.join(resp_parts)}")

    return "\n".join(lines)


def _format_model(name: str, schema: dict, spec: dict) -> str:
    lines = [f"### {name}"]

    if schema.get("description"):
        lines.append(f"\n{schema['description']}")

    props = schema.get("properties", {})
    required_fields = set(schema.get("required", []))
    if props:
        lines.append("\n| Field | Type | Required | Description |")
        lines.append("|---|---|---|---|")
        for field_name, field_schema in props.items():
            f_type = _type_str(field_schema)
            f_desc = field_schema.get("description", "")
            f_req = "yes" if field_name in required_fields else ""
            lines.append(f"| {field_name} | {f_type} | {f_req} | {f_desc} |")

    return "\n".join(lines)
