"""Convert .proto (Protocol Buffers / gRPC) files to structured Markdown.

The converter uses ``proto-schema-parser`` (ANTLR-based, Buf grammar) to
parse any valid proto2/proto3/editions file and produces Markdown optimised
for semantic search: services become sections with method signatures,
messages become tables of fields, and enums become bullet lists.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from proto_schema_parser import ast as proto_ast
from proto_schema_parser.parser import Parser as _SchemaParser


# ---------------------------------------------------------------------------
# Internal domain model (stable API used by renderers and tests)
# ---------------------------------------------------------------------------

@dataclass
class ProtoEnum:
    name: str
    values: list[tuple[str, int]]  # (name, number)
    comment: str = ""


@dataclass
class ProtoField:
    label: str  # "", "repeated", "optional", "map<K,V>"
    type: str
    name: str
    number: int
    comment: str = ""


@dataclass
class ProtoOneOf:
    name: str
    fields: list[ProtoField] = field(default_factory=list)


@dataclass
class ProtoMessage:
    name: str
    fields: list[ProtoField] = field(default_factory=list)
    oneofs: list[ProtoOneOf] = field(default_factory=list)
    nested_messages: list["ProtoMessage"] = field(default_factory=list)
    nested_enums: list[ProtoEnum] = field(default_factory=list)
    comment: str = ""


@dataclass
class ProtoMethod:
    name: str
    input_type: str
    output_type: str
    client_streaming: bool = False
    server_streaming: bool = False
    comment: str = ""


@dataclass
class ProtoService:
    name: str
    methods: list[ProtoMethod] = field(default_factory=list)
    comment: str = ""


@dataclass
class ProtoFile:
    syntax: str = "proto3"
    package: str = ""
    imports: list[str] = field(default_factory=list)
    options: dict[str, str] = field(default_factory=dict)
    services: list[ProtoService] = field(default_factory=list)
    messages: list[ProtoMessage] = field(default_factory=list)
    enums: list[ProtoEnum] = field(default_factory=list)


# ---------------------------------------------------------------------------
# AST adapter: proto_schema_parser AST  ->  our domain model
# ---------------------------------------------------------------------------

_COMMENT_PREFIX = re.compile(r"^(?://\s?|/\*\s?|\s?\*/?\s?)")


def _strip_comment_markers(text: str) -> str:
    """Remove ``//``, ``/*``, ``*/`` prefixes from a comment string."""
    lines: list[str] = []
    for line in text.splitlines():
        cleaned = _COMMENT_PREFIX.sub("", line).rstrip()
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines)


def _collect_comment(elements: list, index: int) -> str:
    """Walk backwards from *index* collecting adjacent Comment nodes."""
    parts: list[str] = []
    i = index - 1
    while i >= 0 and isinstance(elements[i], proto_ast.Comment) and not elements[i].inline:
        parts.append(_strip_comment_markers(elements[i].text))
        i -= 1
    parts.reverse()
    return "\n".join(parts).strip()


def _collect_inline_comment(elements: list, index: int) -> str:
    """Look at the element right after *index* for an inline comment."""
    nxt = index + 1
    if nxt < len(elements) and isinstance(elements[nxt], proto_ast.Comment) and elements[nxt].inline:
        return _strip_comment_markers(elements[nxt].text)
    return ""


def _convert_field(f: proto_ast.Field, comment: str = "") -> ProtoField:
    if f.cardinality is proto_ast.FieldCardinality.REPEATED:
        label = "repeated"
    elif f.cardinality is proto_ast.FieldCardinality.OPTIONAL:
        label = "optional"
    elif f.cardinality is proto_ast.FieldCardinality.REQUIRED:
        label = "required"
    else:
        label = ""
    return ProtoField(
        label=label,
        type=f.type,
        name=f.name,
        number=f.number,
        comment=comment,
    )


def _convert_map_field(mf: proto_ast.MapField, comment: str = "") -> ProtoField:
    map_type = f"map<{mf.key_type}, {mf.value_type}>"
    return ProtoField(
        label=map_type,
        type=map_type,
        name=mf.name,
        number=mf.number,
        comment=comment,
    )


def _convert_enum(node: proto_ast.Enum, comment: str = "") -> ProtoEnum:
    values: list[tuple[str, int]] = []
    for el in node.elements:
        if isinstance(el, proto_ast.EnumValue):
            values.append((el.name, el.number))
    return ProtoEnum(name=node.name, values=values, comment=comment)


def _convert_oneof(node: proto_ast.OneOf) -> ProtoOneOf:
    oneof = ProtoOneOf(name=node.name)
    elements = node.elements
    for i, el in enumerate(elements):
        if isinstance(el, proto_ast.Field):
            cmt = _collect_inline_comment(elements, i) or _collect_comment(elements, i)
            oneof.fields.append(_convert_field(el, cmt))
    return oneof


def _convert_message(node: proto_ast.Message, comment: str = "") -> ProtoMessage:
    msg = ProtoMessage(name=node.name, comment=comment)
    elements = node.elements
    for i, el in enumerate(elements):
        if isinstance(el, proto_ast.Field):
            cmt = _collect_inline_comment(elements, i) or _collect_comment(elements, i)
            msg.fields.append(_convert_field(el, cmt))
        elif isinstance(el, proto_ast.MapField):
            cmt = _collect_inline_comment(elements, i) or _collect_comment(elements, i)
            msg.fields.append(_convert_map_field(el, cmt))
        elif isinstance(el, proto_ast.OneOf):
            msg.oneofs.append(_convert_oneof(el))
        elif isinstance(el, proto_ast.Message):
            nested_cmt = _collect_comment(elements, i)
            msg.nested_messages.append(_convert_message(el, nested_cmt))
        elif isinstance(el, proto_ast.Enum):
            nested_cmt = _collect_comment(elements, i)
            msg.nested_enums.append(_convert_enum(el, nested_cmt))
    return msg


def _convert_method(node: proto_ast.Method, comment: str = "") -> ProtoMethod:
    return ProtoMethod(
        name=node.name,
        input_type=node.input_type.type,
        output_type=node.output_type.type,
        client_streaming=node.input_type.stream,
        server_streaming=node.output_type.stream,
        comment=comment,
    )


def _convert_service(node: proto_ast.Service, comment: str = "") -> ProtoService:
    svc = ProtoService(name=node.name, comment=comment)
    elements = node.elements
    for i, el in enumerate(elements):
        if isinstance(el, proto_ast.Method):
            method_cmt = _collect_comment(elements, i)
            svc.methods.append(_convert_method(el, method_cmt))
    return svc


def _convert_ast(ast_file: proto_ast.File) -> ProtoFile:
    """Convert a ``proto_schema_parser`` AST into our domain :class:`ProtoFile`."""
    result = ProtoFile(
        syntax=ast_file.syntax or ast_file.edition or "proto3",
    )

    elements = ast_file.file_elements
    for i, el in enumerate(elements):
        if isinstance(el, proto_ast.Package):
            result.package = el.name
        elif isinstance(el, proto_ast.Import):
            result.imports.append(el.name)
        elif isinstance(el, proto_ast.Option):
            result.options[el.name] = str(el.value)
        elif isinstance(el, proto_ast.Service):
            cmt = _collect_comment(elements, i)
            result.services.append(_convert_service(el, cmt))
        elif isinstance(el, proto_ast.Message):
            cmt = _collect_comment(elements, i)
            result.messages.append(_convert_message(el, cmt))
        elif isinstance(el, proto_ast.Enum):
            cmt = _collect_comment(elements, i)
            result.enums.append(_convert_enum(el, cmt))

    return result


# ---------------------------------------------------------------------------
# Public parsing API
# ---------------------------------------------------------------------------

def parse_proto(text: str) -> ProtoFile:
    """Parse proto source text into a structured :class:`ProtoFile`.

    Supports proto2, proto3, and protobuf editions.  Formatting style
    (K&R, Allman, mixed, minified) does not matter — the ANTLR-based
    parser works on tokens, not lines.
    """
    ast_file = _SchemaParser().parse(text)
    return _convert_ast(ast_file)


# ---------------------------------------------------------------------------
# Markdown rendering  (unchanged — operates on our domain model)
# ---------------------------------------------------------------------------

def _render_enum_md(enum: ProtoEnum, heading_level: int = 3) -> str:
    hashes = "#" * heading_level
    lines = [f"{hashes} Enum `{enum.name}`", ""]
    if enum.comment:
        lines.append(enum.comment)
        lines.append("")
    for name, num in enum.values:
        lines.append(f"- `{name}` = {num}")
    lines.append("")
    return "\n".join(lines)


def _render_message_md(msg: ProtoMessage, heading_level: int = 3) -> str:
    hashes = "#" * heading_level
    lines = [f"{hashes} Message `{msg.name}`", ""]
    if msg.comment:
        lines.append(msg.comment)
        lines.append("")

    all_fields = list(msg.fields)
    for oneof in msg.oneofs:
        all_fields.extend(oneof.fields)

    if all_fields:
        proto_lines = [f"message {msg.name} {{"]
        for f in msg.fields:
            label = f"{f.label} " if f.label else ""
            proto_lines.append(f"  {label}{f.type} {f.name} = {f.number};")
        for oneof in msg.oneofs:
            proto_lines.append(f"  oneof {oneof.name} {{")
            for f in oneof.fields:
                proto_lines.append(f"    {f.type} {f.name} = {f.number};")
            proto_lines.append("  }")
        proto_lines.append("}")
        lines.append("```protobuf")
        lines.extend(proto_lines)
        lines.append("```")
        lines.append("")

    if msg.fields:
        lines.append("| # | Field | Type | Label | Description |")
        lines.append("|---|-------|------|-------|-------------|")
        for f in msg.fields:
            label = f.label if f.label else ""
            lines.append(f"| {f.number} | `{f.name}` | `{f.type}` | {label} | {f.comment} |")
        lines.append("")

    for oneof in msg.oneofs:
        lines.append(f"**oneof** `{oneof.name}`:")
        lines.append("")
        lines.append("| # | Field | Type | Description |")
        lines.append("|---|-------|------|-------------|")
        for f in oneof.fields:
            lines.append(f"| {f.number} | `{f.name}` | `{f.type}` | {f.comment} |")
        lines.append("")

    for nested_enum in msg.nested_enums:
        lines.append(_render_enum_md(nested_enum, heading_level + 1))

    for nested_msg in msg.nested_messages:
        lines.append(_render_message_md(nested_msg, heading_level + 1))

    return "\n".join(lines)


def _render_service_md(svc: ProtoService, heading_level: int = 2) -> str:
    hashes = "#" * heading_level
    lines = [f"{hashes} Service `{svc.name}`", ""]
    if svc.comment:
        lines.append(svc.comment)
        lines.append("")

    if svc.methods:
        proto_lines = [f"service {svc.name} {{"]
        for method in svc.methods:
            in_s = "stream " if method.client_streaming else ""
            out_s = "stream " if method.server_streaming else ""
            proto_lines.append(
                f"  rpc {method.name}({in_s}{method.input_type}) "
                f"returns ({out_s}{method.output_type});"
            )
        proto_lines.append("}")
        lines.append("```protobuf")
        lines.extend(proto_lines)
        lines.append("```")
        lines.append("")

    for method in svc.methods:
        if method.comment:
            in_s = "stream " if method.client_streaming else ""
            out_s = "stream " if method.server_streaming else ""
            lines.append(
                f"- `rpc {method.name}({in_s}{method.input_type}) "
                f"returns ({out_s}{method.output_type})`"
            )
            lines.append(f"  - {method.comment}")

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public conversion API
# ---------------------------------------------------------------------------

def convert_proto(text: str, filename: str = "") -> tuple[str, dict]:
    """Convert a .proto file to Markdown.

    Returns:
        Tuple of (markdown_text, metadata_dict).
    """
    proto = parse_proto(text)

    parts: list[str] = []

    title = filename or "Proto Definition"
    parts.append(f"# {title}")
    parts.append("")

    if proto.package:
        parts.append(f"**Package:** `{proto.package}`")
        parts.append("")

    if proto.syntax:
        parts.append(f"**Syntax:** {proto.syntax}")
        parts.append("")

    if proto.imports:
        parts.append("**Imports:**")
        for imp in proto.imports:
            parts.append(f"- `{imp}`")
        parts.append("")

    if proto.options:
        parts.append("**Options:**")
        for k, v in proto.options.items():
            parts.append(f"- `{k}` = `{v}`")
        parts.append("")

    for svc in proto.services:
        parts.append(_render_service_md(svc))

    if proto.messages:
        parts.append("## Messages")
        parts.append("")
        for msg in proto.messages:
            parts.append(_render_message_md(msg))

    if proto.enums:
        parts.append("## Enums")
        parts.append("")
        for enum in proto.enums:
            parts.append(_render_enum_md(enum))

    markdown = "\n".join(parts)

    metadata = {
        "syntax": proto.syntax,
        "package": proto.package,
        "services": len(proto.services),
        "messages": len(proto.messages),
        "enums": len(proto.enums),
        "methods": sum(len(s.methods) for s in proto.services),
    }

    return markdown, metadata


def convert_proto_file(file_path: str, original_filename: str = "") -> tuple[str, dict]:
    """Read a .proto file from disk and convert to Markdown.

    Args:
        file_path: Path to the .proto file on disk (may be a temp file).
        original_filename: Original filename to use in the Markdown title.
            Falls back to basename of file_path if not provided.
    """
    import os
    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()
    filename = original_filename or os.path.basename(file_path)
    return convert_proto(text, filename)
