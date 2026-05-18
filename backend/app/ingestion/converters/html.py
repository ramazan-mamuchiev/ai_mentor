"""HTML -> Markdown converter.

Reuses MarkItDown (already used for DOCX) as the primary converter.
Falls back to markdownify (already used for Confluence/site crawl)
when MarkItDown produces too little content — this happens with
heavily-scripted API documentation pages (e.g. Swagger-UI-like HTML
files exported from vendor tools).
"""

import logging
import os
import time

from markdownify import markdownify as md_convert
from markitdown import MarkItDown

logger = logging.getLogger(__name__)

_MARKITDOWN_MIN_CHARS = 200


def convert_html(file_path: str) -> tuple[str, dict]:
    """Convert an HTML file to Markdown text.

    Args:
        file_path: Path to the .html / .htm file.

    Returns:
        (markdown_text, metadata) where metadata includes conversion stats.
    """
    t0 = time.perf_counter()
    file_size = os.path.getsize(file_path)

    logger.info(
        "HTML conversion started",
        extra={"file": os.path.basename(file_path), "file_size_bytes": file_size},
    )

    method = "markitdown"
    converter = MarkItDown()
    result = converter.convert(file_path)
    md_text = result.text_content

    if len(md_text.strip()) < _MARKITDOWN_MIN_CHARS:
        logger.debug(
            "MarkItDown output too short, falling back to markdownify",
            extra={"markitdown_len": len(md_text), "file": os.path.basename(file_path)},
        )
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            raw_html = f.read()

        md_text = md_convert(
            raw_html,
            heading_style="ATX",
            bullets="-",
            strip=["script", "style", "nav", "footer"],
        )
        md_text = _clean_blank_lines(md_text)
        method = "markdownify"

    total_ms = round((time.perf_counter() - t0) * 1000, 1)

    metadata: dict = {
        "file_size_bytes": file_size,
        "total_ms": total_ms,
        "method": method,
    }

    logger.info(
        "HTML conversion completed",
        extra={
            "file": os.path.basename(file_path),
            "total_ms": total_ms,
            "md_length": len(md_text),
            "method": method,
        },
    )

    return md_text, metadata


def _clean_blank_lines(text: str) -> str:
    """Collapse 3+ consecutive blank lines into 2."""
    lines = text.split("\n")
    cleaned: list[str] = []
    blank_count = 0
    for line in lines:
        stripped = line.rstrip()
        if not stripped:
            blank_count += 1
            if blank_count <= 2:
                cleaned.append("")
        else:
            blank_count = 0
            cleaned.append(stripped)
    return "\n".join(cleaned).strip()
