"""PDF -> Markdown converter with optional OCR (EasyOCR).

Two-pass pipeline:
  Pass 1: pymupdf4llm.to_markdown() -- text layer extraction (parallel, chunked)
  Pass 2: _enrich_markdown_with_ocr() -- OCR images via EasyOCR with auto-detected language

Language detection uses Gemini (same API key as embeddings) between passes.
"""

import logging
import math
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

import pymupdf
import pymupdf4llm

logger = logging.getLogger(__name__)

PARALLEL_THRESHOLD = 10
MAX_PDF_WORKERS = 4
MAX_RETRIES = 2
PAGES_PER_CHUNK = 50

_OCR_IMAGE_MIN_AREA = 100_000
_IMG_REF_RE = re.compile(r"!\[([^\]]*)\]\(((?:[^()]*|\([^()]*\))*)\)")

_ocr_reader = None
_ocr_reader_langs: list[str] = []

_LANG_MAP = {
    "zh": "ch_sim", "chinese": "ch_sim", "zh-cn": "ch_sim", "zh-hans": "ch_sim",
    "zh-tw": "ch_tra", "zh-hant": "ch_tra",
    "en": "en", "ru": "ru", "de": "de", "fr": "fr", "es": "es",
    "pt": "pt", "it": "it", "ar": "ar", "hi": "hi", "th": "th",
    "vi": "vi", "ja": "ja", "ko": "ko", "nl": "nl", "pl": "pl",
    "tr": "tr", "uk": "uk", "cs": "cs", "sv": "sv", "id": "id",
}


def _detect_language_via_gemini(md_text: str) -> list[str]:
    """Detect document language(s) from extracted text using Gemini.

    Returns EasyOCR-compatible language codes (e.g. ["en", "ru"]).
    Falls back to ["en"] on any error.
    """
    from app.config import settings

    if not settings.gemini_api_key:
        logger.warning("No Gemini API key, falling back to default OCR language")
        return ["en"]

    sample = md_text[:3000].strip()
    if not sample:
        return ["en"]

    try:
        from app.ingestion.embedder import _get_gemini_client
        client = _get_gemini_client()

        prompt = (
            "Determine the language(s) of this text. "
            "Return ONLY ISO 639-1 language codes separated by commas, nothing else. "
            "Examples: en  |  ru  |  en,ru  |  zh  |  de,en\n\n"
            f"Text:\n{sample}"
        )

        response = client.models.generate_content(
            model=settings.ocr_lang_detect_model,
            contents=prompt,
        )
        raw = response.text.strip().lower().replace(" ", "")
        codes = [c.strip() for c in raw.split(",") if c.strip()]

        easyocr_langs = []
        for code in codes:
            mapped = _LANG_MAP.get(code, code)
            if mapped not in easyocr_langs:
                easyocr_langs.append(mapped)

        if not easyocr_langs:
            easyocr_langs = ["en"]

        logger.info("Language detected via Gemini", extra={
            "raw_response": raw, "easyocr_langs": easyocr_langs,
        })
        return easyocr_langs

    except Exception as exc:
        logger.warning("Language detection failed, using fallback", extra={
            "error_type": type(exc).__name__, "error": str(exc)[:200],
        })
        return ["en"]


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
    progress_callback: Callable[[float], None] | None = None,
) -> tuple[str, dict]:
    """Replace image references in Markdown with OCR-extracted text.

    Each image is processed in a try/except so a single failure never
    breaks the whole pipeline. Returns (enriched_markdown, ocr_stats).
    """
    matches = list(_IMG_REF_RE.finditer(md_text))
    stats: dict = {
        "ocr_images_total": 0,
        "ocr_images_success": 0,
        "ocr_images_empty": 0,
        "ocr_images_failed": 0,
    }

    if not matches:
        return md_text, stats

    _get_ocr_reader(languages)
    total_images = len(matches)
    processed = 0

    def _process_image(img_path: str) -> str:
        nonlocal processed
        stats["ocr_images_total"] += 1
        result = ""
        try:
            if not os.path.isfile(img_path):
                stats["ocr_images_failed"] += 1
                logger.debug("OCR image file missing", extra={"image": img_path})
                return ""
            try:
                from PIL import Image
                with Image.open(img_path) as pil_img:
                    w, h = pil_img.size
                if w * h < _OCR_IMAGE_MIN_AREA:
                    stats["ocr_images_empty"] += 1
                    return ""
            except Exception:
                pass

            ocr_text = _ocr_image_file(img_path, languages)
            if not ocr_text.strip():
                stats["ocr_images_empty"] += 1
                return ""
            stats["ocr_images_success"] += 1
            result = ocr_text.strip()
        except Exception as exc:
            stats["ocr_images_failed"] += 1
            logger.warning("OCR failed for image, continuing", extra={
                "image": img_path, "error_type": type(exc).__name__,
                "error": str(exc)[:200],
            })
        finally:
            processed += 1
            if progress_callback is not None:
                progress_callback(processed / total_images)
        return result

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


def _split_page_ranges(page_count: int, pages_per_chunk: int = PAGES_PER_CHUNK) -> list[list[int]]:
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

    ocr_pages = _find_ocr_pages(file_path)
    has_ocr_images = len(ocr_pages) > 0
    will_ocr = has_ocr_images and _ocr_available()

    if progress_callback is not None:
        if will_ocr:
            _convert_cb = lambda frac: progress_callback(frac * 0.625, "converting")
            _ocr_cb = lambda frac: progress_callback(0.625 + frac * 0.375, "ocr")
        else:
            _convert_cb = lambda frac: progress_callback(frac, "converting")
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

    if page_count > PARALLEL_THRESHOLD:
        num_workers = min(MAX_PDF_WORKERS, page_count)
        page_ranges = _split_page_ranges(page_count)
        results: dict[int, str] = {}
        completed_count = 0

        logger.info(
            "Parallel PDF conversion",
            extra={
                "workers": num_workers,
                "total_chunks": len(page_ranges),
                "pages_per_chunk": PAGES_PER_CHUNK,
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
                    _convert_cb(completed_count / len(page_ranges))

        md_text = "\n\n".join(results[i] for i in range(len(page_ranges)))
    else:
        page_ranges = _split_page_ranges(page_count, pages_per_chunk=1)
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
                _convert_cb((idx + 1) / len(page_ranges))

        md_text = "\n\n".join(page_results[i] for i in range(len(page_ranges)))

    convert_ms = round((time.perf_counter() - t0) * 1000, 1)

    metadata: dict = {
        "pages": page_count,
        "file_size_bytes": file_size,
        "convert_ms": convert_ms,
        "ocr_applied": False,
        "parallel_workers": min(MAX_PDF_WORKERS, page_count) if page_count > PARALLEL_THRESHOLD else 1,
    }

    if will_ocr:
        detected_langs = _detect_language_via_gemini(md_text)
        metadata["detected_languages"] = detected_langs
        metadata["detected_languages_str"] = ",".join(detected_langs)

        t_ocr = time.perf_counter()
        md_text, ocr_stats = _enrich_markdown_with_ocr(
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
