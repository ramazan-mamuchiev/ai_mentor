"""PDF -> Markdown converter with optional OCR (EasyOCR).

OCR is optional: if easyocr is not installed, PDF conversion works
without OCR (text-only extraction via pymupdf4llm).
"""

import logging
import math
import os
import re
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Callable

import pymupdf
import pymupdf4llm

logger = logging.getLogger(__name__)

PARALLEL_THRESHOLD = 10
MAX_PDF_WORKERS = 4
MAX_RETRIES = 2

_OCR_IMAGE_MIN_AREA = 100_000
_IMG_REF_RE = re.compile(r"!\[([^\]]*)\]\(((?:[^()]*|\([^()]*\))*)\)")

_ocr_reader = None
_ocr_reader_langs: list[str] = []


def _ocr_available() -> bool:
    try:
        import easyocr  # noqa: F401
        return True
    except ImportError:
        return False


def _get_ocr_reader(languages: list[str] | None = None):
    global _ocr_reader, _ocr_reader_langs
    langs = languages or ["en"]
    if _ocr_reader is None or _ocr_reader_langs != langs:
        import easyocr
        logger.info("Loading OCR model", extra={"languages": langs})
        t0 = time.perf_counter()
        _ocr_reader = easyocr.Reader(langs, gpu=False, verbose=False)
        duration_sec = round(time.perf_counter() - t0, 2)
        logger.info("OCR model loaded", extra={"languages": langs, "duration_sec": duration_sec})
        _ocr_reader_langs = langs
    return _ocr_reader


def _ocr_image_file(image_path: str, languages: list[str] | None = None) -> str:
    import io
    import numpy as np
    from PIL import Image

    img = np.array(Image.open(image_path))
    reader = _get_ocr_reader(languages)

    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setLevel(logging.WARNING)
    cv_logger = logging.getLogger("cv2")
    cv_logger.addHandler(handler)
    try:
        results = reader.readtext(img)
    finally:
        cv_logger.removeHandler(handler)

    return " ".join(item[1] for item in results if item[1].strip())


def _find_ocr_pages(pdf_path: str) -> list[int]:
    doc = pymupdf.open(pdf_path)
    try:
        ocr_pages: list[int] = []
        for i in range(doc.page_count):
            page = doc[i]
            for img_info in page.get_images():
                xref = img_info[0]
                pix = pymupdf.Pixmap(doc, xref)
                area = pix.width * pix.height
                pix = None
                if area >= _OCR_IMAGE_MIN_AREA:
                    ocr_pages.append(i)
                    break
        return ocr_pages
    finally:
        doc.close()


def _enrich_markdown_with_ocr(
    md_text: str,
    languages: list[str] | None = None,
) -> tuple[str, dict]:
    """Replace image references in Markdown with OCR-extracted text.

    Returns (enriched_markdown, ocr_stats).
    """
    matches = list(_IMG_REF_RE.finditer(md_text))
    stats: dict = {
        "images_total": 0,
        "images_ocr_ok": 0,
        "images_ocr_empty": 0,
        "images_ocr_error": 0,
        "images_missing": 0,
        "images_skipped_small": 0,
    }

    if not matches:
        return md_text, stats

    _get_ocr_reader(languages)

    def _process_image(img_path: str) -> str:
        stats["images_total"] += 1
        if not os.path.isfile(img_path):
            stats["images_missing"] += 1
            return ""
        try:
            from PIL import Image
            with Image.open(img_path) as pil_img:
                w, h = pil_img.size
            if w * h < _OCR_IMAGE_MIN_AREA:
                stats["images_skipped_small"] += 1
                return ""
        except Exception:
            pass
        try:
            ocr_text = _ocr_image_file(img_path, languages)
        except Exception as exc:
            stats["images_ocr_error"] += 1
            logger.debug("OCR failed for image", extra={"image": img_path, "error_type": type(exc).__name__})
            return ""
        if not ocr_text.strip():
            stats["images_ocr_empty"] += 1
            return ""
        stats["images_ocr_ok"] += 1
        return ocr_text.strip()

    parts: list[str] = []
    last_end = 0
    for match in matches:
        parts.append(md_text[last_end:match.start()])
        replacement = _process_image(match.group(2))
        parts.append(replacement)
        last_end = match.end()
    parts.append(md_text[last_end:])

    return "".join(parts), stats


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


def _split_page_ranges(page_count: int, max_workers: int) -> list[list[int]]:
    """Split pages into roughly equal chunks for parallel processing."""
    chunk_size = math.ceil(page_count / max_workers)
    ranges: list[list[int]] = []
    for start in range(0, page_count, chunk_size):
        end = min(start + chunk_size, page_count)
        ranges.append(list(range(start, end)))
    return ranges


def convert_pdf(
    file_path: str,
    ocr_mode: str = "auto",
    ocr_languages: str = "en",
    progress_callback: Callable[[float], None] | None = None,
) -> tuple[str, dict]:
    """Convert PDF to Markdown text with optional parallel page processing.

    Args:
        file_path: Path to the PDF file.
        ocr_mode: "auto" (OCR pages with large images), "always", or "off".
        ocr_languages: Comma-separated language codes (e.g. "en,ru").
        progress_callback: optional fn(fraction) called as conversion progresses, fraction in [0..1].

    Returns:
        (markdown_text, metadata) where metadata includes conversion stats.
    """
    t0 = time.perf_counter()
    file_size = os.path.getsize(file_path)
    doc = pymupdf.open(file_path)
    page_count = doc.page_count
    doc.close()

    logger.info(
        "PDF conversion started",
        extra={
            "file": os.path.basename(file_path), "pages": page_count,
            "file_size_bytes": file_size, "ocr_mode": ocr_mode,
            "parallel": page_count > PARALLEL_THRESHOLD,
        },
    )

    if page_count > PARALLEL_THRESHOLD:
        num_workers = min(MAX_PDF_WORKERS, page_count)
        page_ranges = _split_page_ranges(page_count, num_workers)
        results: dict[int, str] = {}
        completed_count = 0

        logger.info(
            "Parallel PDF conversion",
            extra={
                "workers": num_workers,
                "chunks": len(page_ranges),
                "pages_per_chunk": [len(r) for r in page_ranges],
            },
        )

        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            future_to_idx = {
                executor.submit(_convert_page_range_with_retry, file_path, pr): idx
                for idx, pr in enumerate(page_ranges)
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                results[idx] = future.result()
                completed_count += 1
                if progress_callback is not None:
                    progress_callback(completed_count / len(page_ranges))

        md_text = "\n\n".join(results[i] for i in range(len(page_ranges)))
    else:
        for attempt in range(1, MAX_RETRIES + 2):
            try:
                md_text = pymupdf4llm.to_markdown(file_path)
                break
            except Exception as exc:
                if attempt > MAX_RETRIES:
                    raise
                logger.warning(
                    "PDF conversion failed, retrying",
                    extra={"attempt": attempt, "error": str(exc)[:200]},
                )
                time.sleep(attempt)
        if progress_callback is not None:
            progress_callback(1.0)

    convert_ms = round((time.perf_counter() - t0) * 1000, 1)

    metadata: dict = {
        "pages": page_count,
        "file_size_bytes": file_size,
        "convert_ms": convert_ms,
        "ocr_applied": False,
        "parallel_workers": min(MAX_PDF_WORKERS, page_count) if page_count > PARALLEL_THRESHOLD else 1,
    }

    should_ocr = False
    if ocr_mode == "always":
        should_ocr = True
    elif ocr_mode == "auto":
        ocr_pages = _find_ocr_pages(file_path)
        should_ocr = len(ocr_pages) > 0
        if should_ocr:
            logger.debug("OCR pages detected", extra={"ocr_pages_count": len(ocr_pages)})

    if should_ocr:
        if not _ocr_available():
            logger.warning("OCR requested but easyocr not installed, skipping OCR")
        else:
            langs = [l.strip() for l in ocr_languages.split(",") if l.strip()]
            t_ocr = time.perf_counter()
            md_text, ocr_stats = _enrich_markdown_with_ocr(md_text, languages=langs)
            ocr_ms = round((time.perf_counter() - t_ocr) * 1000, 1)
            metadata["ocr_applied"] = True
            metadata["ocr_ms"] = ocr_ms
            metadata["ocr_stats"] = ocr_stats
            logger.info(
                "OCR completed",
                extra={
                    "ocr_ms": ocr_ms,
                    "images_total": ocr_stats["images_total"],
                    "images_ocr_ok": ocr_stats["images_ocr_ok"],
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
