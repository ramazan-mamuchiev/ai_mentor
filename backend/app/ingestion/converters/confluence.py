"""Confluence documentation crawler with optional OCR for images.

Crawls a Confluence page tree via REST API and converts each page to Markdown.
Supports public (anonymous) Confluence instances.
When OCR is enabled, downloads images from pages and extracts text via Gemini Vision.

Discovery strategy (in order of priority):
  1. Child pages via REST API  (parent → child hierarchy)
  2. In-body Confluence links  (hyperlinks in page HTML pointing to same space)

Usage:
    pages = await crawl_confluence(
        "https://docs.axxonsoft.com/confluence/spaces/one20en/pages/246484043/Documentation",
        max_pages=500,
    )
    # pages: list[ConfluencePage]
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

_CONNECT_TIMEOUT = 15
_READ_TIMEOUT = 30
_IMAGE_READ_TIMEOUT = 15
_MAX_CRAWL_SECONDS = 600
_PAGE_LIMIT = 100

_HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Lexiro/1.0",
    "Accept": "application/json",
}

_CONFLUENCE_URL_PATTERN = re.compile(
    r"(?P<base>https?://[^/]+(?:/[^/]+)*?)/spaces/(?P<space>[^/]+)/pages/(?P<page_id>\d+)"
)

_BODY_LINK_RE = re.compile(
    r'/spaces/(?P<space>[^/]+)/pages/(?P<page_id>\d+)'
)


@dataclass
class ConfluencePage:
    page_id: str
    title: str
    markdown: str
    url: str
    space_key: str
    depth: int = 0
    children_count: int = 0
    ocr_images_total: int = 0
    ocr_images_success: int = 0
    ocr_images_empty: int = 0
    ocr_images_failed: int = 0
    ocr_prompt_tokens: int = 0
    ocr_completion_tokens: int = 0
    ocr_ms: float = 0.0
    ocr_error: str = ""


@dataclass
class CrawlResult:
    pages: list[ConfluencePage] = field(default_factory=list)
    root_title: str = ""
    space_key: str = ""
    base_url: str = ""
    total_pages: int = 0
    crawl_ms: float = 0.0
    errors: list[str] = field(default_factory=list)
    ocr_images_total: int = 0
    ocr_images_success: int = 0
    ocr_prompt_tokens: int = 0
    ocr_completion_tokens: int = 0
    ocr_ms: float = 0.0


def _make_http_client(image: bool = False) -> httpx.Client:
    timeout = httpx.Timeout(
        connect=_CONNECT_TIMEOUT,
        read=_IMAGE_READ_TIMEOUT if image else _READ_TIMEOUT,
        write=10.0,
        pool=10.0,
    )
    return httpx.Client(
        timeout=timeout,
        headers=_HTTP_HEADERS,
        verify=False,
        follow_redirects=True,
    )


def _api_get(url: str, client: httpx.Client | None = None) -> dict:
    """Fetch JSON from Confluence REST API."""
    own_client = client is None
    if own_client:
        client = _make_http_client()
    try:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.json()
    finally:
        if own_client:
            client.close()


def parse_confluence_url(url: str) -> tuple[str, str, str]:
    """Extract (base_url, space_key, page_id) from a Confluence page URL.

    Raises ValueError if the URL doesn't match the expected pattern.
    """
    m = _CONFLUENCE_URL_PATTERN.search(url)
    if not m:
        raise ValueError(
            f"Not a valid Confluence page URL: {url}. "
            f"Expected format: https://host/confluence/spaces/SPACE/pages/12345/Title"
        )
    return m.group("base"), m.group("space"), m.group("page_id")


def _get_page_content(
    base_url: str, page_id: str, client: httpx.Client | None = None,
) -> tuple[str, str]:
    """Fetch page title and HTML body via REST API. Returns (title, html_body)."""
    url = f"{base_url}/rest/api/content/{page_id}?expand=body.storage,title"
    data = _api_get(url, client)
    title = data.get("title", "")
    html_body = data.get("body", {}).get("storage", {}).get("value", "")
    return title, html_body


def _get_child_pages(
    base_url: str, page_id: str, client: httpx.Client | None = None,
) -> list[dict]:
    """Fetch all child pages (handles pagination)."""
    children: list[dict] = []
    start = 0
    while True:
        url = f"{base_url}/rest/api/content/{page_id}/child/page?limit={_PAGE_LIMIT}&start={start}"
        data = _api_get(url, client)
        results = data.get("results", [])
        children.extend(results)
        if len(results) < _PAGE_LIMIT:
            break
        start += _PAGE_LIMIT
    return children


def _extract_linked_page_ids(html_body: str, space_key: str) -> list[str]:
    """Extract Confluence page IDs from hyperlinks in the HTML body.

    Only returns pages that belong to the same space.
    """
    page_ids: list[str] = []
    for m in _BODY_LINK_RE.finditer(html_body):
        if m.group("space") == space_key:
            pid = m.group("page_id")
            if pid not in page_ids:
                page_ids.append(pid)
    return page_ids


_AC_IMAGE_RE = re.compile(
    r"<ac:image[^>]*>.*?<ri:attachment\s+ri:filename=\"([^\"]+)\"\s*/?>.*?</ac:image>",
    re.DOTALL,
)


def _resolve_confluence_images(html: str, base_url: str, page_id: str) -> str:
    """Replace Confluence <ac:image><ri:attachment/></ac:image> with standard <img> tags."""
    def _replace(m: re.Match) -> str:
        filename = m.group(1)
        img_url = f"{base_url}/download/attachments/{page_id}/{quote(filename, safe='')}"
        return f'<img src="{img_url}" alt="{filename}" />'
    return _AC_IMAGE_RE.sub(_replace, html)


def _html_to_markdown(html: str, page_title: str, base_url: str = "", page_id: str = "") -> str:
    """Convert Confluence storage format HTML to clean Markdown."""
    from markdownify import markdownify as md

    if not html or not html.strip():
        return ""

    if base_url and page_id:
        html = _resolve_confluence_images(html, base_url, page_id)

    text = md(
        html,
        heading_style="ATX",
        bullets="-",
        strip=["script", "style", "nav", "footer", "header"],
    )

    lines = text.split("\n")
    cleaned = []
    blank_count = 0
    for line in lines:
        stripped = line.rstrip()
        if not stripped:
            blank_count += 1
            if blank_count <= 2:
                cleaned.append("")
        else:
            blank_count = 0
            cleaned.append(stripped)

    result = "\n".join(cleaned).strip()

    if result and not result.startswith("#"):
        result = f"# {page_title}\n\n{result}"

    return result


def _fetch_image_bytes(url: str) -> bytes | None:
    """Download image bytes from a URL. Returns None on failure."""
    try:
        with _make_http_client(image=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.content
    except Exception as exc:
        logger.debug("Failed to download image", extra={
            "url": url[:200], "error": str(exc)[:200],
        })
        return None


def _enrich_confluence_markdown_with_ocr(
    md_text: str,
    languages: list[str] | None = None,
) -> tuple[str, dict]:
    """Download images referenced in Markdown and replace with OCR text.

    Handles both absolute URLs and relative Confluence attachment paths.
    Returns (enriched_markdown, ocr_stats).
    """
    from app.ingestion.converters.ocr import (
        IMG_REF_RE,
        OCR_IMAGE_MIN_AREA,
        image_size_from_bytes,
        ocr_image_bytes,
    )

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

    def _process_image_url(img_url: str) -> str:
        if not img_url or not img_url.startswith(("http://", "https://")):
            return ""

        stats["ocr_images_total"] += 1
        try:
            data = _fetch_image_bytes(img_url)
            if data is None:
                stats["ocr_images_failed"] += 1
                return ""

            try:
                w, h = image_size_from_bytes(data)
                if w * h < OCR_IMAGE_MIN_AREA:
                    stats["ocr_images_empty"] += 1
                    return ""
            except Exception:
                pass

            ocr_text, usage = ocr_image_bytes(data, languages)
            stats["ocr_prompt_tokens"] += usage.get("prompt_tokens", 0)
            stats["ocr_completion_tokens"] += usage.get("completion_tokens", 0)
            if not ocr_text.strip():
                stats["ocr_images_empty"] += 1
                return ""

            stats["ocr_images_success"] += 1
            return ocr_text.strip()

        except Exception as exc:
            stats["ocr_images_failed"] += 1
            logger.warning("OCR failed for Confluence image", extra={
                "url": img_url[:200],
                "error_type": type(exc).__name__,
                "error": str(exc)[:200],
            })
            return ""

    parts: list[str] = []
    last_end = 0
    for match in matches:
        parts.append(md_text[last_end:match.start()])
        replacement = _process_image_url(match.group(2))
        parts.append(replacement)
        last_end = match.end()
    parts.append(md_text[last_end:])

    return "".join(parts), stats


async def crawl_confluence(
    url: str,
    max_pages: int = 500,
    max_depth: int = 20,
    progress_callback: callable | None = None,
    max_seconds: int = _MAX_CRAWL_SECONDS,
    page_callback: callable | None = None,
) -> CrawlResult:
    """Crawl a Confluence page tree starting from the given URL.

    Pages are discovered via two mechanisms:
      - REST API child-page hierarchy (parent → child)
      - In-body hyperlinks pointing to pages in the same Confluence space

    Args:
        url: Confluence page URL.
        max_pages: Maximum number of pages to crawl.
        max_depth: Maximum tree depth to traverse.
        progress_callback: Optional callback(pages_done, total_estimated).
        max_seconds: Hard wall-clock limit for the entire crawl.
        page_callback: Optional callback(page: ConfluencePage) invoked for
            each page immediately after it is crawled, before the next page
            starts.  This allows the caller to persist / enqueue the page
            without waiting for the full crawl to finish.

    Returns:
        CrawlResult with all crawled pages.
    """
    from app.ingestion.converters.ocr import (
        detect_language_via_gemini,
        ocr_enabled as _ocr_enabled,
    )

    t0 = time.perf_counter()
    deadline = t0 + max_seconds
    base_url, space_key, root_page_id = parse_confluence_url(url)
    do_ocr = _ocr_enabled()

    logger.info("Confluence crawl started", extra={
        "url": url, "base_url": base_url,
        "space_key": space_key, "root_page_id": root_page_id,
        "max_pages": max_pages, "ocr_enabled": do_ocr,
        "max_seconds": max_seconds,
    })

    result = CrawlResult(base_url=base_url, space_key=space_key)

    queue: list[tuple[str, int]] = [(root_page_id, 0)]
    visited: set[str] = set()
    pages_done = 0
    ocr_languages: list[str] | None = None

    client = _make_http_client()
    try:
        while queue and pages_done < max_pages:
            if time.perf_counter() >= deadline:
                logger.warning("Confluence crawl hit time limit", extra={
                    "max_seconds": max_seconds, "pages_done": pages_done,
                })
                result.errors.append(
                    f"Crawl stopped: wall-clock limit of {max_seconds}s reached "
                    f"after {pages_done} pages"
                )
                break

            page_id, depth = queue.pop(0)

            if page_id in visited:
                continue
            visited.add(page_id)

            if depth > max_depth:
                continue

            try:
                title, html_body = await asyncio.to_thread(
                    _get_page_content, base_url, page_id, client,
                )
            except Exception as exc:
                error_msg = f"Failed to fetch page {page_id}: {type(exc).__name__}: {exc}"
                logger.warning(error_msg)
                result.errors.append(error_msg)
                continue

            markdown = _html_to_markdown(html_body, title, base_url=base_url, page_id=page_id)

            page_ocr_stats: dict = {}
            page_ocr_ms = 0.0

            if do_ocr and markdown:
                if ocr_languages is None:
                    ocr_languages = detect_language_via_gemini(markdown)
                t_ocr = time.perf_counter()
                try:
                    markdown, page_ocr_stats = await asyncio.to_thread(
                        _enrich_confluence_markdown_with_ocr, markdown, ocr_languages,
                    )
                except Exception as exc:
                    ocr_error_msg = f"{type(exc).__name__}: {exc}"
                    logger.warning("OCR enrichment failed for page", extra={
                        "page_id": page_id, "title": title,
                        "error": ocr_error_msg[:200],
                    })
                    page_ocr_stats = {"ocr_error": ocr_error_msg[:500]}
                page_ocr_ms = round((time.perf_counter() - t_ocr) * 1000, 1)

            page_url = f"{base_url}/spaces/{space_key}/pages/{page_id}/{quote(title, safe='')}"

            children: list[dict] = []
            try:
                children = await asyncio.to_thread(
                    _get_child_pages, base_url, page_id, client,
                )
            except Exception as exc:
                error_msg = f"Failed to fetch children of page {page_id}: {type(exc).__name__}: {exc}"
                logger.warning(error_msg)
                result.errors.append(error_msg)

            linked_ids = _extract_linked_page_ids(html_body, space_key)

            page = ConfluencePage(
                page_id=page_id,
                title=title,
                markdown=markdown,
                url=page_url,
                space_key=space_key,
                depth=depth,
                children_count=len(children),
                ocr_images_total=page_ocr_stats.get("ocr_images_total", 0),
                ocr_images_success=page_ocr_stats.get("ocr_images_success", 0),
                ocr_images_empty=page_ocr_stats.get("ocr_images_empty", 0),
                ocr_images_failed=page_ocr_stats.get("ocr_images_failed", 0),
                ocr_prompt_tokens=page_ocr_stats.get("ocr_prompt_tokens", 0),
                ocr_completion_tokens=page_ocr_stats.get("ocr_completion_tokens", 0),
                ocr_ms=page_ocr_ms,
                ocr_error=page_ocr_stats.get("ocr_error", ""),
            )
            result.pages.append(page)
            pages_done += 1

            result.ocr_images_total += page.ocr_images_total
            result.ocr_images_success += page.ocr_images_success
            result.ocr_prompt_tokens += page.ocr_prompt_tokens
            result.ocr_completion_tokens += page.ocr_completion_tokens
            result.ocr_ms += page_ocr_ms

            if pages_done == 1:
                result.root_title = title

            for child in children:
                child_id = child.get("id", "")
                if child_id and child_id not in visited:
                    queue.append((child_id, depth + 1))

            for linked_id in linked_ids:
                if linked_id not in visited:
                    queue.append((linked_id, depth + 1))

            if page_callback:
                try:
                    await asyncio.to_thread(page_callback, page)
                except Exception as cb_exc:
                    logger.warning("page_callback failed", extra={
                        "page_id": page_id, "error": str(cb_exc)[:200],
                    })

            if progress_callback:
                estimated_total = pages_done + len(queue)
                try:
                    progress_callback(pages_done, estimated_total)
                except Exception:
                    pass

            logger.info("Page crawled", extra={
                "page_id": page_id, "title": title,
                "depth": depth, "children": len(children),
                "linked_pages": len(linked_ids),
                "md_length": len(markdown),
                "ocr_images": page_ocr_stats.get("ocr_images_success", 0),
                "ocr_ms": page_ocr_ms,
            })
    finally:
        client.close()

    result.total_pages = pages_done
    result.crawl_ms = round((time.perf_counter() - t0) * 1000, 1)

    logger.info("Confluence crawl completed", extra={
        "url": url, "total_pages": pages_done,
        "crawl_ms": result.crawl_ms,
        "errors": len(result.errors),
        "ocr_images_total": result.ocr_images_total,
        "ocr_images_success": result.ocr_images_success,
        "ocr_ms": result.ocr_ms,
    })

    return result
