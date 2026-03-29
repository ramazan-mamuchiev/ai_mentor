"""GitHub repository importer via GitHub REST API.

Fetches the full file tree of a public repository using the Git Trees API,
filters files by supported extensions, and downloads each file via
raw.githubusercontent.com.  No git clone required.

Supports optional authentication via GITHUB_API_TOKEN for higher rate limits
(5000 req/hr authenticated vs 60 req/hr anonymous).
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
import time
from dataclasses import dataclass, field
from typing import Callable

import httpx

logger = logging.getLogger(__name__)

_FETCH_TIMEOUT = 30
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Lexiro/1.0"

SUPPORTED_EXTENSIONS = {
    ".md", ".txt", ".yaml", ".yml", ".json", ".pdf",
    ".proto", ".wsdl", ".xml",
}

EXCLUDED_DIRS = {
    ".github", ".git", "node_modules", "__pycache__", ".venv", "venv",
    "dist", ".idea", ".vscode",
}

FORMAT_MAP = {
    ".md": "markdown",
    ".txt": "markdown",
    ".yaml": "swagger",
    ".yml": "swagger",
    ".json": "swagger",
    ".pdf": "pdf",
    ".proto": "proto",
    ".wsdl": "wsdl",
    ".xml": "xml",
}

# ---------------------------------------------------------------------------
# Smart XML classification: decide whether an XML file is documentation
# (DocBook, DITA, XSD, WSDL, etc.) or noise (XSLT, SVG, configs, i18n).
# We inspect the root element of the first ~4 KB of the file.
# ---------------------------------------------------------------------------

_XML_ROOT_TAG_RE = re.compile(
    r"<(?:\w+:)?(\w+)[\s/>]",
)

_DOC_XML_ROOT_TAGS = frozenset({
    # DocBook
    "book", "article", "chapter", "section", "refentry", "set", "part",
    "appendix", "preface", "glossary", "bibliography", "index",
    # DITA
    "topic", "concept", "task", "reference", "map", "bookmap", "ditamap",
    "learningContent", "troubleshooting",
    # XSD / WSDL (supplementary to .wsdl extension)
    "schema", "definitions",
    # TEI (scholarly docs)
    "TEI",
    # Mallard (GNOME docs)
    "page",
    # Generic spec roots
    "specification", "standard", "document", "spec", "rfc",
})

_NOISE_XML_ROOT_TAGS = frozenset({
    # XSLT
    "stylesheet", "transform",
    # Graphics
    "svg",
    # HTML mislabeled as .xml
    "html", "HTML",
    # Build systems
    "Project", "project", "build", "target", "ivy", "assembly",
    "pom", "settings", "plugin", "metadata",
    # .NET / Java configs
    "configuration", "appSettings", "connectionStrings",
    "web", "beans", "context",
    # i18n / resources
    "resources", "xliff", "translations", "root", "data",
    # Feeds
    "rss", "feed",
    # Apple
    "plist",
    # MIME
    "mime-info",
    # Android
    "manifest", "selector", "shape", "vector", "layer-list",
    "RelativeLayout", "LinearLayout", "ConstraintLayout", "FrameLayout",
})

_XML_MIN_DOC_SIZE = 5_000


def _classify_xml_content(content_head: bytes) -> bool:
    """Return True if XML content looks like documentation, False if noise.

    Inspects the root element tag of the first few KB.
    """
    try:
        text = content_head.decode("utf-8", errors="ignore")
    except Exception:
        return False

    text_stripped = text.lstrip()
    if text_stripped.startswith("<?"):
        close = text_stripped.find("?>")
        if close != -1:
            text_stripped = text_stripped[close + 2:].lstrip()

    while text_stripped.startswith("<!"):
        close = text_stripped.find(">")
        if close == -1:
            break
        text_stripped = text_stripped[close + 1:].lstrip()

    m = _XML_ROOT_TAG_RE.search(text_stripped[:500])
    if not m:
        return False

    root_tag = m.group(1)

    if root_tag in _DOC_XML_ROOT_TAGS:
        return True
    if root_tag in _NOISE_XML_ROOT_TAGS:
        return False

    return len(content_head) >= _XML_MIN_DOC_SIZE


def _get_extension(path: str) -> str:
    _, ext = os.path.splitext(path)
    return ext.lower()


def _detect_format(path: str) -> str:
    return FORMAT_MAP.get(_get_extension(path), "markdown")


def _is_excluded(path: str) -> bool:
    parts = path.split("/")
    return any(part in EXCLUDED_DIRS for part in parts)


_GITHUB_URL_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/"
    r"(?P<owner>[^/]+)/(?P<repo>[^/]+)"
    r"(?:/tree/(?P<branch>[^/]+))?",
)


def parse_github_url(url: str) -> tuple[str, str, str | None]:
    """Parse a GitHub repository URL.

    Returns:
        (owner, repo, branch_or_none)

    Raises:
        ValueError: If the URL is not a valid GitHub repository URL.
    """
    url = url.strip().rstrip("/")
    m = _GITHUB_URL_RE.match(url)
    if not m:
        raise ValueError(f"Not a valid GitHub repository URL: {url}")

    owner = m.group("owner")
    repo = m.group("repo")
    if repo.endswith(".git"):
        repo = repo[:-4]
    branch = m.group("branch")
    return owner, repo, branch


@dataclass
class GitHubFile:
    path: str
    url: str
    size: int
    format: str
    local_path: str = ""


@dataclass
class GitHubCrawlResult:
    repo: str = ""
    branch: str = ""
    files_found: int = 0
    files_downloaded: int = 0
    files_skipped: int = 0
    crawl_ms: float = 0.0
    errors: list[str] = field(default_factory=list)


def _build_headers(token: str = "") -> dict[str, str]:
    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _download_file(
    url: str,
    suffix: str,
    timeout: int = _FETCH_TIMEOUT,
    classify_xml: bool = False,
) -> str | None:
    """Download a raw file to a temp path. Returns path or None on failure.

    When *classify_xml* is True and the suffix is .xml, the downloaded content
    is checked with _classify_xml_content(); returns None for noise XML.
    """
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": _USER_AGENT})
            resp.raise_for_status()
            content = resp.content

            if classify_xml and suffix.lower() == ".xml":
                head = content[:4096]
                if not _classify_xml_content(head):
                    logger.debug("XML classified as noise, skipping", extra={
                        "url": url[:300], "head_bytes": len(head),
                    })
                    return None

            fd, path = tempfile.mkstemp(suffix=suffix, prefix="lexiro_gh_")
            with os.fdopen(fd, "wb") as f:
                f.write(content)
            return path
    except Exception as exc:
        logger.warning("GitHub file download failed", extra={
            "url": url[:300], "error": str(exc)[:200],
        })
        return None


async def crawl_github(
    owner: str,
    repo: str,
    branch: str = "main",
    token: str = "",
    max_files: int = 500,
    max_file_size_mb: int = 10,
    extensions: set[str] | None = None,
    file_callback: Callable[[GitHubFile], None] | None = None,
) -> GitHubCrawlResult:
    """Fetch repo file tree and download supported files.

    Uses GET /repos/{owner}/{repo}/git/trees/{branch}?recursive=1 to list
    all files in a single API call, then downloads each matching file from
    raw.githubusercontent.com (no API rate limit for raw downloads).

    Args:
        owner: GitHub user or organization.
        repo: Repository name.
        branch: Branch or tag (default "main").
        token: Optional GitHub PAT for higher API rate limits.
        max_files: Maximum number of files to download.
        max_file_size_mb: Skip files larger than this (MB).
        extensions: Whitelist of extensions; defaults to SUPPORTED_EXTENSIONS.
        file_callback: Called for each downloaded file with a GitHubFile.

    Returns:
        GitHubCrawlResult with download statistics.
    """
    import asyncio

    t0 = time.perf_counter()
    result = GitHubCrawlResult(repo=f"{owner}/{repo}", branch=branch)
    allowed_ext = extensions or SUPPORTED_EXTENSIONS
    max_size_bytes = max_file_size_mb * 1024 * 1024

    logger.info("GitHub crawl started", extra={
        "owner": owner, "repo": repo, "branch": branch,
        "max_files": max_files, "extensions": sorted(allowed_ext),
    })

    tree_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
    headers = _build_headers(token)

    async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT) as client:
        resp = await client.get(tree_url, headers=headers)

    if resp.status_code == 404:
        raise ValueError(
            f"Repository {owner}/{repo} (branch: {branch}) not found. "
            f"Check the URL and ensure the repository is public."
        )
    if resp.status_code == 403:
        raise ValueError(
            "GitHub API rate limit exceeded. "
            "Try again later or configure GITHUB_API_TOKEN."
        )
    resp.raise_for_status()

    tree_data = resp.json()
    tree = tree_data.get("tree", [])
    truncated = tree_data.get("truncated", False)

    if truncated:
        logger.warning("GitHub tree was truncated (repo too large)", extra={
            "owner": owner, "repo": repo,
        })
        result.errors.append("Repository tree was truncated by GitHub API; some files may be missing")

    candidates = []
    for item in tree:
        if item.get("type") != "blob":
            continue
        path = item.get("path", "")
        size = item.get("size", 0)

        if _is_excluded(path):
            continue

        ext = _get_extension(path)
        if ext not in allowed_ext:
            continue

        if size > max_size_bytes:
            result.files_skipped += 1
            logger.debug("Skipping large file", extra={
                "path": path, "size": size, "max": max_size_bytes,
            })
            continue

        candidates.append((path, size))

    result.files_found = len(candidates)

    if len(candidates) > max_files:
        logger.warning("Limiting GitHub files", extra={
            "found": len(candidates), "max": max_files,
        })
        result.errors.append(
            f"Repository has {len(candidates)} matching files, "
            f"limited to {max_files}"
        )
        candidates = candidates[:max_files]

    logger.info("GitHub tree fetched", extra={
        "owner": owner, "repo": repo,
        "total_blobs": sum(1 for i in tree if i.get("type") == "blob"),
        "matching_files": len(candidates),
        "truncated": truncated,
    })

    for file_path, file_size in candidates:
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{file_path}"
        ext = _get_extension(file_path)
        fmt = _detect_format(file_path)

        local_path = await asyncio.to_thread(
            _download_file, raw_url, ext or ".bin", _FETCH_TIMEOUT, ext == ".xml",
        )
        if local_path is None:
            if ext == ".xml":
                result.files_skipped += 1
                logger.debug("XML file skipped (noise)", extra={"path": file_path})
            else:
                result.errors.append(f"Download failed: {file_path}")
            continue

        gh_file = GitHubFile(
            path=file_path,
            url=raw_url,
            size=file_size,
            format=fmt,
            local_path=local_path,
        )

        if file_callback:
            try:
                await asyncio.to_thread(file_callback, gh_file)
            except Exception as cb_exc:
                logger.warning("file_callback failed", extra={
                    "path": file_path, "error": str(cb_exc)[:200],
                })
                result.errors.append(f"Callback error for {file_path}: {cb_exc}")
                continue

        result.files_downloaded += 1

    result.crawl_ms = round((time.perf_counter() - t0) * 1000, 1)

    logger.info("GitHub crawl completed", extra={
        "repo": f"{owner}/{repo}", "branch": branch,
        "files_found": result.files_found,
        "files_downloaded": result.files_downloaded,
        "files_skipped": result.files_skipped,
        "crawl_ms": result.crawl_ms,
        "errors": len(result.errors),
    })

    return result
