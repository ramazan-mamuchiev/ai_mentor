"""Utility helpers for the products module."""

import re
import unicodedata


def make_product_slug(manufacturer: str, name: str, version: str = "") -> str:
    """Build a URL-safe slug from manufacturer, product name, and version."""
    parts = [manufacturer, name]
    if version:
        parts.append(version)
    raw = " ".join(p for p in parts if p)
    raw = unicodedata.normalize("NFKD", raw)
    raw = raw.encode("ascii", "ignore").decode("ascii")
    raw = raw.lower()
    raw = re.sub(r"[^a-z0-9]+", "-", raw)
    raw = raw.strip("-")
    return raw or "product"
