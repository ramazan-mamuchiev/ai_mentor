"""URL -> Markdown converter.

Auto-detects content type:
- Direct Swagger/OpenAPI spec (JSON/YAML) -> structured Markdown
- Swagger UI / ReDoc page -> extracts spec URL, then parses
- Generic web page -> headless browser via httpx + optional Crawl4AI

Crawl4AI is optional: if not installed, falls back to httpx for simple pages.
"""

import asyncio
import json
import logging
import re
import ssl
import time
import urllib.request
from urllib.parse import urlparse

import yaml

from app.ingestion.converters.swagger import _openapi_to_markdown, _parse_openapi_text

logger = logging.getLogger(__name__)

_FETCH_TIMEOUT = 30
_MAX_RESPONSE_BYTES = 50 * 1024 * 1024

_SWAGGER_NAMES = {"swagger", "openapi", "paths", "info"}

_SWAGGER_UI_PATTERNS = re.compile(
    r"swagger-ui|SwaggerUIBundle|redoc\.standalone|spec-url|swagger-config",
    re.IGNORECASE,
)

_SPEC_URL_EXTRACTORS = [
    re.compile(r"""url\s*[:=]\s*['"]([^'"]+\.(?:json|yaml|yml))['"]"""),
    re.compile(r"""spec-url\s*=\s*['"]([^'"]+)['"]"""),
    re.compile(r"""configUrl\s*[:=]\s*['"]([^'"]+)['"]"""),
]

_COMMON_SPEC_PATHS = [
    "/swagger.json", "/openapi.json", "/api-docs",
    "/v2/api-docs", "/v3/api-docs",
    "/swagger/v1/swagger.json", "/swagger.yaml",
]


def _make_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _fetch_url(url: str, accept: str = "*/*") -> tuple[bytes, str, str]:
    """Fetch URL content. Returns (body_bytes, content_type, final_url)."""
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) IPCodex/1.0",
        "Accept": accept,
    })
    ctx = _make_ssl_context()
    with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT, context=ctx) as resp:
        ct = resp.headers.get("Content-Type", "")
        final_url = resp.url
        body = resp.read(_MAX_RESPONSE_BYTES)
    return body, ct, final_url


def _try_parse_as_openapi(raw: bytes, content_type: str) -> dict | None:
    text = raw.decode("utf-8", errors="replace")
    return _parse_openapi_text(text, content_type)


def _detect_swagger_spec_url(html: str, page_url: str) -> str | None:
    if not _SWAGGER_UI_PATTERNS.search(html):
        return None
    for pattern in _SPEC_URL_EXTRACTORS:
        m = pattern.search(html)
        if m:
            spec_url = m.group(1)
            if spec_url.startswith("/"):
                parsed = urlparse(page_url)
                spec_url = f"{parsed.scheme}://{parsed.netloc}{spec_url}"
            elif not spec_url.startswith("http"):
                base = page_url.rsplit("/", 1)[0]
                spec_url = f"{base}/{spec_url}"
            return spec_url

    parsed = urlparse(page_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    for path in _COMMON_SPEC_PATHS:
        probe_url = base + path
        try:
            body, ct, _ = _fetch_url(probe_url, accept="application/json, application/yaml")
            if _try_parse_as_openapi(body, ct) is not None:
                return probe_url
        except Exception:
            continue
    return None


def _crawl4ai_available() -> bool:
    try:
        import crawl4ai  # noqa: F401
        return True
    except ImportError:
        return False


async def _crawl_url(url: str, wait_for: str | None = None, delay: float = 0) -> tuple[str, str]:
    """Crawl a single URL with headless browser. Returns (markdown, page_title)."""
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
    from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
    from crawl4ai.content_filter_strategy import PruningContentFilter

    md_gen = DefaultMarkdownGenerator(
        content_filter=PruningContentFilter(threshold=0.4, threshold_type="fixed")
    )

    run_cfg_kwargs: dict = {
        "cache_mode": CacheMode.BYPASS,
        "markdown_generator": md_gen,
    }
    if wait_for:
        run_cfg_kwargs["wait_for"] = wait_for
    if delay:
        run_cfg_kwargs["delay_before_return_html"] = delay

    browser_cfg = BrowserConfig(headless=True)
    run_cfg = CrawlerRunConfig(**run_cfg_kwargs)

    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        result = await crawler.arun(url=url, config=run_cfg)
        if not result.success:
            raise RuntimeError(result.error_message or "Crawl failed")
        md = result.markdown
        if hasattr(md, "fit_markdown") and md.fit_markdown:
            md_text = md.fit_markdown
        elif hasattr(md, "raw_markdown"):
            md_text = md.raw_markdown
        else:
            md_text = str(md)
        title = ""
        if result.metadata and isinstance(result.metadata, dict):
            title = result.metadata.get("title", "")
        return md_text, title


async def convert_url(url: str) -> tuple[str, dict]:
    """Convert a URL to Markdown text.

    Auto-detects: direct OpenAPI spec, Swagger UI page, or generic web page.

    Returns (markdown_text, metadata).
    """
    t0 = time.perf_counter()
    url = url.strip()

    logger.info("URL conversion started", extra={"url": url})

    detection_method = "unknown"
    spec: dict | None = None
    md_text: str = ""
    page_title: str = ""

    raw_body, content_type, final_url = await asyncio.to_thread(
        _fetch_url, url, "application/json, application/yaml, text/html, */*"
    )
    fetch_ms = round((time.perf_counter() - t0) * 1000, 1)
    logger.debug("URL fetched", extra={"url": url, "fetch_ms": fetch_ms, "content_type": content_type})

    spec = _try_parse_as_openapi(raw_body, content_type)
    if spec:
        detection_method = "direct_openapi_spec"
        logger.info("Detected direct OpenAPI spec", extra={"url": url})
    else:
        body_text = raw_body.decode("utf-8", errors="replace")
        is_html = (
            "html" in content_type.lower()
            or body_text.lstrip().startswith("<!")
            or "<html" in body_text[:500].lower()
        )
        if is_html:
            spec_url = await asyncio.to_thread(_detect_swagger_spec_url, body_text, final_url)
            if spec_url:
                logger.info("Swagger UI detected, fetching spec", extra={"spec_url": spec_url})
                try:
                    spec_body, spec_ct, _ = await asyncio.to_thread(
                        _fetch_url, spec_url, "application/json, application/yaml"
                    )
                    spec = _try_parse_as_openapi(spec_body, spec_ct)
                    if spec:
                        detection_method = "swagger_ui_extracted"
                except Exception as exc:
                    logger.warning("Failed to fetch extracted spec URL", extra={
                        "spec_url": spec_url, "error_type": type(exc).__name__,
                    })

    if spec:
        md_text = _openapi_to_markdown(spec)
        info = spec.get("info", {})
        page_title = info.get("title", "")
    else:
        detection_method = "crawl4ai_fallback"
        if _crawl4ai_available():
            logger.info("Falling back to Crawl4AI", extra={"url": url})
            md_text, page_title = await _crawl_url(url, None, 2.0)
        else:
            body_text = raw_body.decode("utf-8", errors="replace")
            md_text = body_text
            detection_method = "raw_html_fallback"
            logger.warning("Crawl4AI not available, using raw HTML", extra={"url": url})

    total_ms = round((time.perf_counter() - t0) * 1000, 1)

    if not md_text or not md_text.strip():
        logger.warning("URL conversion produced empty content", extra={"url": url, "detection": detection_method})
        raise ValueError(f"Conversion of {url} produced empty content")

    metadata: dict = {
        "url": url,
        "detection_method": detection_method,
        "page_title": page_title,
        "total_ms": total_ms,
        "fetch_ms": fetch_ms,
        "md_length": len(md_text),
    }

    if spec:
        info = spec.get("info", {})
        metadata["api_title"] = info.get("title", "")
        metadata["api_version"] = info.get("version", "")
        metadata["endpoints"] = sum(
            len([m for m in ("get", "post", "put", "patch", "delete", "options", "head") if m in ops])
            for ops in spec.get("paths", {}).values()
            if isinstance(ops, dict)
        )
        metadata["models"] = len(
            spec.get("definitions") or spec.get("components", {}).get("schemas", {}) or {}
        )

    logger.info(
        "URL conversion completed",
        extra={
            "url": url, "detection": detection_method,
            "total_ms": total_ms, "md_length": len(md_text),
        },
    )

    return md_text, metadata
