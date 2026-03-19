"""Convert .proto (Protocol Buffers / gRPC) files to structured Markdown.

The converter parses proto3 syntax and produces Markdown that is optimised
for semantic search: services become sections with method signatures,
messages become tables of fields, and enums become bullet lists.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TextIO


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


_RE_SYNTAX = re.compile(r'syntax\s*=\s*"([^"]+)"')
_RE_PACKAGE = re.compile(r"package\s+([\w.]+)\s*;")
_RE_IMPORT = re.compile(r'import\s+"([^"]+)"\s*;')
_RE_OPTION = re.compile(r'option\s+([\w.]+)\s*=\s*"?([^";]+)"?\s*;')
_RE_SERVICE = re.compile(r"service\s+(\w+)\s*\{")
_RE_RPC = re.compile(
    r"rpc\s+(\w+)\s*\(\s*(stream\s+)?(\S+)\s*\)\s*returns\s*\(\s*(stream\s+)?(\S+)\s*\)"
)
_RE_MESSAGE = re.compile(r"message\s+(\w+)\s*\{")
_RE_ENUM = re.compile(r"enum\s+(\w+)\s*\{")
_RE_ONEOF = re.compile(r"oneof\s+(\w+)\s*\{")
_RE_MAP_FIELD = re.compile(
    r"(map<[^>]+>)\s+(\w+)\s*=\s*(\d+)\s*;"
)
_RE_FIELD = re.compile(
    r"(repeated\s+|optional\s+)?"
    r"(\S+)\s+(\w+)\s*=\s*(\d+)\s*;"
)
_RE_ENUM_VALUE = re.compile(r"(\w+)\s*=\s*(-?\d+)\s*;")
_RE_COMMENT_LINE = re.compile(r"^\s*//\s?(.*)")
_RE_BLOCK_COMMENT_START = re.compile(r"/\*")
_RE_BLOCK_COMMENT_END = re.compile(r"\*/")


def _strip_inline_comment(line: str) -> tuple[str, str]:
    """Return (code_part, inline_comment)."""
    in_string = False
    for i, ch in enumerate(line):
        if ch == '"':
            in_string = not in_string
        if not in_string and line[i:i+2] == "//":
            return line[:i].rstrip(), line[i+2:].strip()
    return line, ""


class _Parser:
    """Simple state-machine parser for proto3 files."""

    def __init__(self, text: str):
        self.lines = text.splitlines()
        self.pos = 0
        self.result = ProtoFile()

    def parse(self) -> ProtoFile:
        self._skip_whitespace()
        while self.pos < len(self.lines):
            line = self.lines[self.pos].strip()

            if not line or line.startswith("//"):
                self.pos += 1
                continue

            if line.startswith("/*"):
                self._skip_block_comment()
                continue

            m = _RE_SYNTAX.search(line)
            if m:
                self.result.syntax = m.group(1)
                self.pos += 1
                continue

            m = _RE_PACKAGE.search(line)
            if m:
                self.result.package = m.group(1)
                self.pos += 1
                continue

            m = _RE_IMPORT.search(line)
            if m:
                self.result.imports.append(m.group(1))
                self.pos += 1
                continue

            m = _RE_OPTION.search(line)
            if m:
                self.result.options[m.group(1)] = m.group(2)
                self.pos += 1
                continue

            m = _RE_SERVICE.search(line)
            if m:
                comment = self._collect_preceding_comment()
                svc = self._parse_service(m.group(1))
                svc.comment = comment
                self.result.services.append(svc)
                continue

            m = _RE_MESSAGE.search(line)
            if m:
                comment = self._collect_preceding_comment()
                msg = self._parse_message(m.group(1))
                msg.comment = comment
                self.result.messages.append(msg)
                continue

            m = _RE_ENUM.search(line)
            if m:
                comment = self._collect_preceding_comment()
                en = self._parse_enum(m.group(1))
                en.comment = comment
                self.result.enums.append(en)
                continue

            self.pos += 1

        return self.result

    def _skip_whitespace(self):
        while self.pos < len(self.lines) and not self.lines[self.pos].strip():
            self.pos += 1

    def _skip_block_comment(self):
        while self.pos < len(self.lines):
            if "*/" in self.lines[self.pos]:
                self.pos += 1
                return
            self.pos += 1

    def _collect_preceding_comment(self) -> str:
        """Look backwards from current pos to collect // comment lines."""
        comments: list[str] = []
        i = self.pos - 1
        while i >= 0:
            m = _RE_COMMENT_LINE.match(self.lines[i])
            if m:
                comments.append(m.group(1))
                i -= 1
            else:
                break
        comments.reverse()
        return "\n".join(comments).strip()

    def _parse_service(self, name: str) -> ProtoService:
        svc = ProtoService(name=name)
        self.pos += 1
        brace_depth = 1
        while self.pos < len(self.lines) and brace_depth > 0:
            line = self.lines[self.pos].strip()
            if not line or line.startswith("//"):
                self.pos += 1
                continue
            if line.startswith("/*"):
                self._skip_block_comment()
                continue

            brace_depth += line.count("{") - line.count("}")

            m = _RE_RPC.search(line)
            if m:
                comment = self._collect_preceding_comment()
                method = ProtoMethod(
                    name=m.group(1),
                    input_type=m.group(3),
                    output_type=m.group(5),
                    client_streaming=bool(m.group(2)),
                    server_streaming=bool(m.group(4)),
                    comment=comment,
                )
                svc.methods.append(method)

            if brace_depth <= 0:
                self.pos += 1
                break

            self.pos += 1
        return svc

    def _parse_message(self, name: str) -> ProtoMessage:
        msg = ProtoMessage(name=name)
        self.pos += 1
        brace_depth = 1
        while self.pos < len(self.lines) and brace_depth > 0:
            line = self.lines[self.pos].strip()
            if not line or line.startswith("//"):
                self.pos += 1
                continue
            if line.startswith("/*"):
                self._skip_block_comment()
                continue

            code, inline_comment = _strip_inline_comment(line)

            m = _RE_MESSAGE.search(code)
            if m:
                comment = self._collect_preceding_comment()
                nested = self._parse_message(m.group(1))
                nested.comment = comment
                msg.nested_messages.append(nested)
                continue

            m = _RE_ENUM.search(code)
            if m:
                comment = self._collect_preceding_comment()
                en = self._parse_enum(m.group(1))
                en.comment = comment
                msg.nested_enums.append(en)
                continue

            m = _RE_ONEOF.search(code)
            if m:
                oneof = self._parse_oneof(m.group(1))
                msg.oneofs.append(oneof)
                continue

            brace_depth += code.count("{") - code.count("}")
            if brace_depth <= 0:
                self.pos += 1
                break

            m = _RE_MAP_FIELD.search(code)
            if m:
                comment = inline_comment or self._collect_preceding_comment()
                fld = ProtoField(
                    label=m.group(1),
                    type=m.group(1),
                    name=m.group(2),
                    number=int(m.group(3)),
                    comment=comment,
                )
                msg.fields.append(fld)
                self.pos += 1
                continue

            m = _RE_FIELD.search(code)
            if m:
                comment = inline_comment or self._collect_preceding_comment()
                label = (m.group(1) or "").strip()
                fld = ProtoField(
                    label=label,
                    type=m.group(2),
                    name=m.group(3),
                    number=int(m.group(4)),
                    comment=comment,
                )
                msg.fields.append(fld)

            self.pos += 1
        return msg

    def _parse_oneof(self, name: str) -> ProtoOneOf:
        oneof = ProtoOneOf(name=name)
        self.pos += 1
        brace_depth = 1
        while self.pos < len(self.lines) and brace_depth > 0:
            line = self.lines[self.pos].strip()
            code, inline_comment = _strip_inline_comment(line)
            brace_depth += code.count("{") - code.count("}")
            if brace_depth <= 0:
                self.pos += 1
                break
            m = _RE_FIELD.search(code)
            if m:
                fld = ProtoField(
                    label=(m.group(1) or "").strip(),
                    type=m.group(2),
                    name=m.group(3),
                    number=int(m.group(4)),
                    comment=inline_comment,
                )
                oneof.fields.append(fld)
            self.pos += 1
        return oneof

    def _parse_enum(self, name: str) -> ProtoEnum:
        en = ProtoEnum(name=name, values=[])
        self.pos += 1
        brace_depth = 1
        while self.pos < len(self.lines) and brace_depth > 0:
            line = self.lines[self.pos].strip()
            code, _ = _strip_inline_comment(line)
            brace_depth += code.count("{") - code.count("}")
            if brace_depth <= 0:
                self.pos += 1
                break
            m = _RE_ENUM_VALUE.search(code)
            if m:
                en.values.append((m.group(1), int(m.group(2))))
            self.pos += 1
        return en


def parse_proto(text: str) -> ProtoFile:
    """Parse proto3 source text into a structured ProtoFile."""
    return _Parser(text).parse()


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

    for method in svc.methods:
        in_stream = "stream " if method.client_streaming else ""
        out_stream = "stream " if method.server_streaming else ""
        sig = f"`rpc {method.name}({in_stream}{method.input_type}) returns ({out_stream}{method.output_type})`"
        lines.append(f"- {sig}")
        if method.comment:
            lines.append(f"  - {method.comment}")
    lines.append("")
    return "\n".join(lines)


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
