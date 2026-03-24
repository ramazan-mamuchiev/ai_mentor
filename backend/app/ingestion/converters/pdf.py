"""PDF -> Markdown converter with optional OCR (EasyOCR).

Two-pass pipeline:
  Pass 1: pymupdf4llm.to_markdown() -- text layer extraction (parallel, chunked)
  Pass 2: OCR images via EasyOCR with auto-detected language

Language detection uses Gemini (same API key as embeddings) between passes.
"""

import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

import pymupdf
import pymupdf4llm

from app.ingestion.converters.ocr import (
    OCR_IMAGE_MIN_AREA,
    detect_language_via_gemini,
    enrich_markdown_with_ocr_files,
    ocr_enabled,
)

logger = logging.getLogger(__name__)

PARALLEL_THRESHOLD = 10
MAX_PDF_WORKERS = 4
MAX_RETRIES = 2
PAGES_PER_CHUNK_SMALL = 2
PAGES_PER_CHUNK_LARGE = 10

_XREF_WIDTH_RE = re.compile(r"/Width\s+(\d+)")
_XREF_HEIGHT_RE = re.compile(r"/Height\s+(\d+)")


def _image_area_from_xref(doc: pymupdf.Document, xref: int) -> int:
    """Get image pixel area from xref metadata without decompressing the image."""
    try:
        obj_str = doc.xref_object(xref)
        w_match = _XREF_WIDTH_RE.search(obj_str)
        h_match = _XREF_HEIGHT_RE.search(obj_str)
        if w_match and h_match:
            return int(w_match.group(1)) * int(h_match.group(1))
    except Exception:
        pass
    return 0


def _find_ocr_pages(
    pdf_path: str,
    progress_callback: Callable[[float], None] | None = None,
) -> list[int]:
    doc = pymupdf.open(pdf_path)
    try:
        ocr_pages: list[int] = []
        total = doc.page_count
        for i in range(total):
            page = doc[i]
            for img_info in page.get_images():
                xref = img_info[0]
                if _image_area_from_xref(doc, xref) >= OCR_IMAGE_MIN_AREA:
                    ocr_pages.append(i)
                    break
            if progress_callback is not None and total > 0:
                progress_callback((i + 1) / total)
        return ocr_pages
    finally:
        doc.close()



def _convert_page_range_with_retry(file_path: str, page_range: list[int]) -> str:
    """Convert pages with retry logic. Top-level for pickle serialisation."""
    _logger = logging.getLogger(__name__)
    for attempt in range(1, MAX_RETRIES + 2):
        try:
            return pymupdf4llm.to_markdown(file_path, pages=page_range)
        except Exception as exc:
            if attempt > MAX_RETRIES:
                _logger.error(
                    "PDF page range conversion failed after all retries",
                    extra={
                        "pages": f"{page_range[0]}-{page_range[-1]}",
                        "attempts": attempt,
                        "error": str(exc)[:300],
                    },
                )
                raise
            _logger.warning(
                "PDF page range conversion failed, retrying",
                extra={
                    "pages": f"{page_range[0]}-{page_range[-1]}",
                    "attempt": attempt,
                    "max_retries": MAX_RETRIES,
                    "error": str(exc)[:200],
                },
            )
            time.sleep(attempt)
    return ""  # unreachable, satisfies type checker


def _split_page_ranges(page_count: int, pages_per_chunk: int = PAGES_PER_CHUNK_SMALL) -> list[list[int]]:
    """Split pages into fixed-size chunks for granular progress reporting."""
    ranges: list[list[int]] = []
    for start in range(0, page_count, pages_per_chunk):
        end = min(start + pages_per_chunk, page_count)
        ranges.append(list(range(start, end)))
    return ranges


def convert_pdf(
    file_path: str,
    progress_callback: Callable[[float, str], None] | None = None,
) -> tuple[str, dict]:
    """Convert PDF to Markdown text with parallel page processing and OCR.

    Two-pass pipeline:
      Pass 1: pymupdf4llm text extraction (parallel for large PDFs)
      Pass 2: OCR all images with auto-detected language via Gemini + EasyOCR

    Language is detected automatically via Gemini after Pass 1.
    Falls back to English if detection fails.

    Progress is reported via callback: progress_callback(fraction, stage)
    where fraction is in [0..1] and stage is "converting" or "ocr".
    If images found: converting = 0→0.625, OCR = 0.625→1.0.
    If no images: converting = full 0→1.0 range.

    Args:
        file_path: Path to the PDF file.
        progress_callback: fn(fraction, stage) called as conversion progresses.

    Returns:
        (markdown_text, metadata) where metadata includes conversion stats.
    """
    t0 = time.perf_counter()
    file_size = os.path.getsize(file_path)
    doc = pymupdf.open(file_path)
    page_count = doc.page_count
    doc.close()

    if progress_callback is not None:
        progress_callback(0.0, "analyzing")

    def _analyze_cb(frac: float) -> None:
        if progress_callback is not None:
            progress_callback(frac * 0.05, "analyzing")

    ocr_pages = _find_ocr_pages(file_path, progress_callback=_analyze_cb)
    has_ocr_images = len(ocr_pages) > 0
    will_ocr = has_ocr_images and ocr_enabled()

    if progress_callback is not None:
        if will_ocr:
            _convert_cb = lambda frac: progress_callback(0.05 + frac * 0.575, "converting")
            _ocr_cb = lambda frac: progress_callback(0.625 + frac * 0.375, "ocr")
        else:
            _convert_cb = lambda frac: progress_callback(0.05 + frac * 0.95, "converting")
            _ocr_cb = None
    else:
        _convert_cb = None
        _ocr_cb = None

    logger.info(
        "PDF conversion started",
        extra={
            "file": os.path.basename(file_path), "pages": page_count,
            "file_size_bytes": file_size,
            "parallel": page_count > PARALLEL_THRESHOLD,
            "will_ocr": will_ocr,
        },
    )

    chunk_size = PAGES_PER_CHUNK_LARGE if page_count > PARALLEL_THRESHOLD else PAGES_PER_CHUNK_SMALL
    page_ranges = _split_page_ranges(page_count, pages_per_chunk=chunk_size)
    total_ranges = len(page_ranges)

    if page_count > PARALLEL_THRESHOLD:
        num_workers = min(MAX_PDF_WORKERS, page_count)
        results: dict[int, str] = {}
        completed_count = 0

        logger.info(
            "Parallel PDF conversion",
            extra={
                "workers": num_workers,
                "total_chunks": total_ranges,
                "pages_per_chunk": chunk_size,
            },
        )

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            future_to_idx = {
                executor.submit(_convert_page_range_with_retry, file_path, pr): idx
                for idx, pr in enumerate(page_ranges)
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                results[idx] = future.result()
                completed_count += 1
                if _convert_cb is not None:
                    _convert_cb(completed_count / total_ranges)

        md_text = "\n\n".join(results[i] for i in range(total_ranges))
    else:
        page_results: dict[int, str] = {}
        for idx, pr in enumerate(page_ranges):
            for attempt in range(1, MAX_RETRIES + 2):
                try:
                    page_results[idx] = pymupdf4llm.to_markdown(file_path, pages=pr)
                    break
                except Exception as exc:
                    if attempt > MAX_RETRIES:
                        raise
                    logger.warning(
                        "PDF page conversion failed, retrying",
                        extra={"page": pr[0], "attempt": attempt, "error": str(exc)[:200]},
                    )
                    time.sleep(attempt)
            if _convert_cb is not None:
                _convert_cb((idx + 1) / total_ranges)

        md_text = "\n\n".join(page_results[i] for i in range(total_ranges))

    convert_ms = round((time.perf_counter() - t0) * 1000, 1)

    metadata: dict = {
        "pages": page_count,
        "file_size_bytes": file_size,
        "convert_ms": convert_ms,
        "ocr_applied": False,
        "parallel_workers": min(MAX_PDF_WORKERS, page_count) if page_count > PARALLEL_THRESHOLD else 1,
    }

    if will_ocr:
        detected_langs = detect_language_via_gemini(md_text)
        metadata["detected_languages"] = detected_langs
        metadata["detected_languages_str"] = ",".join(detected_langs)

        t_ocr = time.perf_counter()
        md_text, ocr_stats = enrich_markdown_with_ocr_files(
            md_text, languages=detected_langs,
            progress_callback=_ocr_cb,
        )
        ocr_ms = round((time.perf_counter() - t_ocr) * 1000, 1)
        metadata["ocr_applied"] = True
        metadata["ocr_ms"] = ocr_ms
        metadata["ocr_stats"] = ocr_stats
        logger.info(
            "OCR completed",
            extra={
                "ocr_ms": ocr_ms,
                "detected_languages": detected_langs,
                "ocr_images_total": ocr_stats["ocr_images_total"],
                "ocr_images_success": ocr_stats["ocr_images_success"],
                "ocr_images_failed": ocr_stats["ocr_images_failed"],
            },
        )

    total_ms = round((time.perf_counter() - t0) * 1000, 1)
    metadata["total_ms"] = total_ms

    logger.info(
        "PDF conversion completed",
        extra={
            "file": os.path.basename(file_path), "pages": page_count,
            "total_ms": total_ms, "ocr_applied": metadata["ocr_applied"],
            "md_length": len(md_text),
        },
    )

    return md_text, metadata
