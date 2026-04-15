"""DOCX -> Markdown converter using Microsoft MarkItDown."""

import logging
import os
import time

from markitdown import MarkItDown

logger = logging.getLogger(__name__)


def convert_docx(file_path: str) -> tuple[str, dict]:
    """Convert a DOCX file to Markdown text.

    Args:
        file_path: Path to the .docx file.

    Returns:
        (markdown_text, metadata) where metadata includes conversion stats.
    """
    t0 = time.perf_counter()
    file_size = os.path.getsize(file_path)

    logger.info(
        "DOCX conversion started",
        extra={"file": os.path.basename(file_path), "file_size_bytes": file_size},
    )

    converter = MarkItDown()
    result = converter.convert(file_path)
    md_text = result.text_content

    total_ms = round((time.perf_counter() - t0) * 1000, 1)

    metadata: dict = {
        "file_size_bytes": file_size,
        "total_ms": total_ms,
    }

    logger.info(
        "DOCX conversion completed",
        extra={
            "file": os.path.basename(file_path),
            "total_ms": total_ms,
            "md_length": len(md_text),
        },
    )

    return md_text, metadata
