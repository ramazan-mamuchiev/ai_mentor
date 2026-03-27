"""Shared OCR utilities (EasyOCR).

Provides image-to-text recognition for PDF and Confluence converters.
Supports both local file paths and in-memory image bytes.
"""

from __future__ import annotations

import io
import logging
import re
import time
from typing import Callable

logger = logging.getLogger(__name__)

OCR_IMAGE_MIN_AREA = 100_000
IMG_REF_RE = re.compile(r"!\[([^\]]*)\]\(((?:[^()]*|\([^()]*\))*)\)")

_ocr_reader = None
_ocr_reader_langs: list[str] = []

LANG_MAP = {
    "zh": "ch_sim", "chinese": "ch_sim", "zh-cn": "ch_sim", "zh-hans": "ch_sim",
    "zh-tw": "ch_tra", "zh-hant": "ch_tra",
    "en": "en", "ru": "ru", "de": "de", "fr": "fr", "es": "es",
    "pt": "pt", "it": "it", "ar": "ar", "hi": "hi", "th": "th",
    "vi": "vi", "ja": "ja", "ko": "ko", "nl": "nl", "pl": "pl",
    "tr": "tr", "uk": "uk", "cs": "cs", "sv": "sv", "id": "id",
}


def ocr_available() -> bool:
    try:
        import easyocr  # noqa: F401
        return True
    except ImportError:
        return False


def ocr_enabled() -> bool:
    """Check both config flag and runtime availability."""
    from app.config import settings
    return settings.ocr_enabled and ocr_available()


def detect_language_via_llm(md_text: str) -> list[str]:
    """Detect document language(s) from extracted text using the configured LLM provider.

    Returns EasyOCR-compatible language codes (e.g. ["en", "ru"]).
    Falls back to ["en"] on any error.
    """
    from app.config import settings
    from app.llm.credentials import llm_credentials

    api_key, _ = llm_credentials()
    if not api_key:
        logger.warning("No LLM API key, falling back to default OCR language")
        return ["en"]

    sample = md_text[:3000].strip()
    if not sample:
        return ["en"]

    prompt = (
        "Determine the language(s) of this text. "
        "Return ONLY ISO 639-1 language codes separated by commas, nothing else. "
        "Examples: en  |  ru  |  en,ru  |  zh  |  de,en\n\n"
        f"Text:\n{sample}"
    )

    try:
        if settings.llm_provider == "gemini":
            from app.ingestion.embedder import _get_gemini_client
            client = _get_gemini_client()
            response = client.models.generate_content(
                model=settings.ocr_lang_detect_model,
                contents=prompt,
            )
            raw = response.text.strip().lower().replace(" ", "")
        else:
            import httpx
            api_key, base_url = llm_credentials()
            url = f"{base_url.rstrip('/')}/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            }
            payload = {
                "model": settings.ocr_lang_detect_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "max_tokens": 30,
            }
            with httpx.Client(timeout=httpx.Timeout(15.0, connect=5.0)) as http_client:
                resp = http_client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            raw = data["choices"][0]["message"]["content"].strip().lower().replace(" ", "")

        codes = [c.strip() for c in raw.split(",") if c.strip()]

        easyocr_langs = []
        for code in codes:
            mapped = LANG_MAP.get(code, code)
            if mapped not in easyocr_langs:
                easyocr_langs.append(mapped)

        if not easyocr_langs:
            easyocr_langs = ["en"]

        logger.info("Language detected via LLM", extra={
            "raw_response": raw, "easyocr_langs": easyocr_langs,
            "provider": settings.llm_provider,
        })
        return easyocr_langs

    except Exception as exc:
        logger.warning("Language detection failed, using fallback", extra={
            "error_type": type(exc).__name__, "error": str(exc)[:200],
        })
        return ["en"]


def get_ocr_reader(languages: list[str] | None = None):
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


def ocr_image_file(image_path: str, languages: list[str] | None = None) -> str:
    """Run OCR on an image file, return recognized text."""
    import numpy as np
    from PIL import Image

    img = np.array(Image.open(image_path))
    return _ocr_numpy_array(img, languages)


def ocr_image_bytes(data: bytes, languages: list[str] | None = None) -> str:
    """Run OCR on in-memory image bytes, return recognized text."""
    import numpy as np
    from PIL import Image

    img = np.array(Image.open(io.BytesIO(data)))
    return _ocr_numpy_array(img, languages)


def image_size_from_bytes(data: bytes) -> tuple[int, int]:
    """Return (width, height) of an image from bytes without full decode."""
    from PIL import Image
    with Image.open(io.BytesIO(data)) as img:
        return img.size


def _ocr_numpy_array(img, languages: list[str] | None = None) -> str:
    reader = get_ocr_reader(languages)

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


def enrich_markdown_with_ocr_files(
    md_text: str,
    languages: list[str] | None = None,
    progress_callback: Callable[[float], None] | None = None,
) -> tuple[str, dict]:
    """Replace local image references in Markdown with OCR-extracted text.

    Used by the PDF converter where images are local files on disk.
    Returns (enriched_markdown, ocr_stats).
    """
    import os

    matches = list(IMG_REF_RE.finditer(md_text))
    stats: dict = {
        "ocr_images_total": 0,
        "ocr_images_success": 0,
        "ocr_images_empty": 0,
        "ocr_images_failed": 0,
    }

    if not matches:
        return md_text, stats

    get_ocr_reader(languages)
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
                if w * h < OCR_IMAGE_MIN_AREA:
                    stats["ocr_images_empty"] += 1
                    return ""
            except Exception:
                pass

            ocr_text = ocr_image_file(img_path, languages)
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
