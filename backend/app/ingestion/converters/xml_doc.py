"""XML documentation converter (DocBook, DITA, XSD, generic XML → Markdown).

Strips XML tags, preserves structure via heading-level mapping, extracts
text content, and produces clean Markdown suitable for RAG chunking.
"""

from __future__ import annotations

import logging
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

logger = logging.getLogger(__name__)

_HEADING_TAGS = {
    "book": 1, "article": 1, "specification": 1,
    "part": 1, "chapter": 2, "section": 3, "sect1": 3, "sect2": 4, "sect3": 5,
    "appendix": 2, "preface": 2, "glossary": 2, "bibliography": 2,
    "refentry": 2, "refsect1": 3, "refsect2": 4,
    # DITA
    "topic": 1, "concept": 1, "task": 1, "reference": 1,
}

_SKIP_TAGS = frozenset({
    "xi:include", "index", "indexterm", "mediaobject", "imageobject",
    "imagedata", "inlinemediaobject",
})

_INLINE_CODE_TAGS = frozenset({
    "code", "literal", "command", "filename", "option", "varname",
    "type", "classname", "function", "parameter", "constant",
    "computeroutput", "userinput", "systemitem",
})

_BLOCK_CODE_TAGS = frozenset({
    "programlisting", "screen", "synopsis", "literallayout",
})

_LIST_ITEM_TAGS = frozenset({"listitem", "member", "step"})


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _extract_title(elem: ET.Element) -> str:
    for child in elem:
        if _local_name(child.tag) == "title":
            return "".join(child.itertext()).strip()
    return ""


def _elem_to_markdown(elem: ET.Element, depth: int = 1) -> list[str]:
    lines: list[str] = []
    tag = _local_name(elem.tag)

    if tag in _SKIP_TAGS:
        return lines

    heading_level = _HEADING_TAGS.get(tag)
    if heading_level is not None:
        title = _extract_title(elem)
        if title:
            level = min(heading_level + depth - 1, 6)
            lines.append(f"\n{'#' * level} {title}\n")

    if tag in _BLOCK_CODE_TAGS:
        text = "".join(elem.itertext()).strip()
        if text:
            lines.append(f"\n```\n{text}\n```\n")
        return lines

    if tag == "table" or tag == "informaltable":
        text = "".join(elem.itertext()).strip()
        if text:
            lines.append(f"\n{text}\n")
        return lines

    if tag in _LIST_ITEM_TAGS:
        text = "".join(elem.itertext()).strip()
        if text:
            lines.append(f"- {text}")
        return lines

    if tag == "para" or tag == "simpara":
        parts: list[str] = []
        if elem.text:
            parts.append(elem.text)
        for child in elem:
            child_tag = _local_name(child.tag)
            if child_tag in _INLINE_CODE_TAGS:
                code_text = "".join(child.itertext()).strip()
                if code_text:
                    parts.append(f"`{code_text}`")
            elif child_tag == "emphasis":
                em_text = "".join(child.itertext()).strip()
                role = child.get("role", "")
                if role == "bold" or role == "strong":
                    parts.append(f"**{em_text}**")
                else:
                    parts.append(f"*{em_text}*")
            elif child_tag == "link" or child_tag == "ulink":
                link_text = "".join(child.itertext()).strip()
                url = child.get("url", child.get("{http://www.w3.org/1999/xlink}href", ""))
                if url and link_text:
                    parts.append(f"[{link_text}]({url})")
                elif link_text:
                    parts.append(link_text)
            elif child_tag == "xref":
                linkend = child.get("linkend", "")
                parts.append(f"[{linkend}]")
            else:
                child_text = "".join(child.itertext()).strip()
                if child_text:
                    parts.append(child_text)
            if child.tail:
                parts.append(child.tail)

        full = " ".join(p.strip() for p in parts if p and p.strip())
        if full:
            lines.append(f"\n{full}\n")
        return lines

    if tag == "title":
        return lines

    for child in elem:
        child_lines = _elem_to_markdown(child, depth)
        lines.extend(child_lines)

    if elem.text and elem.text.strip() and tag not in ("title",) and not lines:
        lines.append(elem.text.strip())

    return lines


def convert_xml_doc(file_path: str) -> tuple[str, dict]:
    """Convert an XML documentation file to Markdown.

    Returns:
        (markdown_text, metadata_dict)
    """
    t0 = time.perf_counter()
    path = Path(file_path)
    raw = path.read_bytes()

    metadata: dict = {
        "converter": "xml_doc",
        "file_size_bytes": len(raw),
    }

    try:
        text = raw.decode("utf-8", errors="replace")
        text = re.sub(r"<!DOCTYPE[^>]*>", "", text)
        text = re.sub(r"<!ENTITY[^>]*>", "", text)

        root = ET.fromstring(text)
    except ET.ParseError as e:
        logger.warning("XML parse failed, falling back to tag-stripping", extra={
            "file": file_path, "error": str(e)[:200],
        })
        plain = re.sub(r"<[^>]+>", " ", raw.decode("utf-8", errors="replace"))
        plain = re.sub(r"\s+", " ", plain).strip()
        metadata["parse_mode"] = "fallback_strip"
        metadata["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        return plain, metadata

    root_tag = _local_name(root.tag)
    metadata["root_tag"] = root_tag

    lines = _elem_to_markdown(root, depth=1)
    md = "\n".join(lines).strip()

    md = re.sub(r"\n{3,}", "\n\n", md)

    metadata["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    metadata["markdown_length"] = len(md)

    return md, metadata
