"""Shared OCR utilities (Gemini Vision API).

Provides image-to-text recognition for PDF and Confluence converters.
Supports both local file paths and in-memory image bytes.
Uses Gemini Vision API instead of local EasyOCR to avoid OOM issues.
"""

from __future__ import annotations

import base64
import io
import logging
import re
import time
from typing import Callable

logger = logging.getLogger(__name__)

OCR_IMAGE_MIN_AREA = 100_000
IMG_REF_RE = re.compile(r"!\[([^\]]*)\]\(((?:[^()]*|\([^()]*\))*)\)")

_MIME_BY_HEADER = [
    (b"\x89PNG", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF8", "image/gif"),
    (b"RIFF", "image/webp"),
    (b"BM", "image/bmp"),
]


def _guess_mime(data: bytes) -> str:
    for prefix, mime in _MIME_BY_HEADER:
        if data[:len(prefix)] == prefix:
            return mime
    return "image/png"


def ocr_available() -> bool:
    from app.config import settings
    return bool(settings.gemini_api_key)


def ocr_enabled() -> bool:
    """Check both config flag and runtime availability."""
    from app.config import settings
    return settings.ocr_enabled and ocr_available()


def detect_language_via_gemini(md_text: str) -> list[str]:
    """Detect document language(s) from extracted text using Gemini.

    Returns language codes (e.g. ["en", "ru"]).
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

        if not codes:
            codes = ["en"]

        logger.info("Language detected via Gemini", extra={
            "raw_response": raw, "languages": codes,
        })
        return codes

    except Exception as exc:
        logger.warning("Language detection failed, using fallback", extra={
            "error_type": type(exc).__name__, "error": str(exc)[:200],
        })
        return ["en"]


def _ocr_via_gemini(data: bytes, languages: list[str] | None = None) -> tuple[str, dict]:
    """Send image to Gemini Vision and return (recognized_text, usage_dict).

    usage_dict has keys: prompt_tokens, completion_tokens.
    """
    from app.config import settings
    from app.ingestion.embedder import _get_gemini_client
    from google.genai import types

    client = _get_gemini_client()
    mime = _guess_mime(data)

    lang_hint = ""
    if languages:
        lang_hint = f" The document is in {', '.join(languages)}."

    prompt = (
        "Extract ALL visible text from this image exactly as it appears."
        " Preserve the structure: headings, lists, table rows."
        " Return ONLY the extracted text, no explanations or commentary."
        f"{lang_hint}"
    )

    image_part = types.Part.from_bytes(data=data, mime_type=mime)

    t0 = time.perf_counter()
    response = client.models.generate_content(
        model=settings.ocr_vision_model,
        contents=[prompt, image_part],
    )
    duration_ms = round((time.perf_counter() - t0) * 1000, 1)

    text = response.text.strip() if response.text else ""

    usage = {"prompt_tokens": 0, "completion_tokens": 0}
    if hasattr(response, "usage_metadata") and response.usage_metadata:
        um = response.usage_metadata
        usage["prompt_tokens"] = getattr(um, "prompt_token_count", 0) or 0
        usage["completion_tokens"] = getattr(um, "candidates_token_count", 0) or 0

    logger.debug("Gemini Vision OCR done", extra={
        "mime": mime, "text_len": len(text),
        "prompt_tokens": usage["prompt_tokens"],
        "completion_tokens": usage["completion_tokens"],
        "duration_ms": duration_ms,
    })

    return text, usage


def ocr_image_file(image_path: str, languages: list[str] | None = None) -> tuple[str, dict]:
    """Run OCR on an image file via Gemini Vision.

    Returns (recognized_text, usage_dict).
    """
    with open(image_path, "rb") as f:
        data = f.read()
    return _ocr_via_gemini(data, languages)


def ocr_image_bytes(data: bytes, languages: list[str] | None = None) -> tuple[str, dict]:
    """Run OCR on in-memory image bytes via Gemini Vision.

    Returns (recognized_text, usage_dict).
    """
    return _ocr_via_gemini(data, languages)


def image_size_from_bytes(data: bytes) -> tuple[int, int]:
    """Return (width, height) of an image from bytes without full decode."""
    from PIL import Image
    with Image.open(io.BytesIO(data)) as img:
        return img.size


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
        "ocr_prompt_tokens": 0,
        "ocr_completion_tokens": 0,
    }

    if not matches:
        return md_text, stats

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

            ocr_text, usage = ocr_image_file(img_path, languages)
            stats["ocr_prompt_tokens"] += usage.get("prompt_tokens", 0)
            stats["ocr_completion_tokens"] += usage.get("completion_tokens", 0)
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
