"""Slug generation utility for human-readable URLs.

Handles Latin, Cyrillic, and mixed-script product/manufacturer names.
"""

import re
import unicodedata

_CYRILLIC_MAP = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def slugify(text: str) -> str:
    """Convert arbitrary text to a URL-safe slug.

    >>> slugify("AxxonOne")
    'axxonone'
    >>> slugify("Hikvision DS-2CD2143G2-IU")
    'hikvision-ds-2cd2143g2-iu'
    >>> slugify("Камера Видеонаблюдения")
    'kamera-videonablyudeniya'
    >>> slugify("")
    'unnamed'
    """
    text = text.strip().lower()

    text = unicodedata.normalize("NFKD", text)

    chars = []
    for ch in text:
        if ch in _CYRILLIC_MAP:
            chars.append(_CYRILLIC_MAP[ch])
        elif ch.isascii():
            chars.append(ch)
        else:
            decomposed = unicodedata.normalize("NFD", ch)
            for d in decomposed:
                if d.isascii():
                    chars.append(d)

    result = "".join(chars)
    result = re.sub(r"[^a-z0-9]+", "-", result)
    result = result.strip("-")

    return result or "unnamed"
