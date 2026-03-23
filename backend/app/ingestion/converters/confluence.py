"""Confluence documentation crawler.

Crawls a Confluence page tree via REST API and converts each page to Markdown.
Supports public (anonymous) Confluence instances.

Usage:
    pages = await crawl_confluence(
        "https://docs.axxonsoft.com/confluence/spaces/one20en/pages/246484043/Documentation",
        max_pages=500,
    )
    # pages: list[ConfluencePage]
"""

import asyncio
import logging
import re
import ssl
import time
import urllib.request
import json
from dataclasses import dataclass, field
from urllib.parse import urlparse, quote

logger = logging.getLogger(__name__)

_FETCH_TIMEOUT = 30
_MAX_RESPONSE_BYTES = 20 * 1024 * 1024
_PAGE_LIMIT = 100

_CONFLUENCE_URL_PATTERN = re.compile(
    r"(?P<base>https?://[^/]+(?:/[^/]+)*?)/spaces/(?P<space>[^/]+)/pages/(?P<page_id>\d+)"
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


@dataclass
class CrawlResult:
    pages: list[ConfluencePage] = field(default_factory=list)
    root_title: str = ""
    space_key: str = ""
    base_url: str = ""
    total_pages: int = 0
    crawl_ms: float = 0.0
    errors: list[str] = field(default_factory=list)


def _make_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _api_get(url: str) -> dict:
    """Fetch JSON from Confluence REST API."""
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) IPCodex/1.0",
        "Accept": "application/json",
    })
    ctx = _make_ssl_context()
    with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT, context=ctx) as resp:
        body = resp.read(_MAX_RESPONSE_BYTES)
    return json.loads(body.decode("utf-8"))


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


def _get_page_content(base_url: str, page_id: str) -> tuple[str, str]:
    """Fetch page title and HTML body via REST API. Returns (title, html_body)."""
    url = f"{base_url}/rest/api/content/{page_id}?expand=body.storage,title"
    data = _api_get(url)
    title = data.get("title", "")
    html_body = data.get("body", {}).get("storage", {}).get("value", "")
    return title, html_body


def _get_child_pages(base_url: str, page_id: str) -> list[dict]:
    """Fetch all child pages (handles pagination)."""
    children = []
    start = 0
    while True:
        url = f"{base_url}/rest/api/content/{page_id}/child/page?limit={_PAGE_LIMIT}&start={start}"
        data = _api_get(url)
        results = data.get("results", [])
        children.extend(results)
        if len(results) < _PAGE_LIMIT:
            break
        start += _PAGE_LIMIT
    return children


def _html_to_markdown(html: str, page_title: str) -> str:
    """Convert Confluence storage format HTML to clean Markdown."""
    from markdownify import markdownify as md

    if not html or not html.strip():
        return ""

    text = md(
        html,
        heading_style="ATX",
        bullets="-",
        strip=["script", "style", "nav", "footer", "header"],
        convert=["table", "tr", "td", "th", "thead", "tbody",
                 "p", "br", "h1", "h2", "h3", "h4", "h5", "h6",
                 "ul", "ol", "li", "a", "img", "strong", "em",
                 "code", "pre", "blockquote", "hr", "div", "span"],
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


async def crawl_confluence(
    url: str,
    max_pages: int = 500,
    max_depth: int = 20,
    progress_callback: callable | None = None,
) -> CrawlResult:
    """Crawl a Confluence page tree starting from the given URL.

    Args:
        url: Confluence page URL.
        max_pages: Maximum number of pages to crawl.
        max_depth: Maximum tree depth to traverse.
        progress_callback: Optional callback(pages_done, total_estimated).

    Returns:
        CrawlResult with all crawled pages.
    """
    t0 = time.perf_counter()
    base_url, space_key, root_page_id = parse_confluence_url(url)

    logger.info("Confluence crawl started", extra={
        "url": url, "base_url": base_url,
        "space_key": space_key, "root_page_id": root_page_id,
        "max_pages": max_pages,
    })

    result = CrawlResult(base_url=base_url, space_key=space_key)

    queue: list[tuple[str, int]] = [(root_page_id, 0)]
    visited: set[str] = set()
    pages_done = 0

    while queue and pages_done < max_pages:
        page_id, depth = queue.pop(0)

        if page_id in visited:
            continue
        visited.add(page_id)

        if depth > max_depth:
            continue

        try:
            title, html_body = await asyncio.to_thread(
                _get_page_content, base_url, page_id
            )
        except Exception as exc:
            error_msg = f"Failed to fetch page {page_id}: {type(exc).__name__}: {exc}"
            logger.warning(error_msg)
            result.errors.append(error_msg)
            continue

        markdown = _html_to_markdown(html_body, title)

        page_url = f"{base_url}/spaces/{space_key}/pages/{page_id}/{quote(title, safe='')}"

        try:
            children = await asyncio.to_thread(
                _get_child_pages, base_url, page_id
            )
        except Exception as exc:
            error_msg = f"Failed to fetch children of page {page_id}: {type(exc).__name__}: {exc}"
            logger.warning(error_msg)
            result.errors.append(error_msg)
            children = []

        page = ConfluencePage(
            page_id=page_id,
            title=title,
            markdown=markdown,
            url=page_url,
            space_key=space_key,
            depth=depth,
            children_count=len(children),
        )
        result.pages.append(page)
        pages_done += 1

        if pages_done == 1:
            result.root_title = title

        for child in children:
            child_id = child.get("id", "")
            if child_id and child_id not in visited:
                queue.append((child_id, depth + 1))

        if progress_callback:
            estimated_total = pages_done + len(queue)
            try:
                progress_callback(pages_done, estimated_total)
            except Exception:
                pass

        logger.debug("Page crawled", extra={
            "page_id": page_id, "title": title,
            "depth": depth, "children": len(children),
            "md_length": len(markdown),
        })

    result.total_pages = pages_done
    result.crawl_ms = round((time.perf_counter() - t0) * 1000, 1)

    logger.info("Confluence crawl completed", extra={
        "url": url, "total_pages": pages_done,
        "crawl_ms": result.crawl_ms,
        "errors": len(result.errors),
    })

    return result
