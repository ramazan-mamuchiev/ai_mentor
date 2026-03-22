"""Markdown parser: split by H1–H6 headers into sections."""

import re
import unicodedata

from app.ingestion.chunker import Section
from app.ingestion.text_cleaner import clean_heading, normalize_unicode

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_CODE_FENCE_RE = re.compile(r"```[\s\S]*?```|```[\s\S]*$", re.MULTILINE)


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


def parse_markdown(text: str) -> list[Section]:
    """Parse markdown text into sections based on H1–H6 headings.

    Returns a list of Section objects with heading_path like
    "Chapter > Section > Subsection" and the content under each heading.
    Headings inside fenced code blocks (```...```) are ignored.
    """
    text = normalize_unicode(text)

    if not text.strip():
        return []

    code_ranges = _code_block_ranges(text)

    headings: list[tuple[int, str, int]] = []
    for match in _HEADING_RE.finditer(text):
        if _inside_code_block(match.start(), code_ranges):
            continue
        level = len(match.group(1))
        title = clean_heading(match.group(2).strip())
        headings.append((match.start(), title, level))

    if not headings:
        return [Section(heading_path="Document", heading_level=1, content=text.strip())]

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

    return sections
