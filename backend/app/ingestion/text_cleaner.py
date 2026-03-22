"""Text cleaning utilities for the ingestion pipeline.

Removes Markdown formatting artifacts that hurt embedding quality:
- Inline formatting: bold, italic, strikethrough, inline code
- Links: keeps visible text, drops URLs
- Images: removes entirely (alt text is rarely useful for search)
- HTML tags: strips completely
- Unicode: normalizes to NFKC form

Cleaning is applied *before* embedding but the original Markdown is
preserved in the stored chunk content for display purposes.
"""

import re
import unicodedata

_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]+\)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_AUTOLINK_RE = re.compile(r"<(https?://[^>]+)>")
_BARE_URL_RE = re.compile(r"(?<!\()https?://\S+")
_HTML_TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>")
_INLINE_CODE_RE = re.compile(r"``([^`\n]+)``|`([^`\n]+)`")
_BOLD_ITALIC_RE = re.compile(r"\*{1,3}([^\n*]+?)\*{1,3}")
_UNDERSCORE_BI_RE = re.compile(r"_{1,3}([^\n_]+?)_{1,3}")
_STRIKETHROUGH_RE = re.compile(r"~~([^\n~]+?)~~")
_HEADING_HASH_RE = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_BLOCKQUOTE_RE = re.compile(r"^>\s?", re.MULTILINE)
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")


def normalize_unicode(text: str) -> str:
    """Normalize Unicode to NFKC form.

    Collapses visually identical but byte-different characters
    (e.g. fullwidth latin, ligatures, non-breaking spaces).
    """
    return unicodedata.normalize("NFKC", text)


def _inline_code_repl_triple(m: re.Match) -> str:
    """Handle ```triple``` backtick inline code (single-line only)."""
    return m.group(1)


def _inline_code_repl(m: re.Match) -> str:
    """Handle ``double`` and `single` backtick inline code."""
    return m.group(1) or m.group(2)


def clean_heading(text: str) -> str:
    """Remove Markdown formatting from heading text.

    Headings appear in heading_path and are used for embedding enrichment,
    so they must be plain text.
    """
    text = _IMAGE_RE.sub("", text)
    text = _LINK_RE.sub(r"\1", text)
    text = _AUTOLINK_RE.sub(r"\1", text)
    text = re.sub(r"```([^`\n]+)```", _inline_code_repl_triple, text)
    text = _INLINE_CODE_RE.sub(_inline_code_repl, text)
    text = _BOLD_ITALIC_RE.sub(r"\1", text)
    text = _UNDERSCORE_BI_RE.sub(r"\1", text)
    text = _STRIKETHROUGH_RE.sub(r"\1", text)
    text = _HTML_TAG_RE.sub("", text)
    return text.strip()


def clean_for_embedding(text: str) -> str:
    """Clean Markdown content for embedding generation.

    Preserves code blocks (they contain valuable API details) but strips
    formatting noise that confuses the embedding model.
    """
    code_blocks: list[str] = []

    def _save_code_block(m: re.Match) -> str:
        code_blocks.append(m.group(0))
        return f"\x00CODEBLOCK{len(code_blocks) - 1}\x00"

    text = re.sub(r"```([^`\n]+)```", _inline_code_repl_triple, text)

    text = re.sub(r"```[\s\S]*?```|```[\s\S]*$", _save_code_block, text)

    text = _IMAGE_RE.sub("", text)
    text = _LINK_RE.sub(r"\1", text)
    text = _AUTOLINK_RE.sub(r"\1", text)
    text = _BARE_URL_RE.sub("", text)
    text = _HTML_TAG_RE.sub("", text)
    text = _INLINE_CODE_RE.sub(_inline_code_repl, text)
    text = _BOLD_ITALIC_RE.sub(r"\1", text)
    text = _UNDERSCORE_BI_RE.sub(r"\1", text)
    text = _STRIKETHROUGH_RE.sub(r"\1", text)
    text = _HEADING_HASH_RE.sub("", text)
    text = _BLOCKQUOTE_RE.sub("", text)

    for i, block in enumerate(code_blocks):
        text = text.replace(f"\x00CODEBLOCK{i}\x00", block)

    text = _MULTI_NEWLINE_RE.sub("\n\n", text)
    text = _MULTI_SPACE_RE.sub(" ", text)

    return text.strip()
