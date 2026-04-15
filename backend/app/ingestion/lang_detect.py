"""Lightweight language detection for documents and queries."""

import logging

from lingua import Language, LanguageDetectorBuilder

logger = logging.getLogger(__name__)

_SUPPORTED = (Language.ENGLISH, Language.RUSSIAN)

_detector = (
    LanguageDetectorBuilder.from_languages(*_SUPPORTED)
    .with_minimum_relative_distance(0.25)
    .build()
)

LANG_EN = "en"
LANG_RU = "ru"
LANG_OTHER = "other"

_LINGUA_TO_CODE = {
    Language.ENGLISH: LANG_EN,
    Language.RUSSIAN: LANG_RU,
}


def detect_language(text: str, *, min_chars: int = 50) -> str:
    """Detect the dominant language of *text*.

    Returns ``'en'``, ``'ru'``, or ``'other'``.
    Samples the first 3 000 characters for speed.
    """
    if not text or len(text.strip()) < min_chars:
        return LANG_OTHER

    sample = text[:3000]
    try:
        lang = _detector.detect_language_of(sample)
    except Exception:
        logger.debug("Language detection failed, falling back to 'other'")
        return LANG_OTHER

    return _LINGUA_TO_CODE.get(lang, LANG_OTHER)
