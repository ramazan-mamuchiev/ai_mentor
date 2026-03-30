"""Utility helpers for the products module."""

import re
import unicodedata


def make_product_slug(manufacturer: str, name: str) -> str:
    """Build a URL-safe slug from manufacturer and product name.

    Examples:
        ("ONVIF", "ONVIF Profiles") -> "onvif-onvif-profiles"
        ("Hikvision", "HikCentral")  -> "hikvision-hikcentral"
        ("", "My Product 2.0")       -> "my-product-2-0"
    """
    raw = f"{manufacturer} {name}" if manufacturer else name
    raw = unicodedata.normalize("NFKD", raw)
    raw = raw.encode("ascii", "ignore").decode("ascii")
    raw = raw.lower()
    raw = re.sub(r"[^a-z0-9]+", "-", raw)
    raw = raw.strip("-")
    return raw or "product"
