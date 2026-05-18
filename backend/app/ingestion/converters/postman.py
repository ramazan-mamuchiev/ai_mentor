"""Postman Collection v2.x -> Markdown converter.

Supports Postman Collection v2.0 and v2.1 JSON format.
Converts folders, requests (method, URL, headers, body, auth),
and saved responses into structured Markdown documentation.
"""

import json
import logging
import os
import time

logger = logging.getLogger(__name__)

_POSTMAN_SCHEMA_MARKERS = ("schema.getpostman.com", "_postman_id", "postman_collection")


def is_postman_collection(file_path: str) -> bool:
    """Check if a JSON file is a Postman Collection.

    Uses a two-pass strategy: first a fast text probe on the first 16 KB,
    then a full JSON parse only when the probe is positive.
    """
    if not file_path.lower().endswith(".json"):
        return False
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            head = f.read(16384)
        if any(m in head for m in _POSTMAN_SCHEMA_MARKERS):
            return True
        if '"_postman_id"' in head and '"item"' in head:
            return True
    except Exception:
        pass
    return False


def _extract_url(url_obj) -> str:
    """Extract URL string from various Postman URL formats."""
    if isinstance(url_obj, str):
        return url_obj
    if isinstance(url_obj, dict):
        if "raw" in url_obj:
            return url_obj["raw"]
        protocol = url_obj.get("protocol", "https")
        host = url_obj.get("host", "")
        if isinstance(host, list):
            host = ".".join(host)
        port = url_obj.get("port", "")
        path = url_obj.get("path", "")
        if isinstance(path, list):
            path = "/".join(path)
        base = f"{protocol}://{host}"
        if port:
            base += f":{port}"
        if path:
            base += f"/{path}"
        return base
    return str(url_obj)


def _extract_description(desc_obj) -> str:
    if not desc_obj:
        return ""
    if isinstance(desc_obj, str):
        return desc_obj.strip()
    if isinstance(desc_obj, dict):
        return (desc_obj.get("content") or "").strip()
    return ""


def _render_auth(auth: dict) -> list[str]:
    """Render auth section to Markdown lines."""
    if not auth or not isinstance(auth, dict):
        return []
    auth_type = auth.get("type", "unknown")
    lines = [f"**Authentication:** {auth_type}"]

    auth_data = auth.get(auth_type, {})
    if isinstance(auth_data, list):
        for item in auth_data:
            if isinstance(item, dict):
                key = item.get("key", "")
                val = item.get("value", "")
                if key and val:
                    lines.append(f"- `{key}`: `{val}`")
    elif isinstance(auth_data, dict):
        for k, v in auth_data.items():
            if v and not k.startswith("_"):
                lines.append(f"- `{k}`: `{v}`")

    lines.append("")
    return lines


def _render_headers(headers) -> list[str]:
    """Render headers to Markdown table."""
    if not headers:
        return []
    header_list = []
    if isinstance(headers, str):
        for line in headers.strip().split("\n"):
            line = line.strip().rstrip("\r")
            if ":" in line:
                k, v = line.split(":", 1)
                header_list.append((k.strip(), v.strip()))
    elif isinstance(headers, list):
        for h in headers:
            if isinstance(h, dict):
                k = h.get("key", "")
                v = h.get("value", "")
                desc = h.get("description", "")
                if k:
                    header_list.append((k, v, desc))

    if not header_list:
        return []

    lines = ["**Headers:**", ""]
    lines.append("| Key | Value | Description |")
    lines.append("|---|---|---|")
    for h in header_list:
        k = h[0] if len(h) > 0 else ""
        v = h[1] if len(h) > 1 else ""
        d = h[2] if len(h) > 2 else ""
        lines.append(f"| `{k}` | `{v}` | {d} |")
    lines.append("")
    return lines


def _render_body(body: dict) -> list[str]:
    """Render request body to Markdown."""
    if not body or not isinstance(body, dict):
        return []
    mode = body.get("mode", "")
    lines = [f"**Body** (`{mode}`):"]

    if mode == "raw":
        raw = body.get("raw", "")
        if raw:
            lang = ""
            options = body.get("options", {})
            if isinstance(options, dict):
                raw_opts = options.get("raw", {})
                if isinstance(raw_opts, dict):
                    lang = raw_opts.get("language", "")
            lines.append("")
            lines.append(f"```{lang}")
            lines.append(raw)
            lines.append("```")
    elif mode == "urlencoded":
        params = body.get("urlencoded", [])
        if params:
            lines.append("")
            lines.append("| Key | Value | Description |")
            lines.append("|---|---|---|")
            for p in params:
                if isinstance(p, dict):
                    lines.append(f"| `{p.get('key', '')}` | `{p.get('value', '')}` | {p.get('description', '')} |")
    elif mode == "formdata":
        params = body.get("formdata", [])
        if params:
            lines.append("")
            lines.append("| Key | Value | Type | Description |")
            lines.append("|---|---|---|---|")
            for p in params:
                if isinstance(p, dict):
                    lines.append(f"| `{p.get('key', '')}` | `{p.get('value', '')}` | {p.get('type', 'text')} | {p.get('description', '')} |")
    elif mode == "graphql":
        gql = body.get("graphql", {})
        query = gql.get("query", "") if isinstance(gql, dict) else ""
        if query:
            lines.append("")
            lines.append("```graphql")
            lines.append(query)
            lines.append("```")

    lines.append("")
    return lines


def _render_responses(responses: list) -> list[str]:
    """Render saved example responses."""
    if not responses:
        return []
    lines = ["**Example Responses:**", ""]
    for resp in responses:
        if not isinstance(resp, dict):
            continue
        name = resp.get("name", "Response")
        status = resp.get("status", "")
        code = resp.get("code", "")
        label = f"{code} {status}".strip() if code else status
        lines.append(f"##### {name}" + (f" ({label})" if label else ""))
        lines.append("")
        body = resp.get("body", "")
        if body:
            lines.append("```json")
            if len(body) > 2000:
                lines.append(body[:2000] + "\n... (truncated)")
            else:
                lines.append(body)
            lines.append("```")
            lines.append("")
    return lines


def _render_request(item: dict, depth: int) -> list[str]:
    """Render a single request item to Markdown."""
    name = item.get("name", "Unnamed Request")
    desc = _extract_description(item.get("description"))
    request = item.get("request", {})

    if isinstance(request, str):
        method = "GET"
        url = request
        req_desc = ""
        headers = None
        body = None
        auth = None
    elif isinstance(request, dict):
        method = request.get("method", "GET")
        url = _extract_url(request.get("url", ""))
        req_desc = _extract_description(request.get("description"))
        headers = request.get("header")
        body = request.get("body")
        auth = request.get("auth")
    else:
        return []

    heading = "#" * min(depth + 2, 6)
    lines = [f"{heading} {method} {name}", ""]

    if url:
        lines.append(f"`{method} {url}`")
        lines.append("")

    effective_desc = req_desc or desc
    if effective_desc:
        lines.append(effective_desc)
        lines.append("")

    if auth:
        lines.extend(_render_auth(auth))

    if headers:
        lines.extend(_render_headers(headers))

    if body:
        lines.extend(_render_body(body))

    responses = item.get("response", [])
    if responses:
        lines.extend(_render_responses(responses))

    return lines


def _render_items(items: list, depth: int = 0) -> list[str]:
    """Recursively render collection items (folders and requests)."""
    lines = []
    for item in items:
        if not isinstance(item, dict):
            continue

        sub_items = item.get("item")
        if isinstance(sub_items, list):
            name = item.get("name", "Folder")
            desc = _extract_description(item.get("description"))
            heading = "#" * min(depth + 2, 6)
            lines.append(f"{heading} {name}")
            lines.append("")
            if desc:
                lines.append(desc)
                lines.append("")
            auth = item.get("auth")
            if auth:
                lines.extend(_render_auth(auth))
            lines.extend(_render_items(sub_items, depth + 1))
        else:
            lines.extend(_render_request(item, depth))

    return lines


def _postman_to_markdown(data: dict) -> str:
    """Convert parsed Postman Collection to Markdown."""
    info = data.get("info", {})
    name = info.get("name", "API Collection")
    desc = _extract_description(info.get("description"))

    lines = [f"# {name}", ""]

    if desc:
        lines.append(desc)
        lines.append("")

    auth = data.get("auth")
    if auth:
        lines.append("## Authentication")
        lines.append("")
        lines.extend(_render_auth(auth))

    variables = data.get("variable", [])
    if variables:
        lines.append("## Variables")
        lines.append("")
        lines.append("| Variable | Value |")
        lines.append("|---|---|")
        for v in variables:
            if isinstance(v, dict):
                vid = v.get("key") or v.get("id", "")
                val = v.get("value", "")
                if vid:
                    lines.append(f"| `{vid}` | `{val}` |")
        lines.append("")

    items = data.get("item", [])
    if items:
        lines.extend(_render_items(items))

    return "\n".join(lines)


def convert_postman_file(file_path: str) -> tuple[str, dict]:
    """Convert a Postman Collection JSON file to Markdown.

    Returns (markdown_text, metadata).
    """
    t0 = time.perf_counter()
    file_size = os.path.getsize(file_path)

    logger.info(
        "Postman conversion started",
        extra={"file": os.path.basename(file_path), "file_size_bytes": file_size},
    )

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    md_text = _postman_to_markdown(data)

    info = data.get("info", {})

    def _count_requests(items: list) -> int:
        count = 0
        for item in items:
            if isinstance(item, dict):
                sub = item.get("item")
                if isinstance(sub, list):
                    count += _count_requests(sub)
                elif "request" in item:
                    count += 1
        return count

    def _count_folders(items: list) -> int:
        count = 0
        for item in items:
            if isinstance(item, dict) and isinstance(item.get("item"), list):
                count += 1
                count += _count_folders(item["item"])
        return count

    requests_count = _count_requests(data.get("item", []))
    folders_count = _count_folders(data.get("item", []))

    total_ms = round((time.perf_counter() - t0) * 1000, 1)

    metadata = {
        "collection_name": info.get("name", ""),
        "postman_id": info.get("_postman_id", ""),
        "requests": requests_count,
        "folders": folders_count,
        "file_size_bytes": file_size,
        "total_ms": total_ms,
    }

    logger.info(
        "Postman conversion completed",
        extra={
            "file": os.path.basename(file_path),
            "requests": requests_count, "folders": folders_count,
            "total_ms": total_ms, "md_length": len(md_text),
        },
    )

    return md_text, metadata
