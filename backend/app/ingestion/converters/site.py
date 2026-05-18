"""Universal website crawler using Crawl4AI Deep Crawling.

BFS-traverses pages within a single domain, collecting:
- HTML pages as Markdown (via Crawl4AI headless browser)
- Links to downloadable files (PDF, WSDL, YAML, proto, etc.)

Supports crash recovery via on_state_change / resume_state,
cancellation via should_cancel, and domain locking.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile
import time
from dataclasses import dataclass, field
from typing import Callable, Awaitable
from urllib.parse import urlparse

import httpx
from markdownify import markdownify as md_convert

logger = logging.getLogger(__name__)

_FETCH_TIMEOUT = 30
_ANTI_BOT_KEYWORDS = {"cloudflare", "anti-bot", "blocked", "captcha", "challenge"}

DOWNLOADABLE_EXTENSIONS = {
    ".pdf", ".wsdl", ".yaml", ".yml", ".proto", ".md", ".txt",
}

_JSON_DOWNLOAD_PATTERNS = {"swagger", "openapi", "api-docs", "collection"}
_XML_DOWNLOAD_PATTERNS = {"schema", "spec", "types", "wsdl"}


def _get_extension(url: str) -> str:
    """Extract file extension from URL path, ignoring query string."""
    path = urlparse(url).path
    _, ext = os.path.splitext(path)
    return ext.lower()


def _should_download(href: str) -> bool:
    """Decide whether a link points to a downloadable file."""
    ext = _get_extension(href)
    if ext in DOWNLOADABLE_EXTENSIONS:
        return True
    filename = urlparse(href).path.rsplit("/", 1)[-1].lower()
    if ext == ".json":
        return any(p in filename for p in _JSON_DOWNLOAD_PATTERNS)
    if ext == ".xml":
        return any(p in filename for p in _XML_DOWNLOAD_PATTERNS)
    return False


def _detect_format_from_url(href: str) -> str:
    """Map URL extension to ingestion format."""
    ext = _get_extension(href)
    mapping = {
        ".pdf": "pdf",
        ".wsdl": "wsdl",
        ".yaml": "swagger",
        ".yml": "swagger",
        ".proto": "proto",
        ".md": "markdown",
        ".txt": "markdown",
        ".json": "swagger",
        ".xml": "markdown",
    }
    return mapping.get(ext, "markdown")


@dataclass
class CrawledPage:
    url: str
    title: str
    markdown: str
    depth: int = 0


@dataclass
class CrawledFile:
    url: str
    extension: str
    format: str
    local_path: str = ""


@dataclass
class SiteCrawlResult:
    start_url: str = ""
    domain: str = ""
    pages_crawled: int = 0
    files_found: int = 0
    crawl_ms: float = 0.0
    stopped_by_time: bool = False
    errors: list[str] = field(default_factory=list)


def _download_file(url: str, timeout: int = _FETCH_TIMEOUT) -> str | None:
    """Download a file to a temp path. Returns path or None on failure."""
    try:
        with httpx.Client(timeout=timeout, verify=False, follow_redirects=True) as client:
            resp = client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AI Mentor/1.0",
            })
            resp.raise_for_status()
            ext = _get_extension(url) or ".bin"
            fd, path = tempfile.mkstemp(suffix=ext, prefix="ai_mentor_site_")
            with os.fdopen(fd, "wb") as f:
                f.write(resp.content)
            return path
    except Exception as exc:
        logger.warning("Failed to download file", extra={
            "url": url[:300], "error": str(exc)[:200],
        })
        return None


def _is_anti_bot_error(error_message: str | None) -> bool:
    """Check if Crawl4AI error looks like a false-positive anti-bot block."""
    if not error_message:
        return False
    msg = error_message.lower()
    return any(kw in msg for kw in _ANTI_BOT_KEYWORDS)


def _httpx_fetch_as_markdown(url: str, timeout: int = _FETCH_TIMEOUT) -> tuple[str, str]:
    """Fetch a page via httpx and convert HTML to markdown.

    Returns (title, markdown_text). Both empty on failure.
    """
    try:
        with httpx.Client(timeout=timeout, verify=False, follow_redirects=True) as client:
            resp = client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 AI Mentor/1.0",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            })
            resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        if "html" not in content_type and "xml" not in content_type:
            return "", ""

        html = resp.text
        if not html or len(html.strip()) < 100:
            return "", ""

        title = ""
        title_match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
        if title_match:
            title = title_match.group(1).strip()

        markdown_text = md_convert(html, strip=["script", "style", "nav", "footer", "header"])
        markdown_text = re.sub(r"\n{3,}", "\n\n", markdown_text).strip()

        return title, markdown_text
    except Exception as exc:
        logger.warning("httpx fallback fetch failed", extra={
            "url": url[:300], "error": str(exc)[:200],
        })
        return "", ""


async def crawl_site(
    url: str,
    max_depth: int = 5,
    max_pages: int = 1000,
    max_seconds: int = 3600,
    page_callback: Callable[[CrawledPage], None] | None = None,
    file_callback: Callable[[CrawledFile], None] | None = None,
    on_state_change: Callable[[dict], Awaitable[None] | None] | None = None,
    resume_state: dict | None = None,
    should_cancel: Callable[[], Awaitable[bool] | bool] | None = None,
) -> SiteCrawlResult:
    """Crawl a website using Crawl4AI BFS deep crawling.

    For each HTML page: extracts markdown, calls page_callback.
    For each downloadable file link (PDF, WSDL, etc.): downloads the file,
    calls file_callback.

    Args:
        url: Starting URL.
        max_depth: Maximum link depth from start page.
        max_pages: Maximum number of HTML pages to crawl.
        max_seconds: Wall-clock time limit.
        page_callback: Called for each crawled HTML page.
        file_callback: Called for each downloaded file.
        on_state_change: Crawl4AI state persistence callback for crash recovery.
        resume_state: Previously saved state to resume from.
        should_cancel: Async/sync callback; return True to stop crawl.

    Returns:
        SiteCrawlResult with crawl statistics.
    """
    from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
    from crawl4ai.deep_crawling import BFSDeepCrawlStrategy
    from crawl4ai.deep_crawling.filters import FilterChain, DomainFilter

    t0 = time.perf_counter()
    parsed = urlparse(url)
    domain = parsed.netloc
    result = SiteCrawlResult(start_url=url, domain=domain)

    logger.info("Site crawl started", extra={
        "url": url, "domain": domain,
        "max_depth": max_depth, "max_pages": max_pages,
        "max_seconds": max_seconds,
        "resuming": resume_state is not None,
    })

    strategy_kwargs: dict = {
        "max_depth": max_depth,
        "include_external": False,
        "max_pages": max_pages,
        "filter_chain": FilterChain([
            DomainFilter(allowed_domains=[domain]),
        ]),
    }

    if resume_state is not None:
        strategy_kwargs["resume_state"] = resume_state
    if on_state_change is not None:
        strategy_kwargs["on_state_change"] = on_state_change
    if should_cancel is not None:
        strategy_kwargs["should_cancel"] = should_cancel

    strategy = BFSDeepCrawlStrategy(**strategy_kwargs)

    config = CrawlerRunConfig(
        deep_crawl_strategy=strategy,
        stream=True,
    )

    downloaded_files: set[str] = set()

    try:
        async with AsyncWebCrawler() as crawler:
            async for page_result in await crawler.arun(url, config=config):
                if time.perf_counter() - t0 > max_seconds:
                    logger.warning("Site crawl hit time limit", extra={
                        "max_seconds": max_seconds,
                        "pages_crawled": result.pages_crawled,
                    })
                    result.stopped_by_time = True
                    result.errors.append(
                        f"Crawl stopped: time limit of {max_seconds}s reached "
                        f"after {result.pages_crawled} pages"
                    )
                    strategy.cancel()
                    break

                depth = 0
                if page_result.metadata and isinstance(page_result.metadata, dict):
                    depth = page_result.metadata.get("depth", 0)

                title = ""
                md_text = ""

                if not page_result.success:
                    if _is_anti_bot_error(page_result.error_message):
                        logger.info("Anti-bot block detected, trying httpx fallback", extra={
                            "url": page_result.url,
                            "original_error": (page_result.error_message or "")[:200],
                        })
                        fb_title, fb_md = await asyncio.to_thread(
                            _httpx_fetch_as_markdown, page_result.url,
                        )
                        if fb_md:
                            title = fb_title
                            md_text = fb_md
                            logger.info("httpx fallback succeeded", extra={
                                "url": page_result.url,
                                "md_length": len(fb_md),
                            })
                        else:
                            result.errors.append(
                                f"Failed: {page_result.url} — {page_result.error_message or 'unknown'} "
                                f"(httpx fallback also failed)"
                            )
                            continue
                    else:
                        result.errors.append(
                            f"Failed: {page_result.url} — {page_result.error_message or 'unknown'}"
                        )
                        continue
                else:
                    md = page_result.markdown
                    if hasattr(md, "fit_markdown") and md.fit_markdown:
                        md_text = md.fit_markdown
                    elif hasattr(md, "raw_markdown"):
                        md_text = md.raw_markdown
                    else:
                        md_text = str(md) if md else ""

                    if page_result.metadata and isinstance(page_result.metadata, dict):
                        title = page_result.metadata.get("title", "")

                if md_text and md_text.strip() and page_callback:
                    page = CrawledPage(
                        url=page_result.url,
                        title=title or page_result.url,
                        markdown=md_text,
                        depth=depth,
                    )
                    try:
                        await asyncio.to_thread(page_callback, page)
                    except Exception as cb_exc:
                        logger.warning("page_callback failed", extra={
                            "url": page_result.url, "error": str(cb_exc)[:200],
                        })
                    result.pages_crawled += 1

                if file_callback:
                    internal_links = []
                    if hasattr(page_result, "links") and isinstance(page_result.links, dict):
                        internal_links = page_result.links.get("internal", [])

                    for link in internal_links:
                        href = link.get("href", "") if isinstance(link, dict) else str(link)
                        if not href or href in downloaded_files:
                            continue
                        if not _should_download(href):
                            continue

                        downloaded_files.add(href)
                        local_path = await asyncio.to_thread(_download_file, href)
                        if local_path is None:
                            continue

                        ext = _get_extension(href)
                        fmt = _detect_format_from_url(href)

                        crawled_file = CrawledFile(
                            url=href,
                            extension=ext,
                            format=fmt,
                            local_path=local_path,
                        )
                        try:
                            await asyncio.to_thread(file_callback, crawled_file)
                        except Exception as cb_exc:
                            logger.warning("file_callback failed", extra={
                                "url": href, "error": str(cb_exc)[:200],
                            })
                        result.files_found += 1

                logger.debug("Page crawled", extra={
                    "url": page_result.url, "depth": depth,
                    "md_length": len(md_text),
                    "file_links": len(downloaded_files),
                })

    except Exception as exc:
        error_msg = f"Crawl error: {type(exc).__name__}: {exc}"
        result.errors.append(error_msg[:500])
        logger.error("Site crawl failed", extra={
            "url": url, "error_type": type(exc).__name__,
            "pages_crawled": result.pages_crawled,
        }, exc_info=True)
        raise

    result.crawl_ms = round((time.perf_counter() - t0) * 1000, 1)

    logger.info("Site crawl completed", extra={
        "url": url, "domain": domain,
        "pages_crawled": result.pages_crawled,
        "files_found": result.files_found,
        "crawl_ms": result.crawl_ms,
        "errors": len(result.errors),
    })

    return result
