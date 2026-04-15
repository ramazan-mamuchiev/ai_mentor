"""Markdown parser: split by H1–H6 headers into sections.

Supports optional YAML front matter (between ``---`` fences at the start of
the file).  When present the front matter is stripped from the body and
returned as a dict so the pipeline can use structured metadata (layer, topic,
related_docs, etc.) without polluting chunk content.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

import yaml

from app.ingestion.chunker import Section
from app.ingestion.text_cleaner import clean_heading, normalize_unicode

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_CODE_FENCE_RE = re.compile(r"```[\s\S]*?```|```[\s\S]*$", re.MULTILINE)
_FRONT_MATTER_RE = re.compile(r"\A---\r?\n(.*?\r?\n)---\r?\n?", re.DOTALL)


@dataclass
class FrontMatter:
    """Structured metadata parsed from YAML front matter."""
    layer: str | None = None
    topic: str | None = None
    doc_number: str | None = None
    related_docs: list[str] = field(default_factory=list)
    chunking: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


def strip_front_matter(text: str) -> tuple[str, FrontMatter | None]:
    """Strip YAML front matter and return (body, parsed FrontMatter | None)."""
    m = _FRONT_MATTER_RE.match(text)
    if not m:
        return text, None
    try:
        data = yaml.safe_load(m.group(1))
    except Exception:
        return text, None
    if not isinstance(data, dict):
        return text, None
    fm = FrontMatter(
        layer=data.get("layer"),
        topic=data.get("topic"),
        doc_number=str(data["doc_number"]) if data.get("doc_number") is not None else None,
        related_docs=data.get("related_docs") or [],
        chunking=data.get("chunking"),
        raw=data,
    )
    body = text[m.end():]
    return body, fm


def _code_block_ranges(text: str) -> list[tuple[int, int]]:
    """Return (start, end) spans of fenced code blocks."""
    return [(m.start(), m.end()) for m in _CODE_FENCE_RE.finditer(text)]


def _inside_code_block(pos: int, ranges: list[tuple[int, int]]) -> bool:
    for start, end in ranges:
        if start <= pos < end:
            return True
        if start > pos:
            break
    return False


def parse_markdown(
    text: str,
    *,
    _strip_fm: bool = True,
) -> tuple[list[Section], FrontMatter | None]:
    """Parse markdown text into sections based on H1–H6 headings.

    Returns ``(sections, front_matter)``.  *front_matter* is ``None`` when the
    file has no YAML front matter block.

    Headings inside fenced code blocks (``\`\`\`…\`\`\```) are ignored.
    """
    text = normalize_unicode(text)

    fm: FrontMatter | None = None
    if _strip_fm:
        text, fm = strip_front_matter(text)

    if not text.strip():
        return [], fm

    code_ranges = _code_block_ranges(text)

    headings: list[tuple[int, str, int]] = []
    for match in _HEADING_RE.finditer(text):
        if _inside_code_block(match.start(), code_ranges):
            continue
        level = len(match.group(1))
        title = clean_heading(match.group(2).strip())
        headings.append((match.start(), title, level))

    if not headings:
        return [Section(heading_path="Document", heading_level=1, content=text.strip())], fm

    sections: list[Section] = []

    preamble = text[: headings[0][0]].strip()
    if preamble:
        sections.append(Section(heading_path="Preamble", heading_level=0, content=preamble))

    heading_stack: list[tuple[int, str]] = []

    for i, (pos, title, level) in enumerate(headings):
        next_pos = headings[i + 1][0] if i + 1 < len(headings) else len(text)
        content_start = text.index("\n", pos) + 1 if "\n" in text[pos:next_pos] else next_pos
        content = text[content_start:next_pos].strip()

        while heading_stack and heading_stack[-1][0] >= level:
            heading_stack.pop()
        heading_stack.append((level, title))

        heading_path = " > ".join(h[1] for h in heading_stack)

        if content:
            sections.append(Section(
                heading_path=heading_path,
                heading_level=level,
                content=content,
            ))

    return sections, fm
