"""Chunking logic: split parsed sections into appropriately sized chunks.

Handles splitting large sections (>max_tokens) and merging small ones (<min_tokens).
Preserves code blocks and tables as atomic units during splitting.
Adds configurable overlap between split pieces for better retrieval.
Uses the real E5 tokenizer for accurate token counting when available.
"""

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from transformers import PreTrainedTokenizerBase

_CODE_BLOCK_RE = re.compile(r"```[\s\S]*?```|```[\s\S]*$", re.MULTILINE)
_TABLE_RE = re.compile(
    r"(?:^[^\S\n]*\|.+\|[^\S\n]*\n)(?:[^\S\n]*\|[-:\s|]+\|[^\S\n]*\n)(?:[^\S\n]*\|.+\|[^\S\n]*\n?)+",
    re.MULTILINE,
)

from app.config import settings

OVERLAP_PARAGRAPHS = settings.chunk_overlap_paragraphs

logger = logging.getLogger(__name__)

_tokenizer: "PreTrainedTokenizerBase | None" = None
_tokenizer_load_failed: bool = False


def _get_tokenizer() -> "PreTrainedTokenizerBase | None":
    """Lazy-load the real tokenizer for the configured embedding model.

    Falls back to None (heuristic) if transformers is not installed or
    the model tokenizer can't be loaded.
    """
    global _tokenizer, _tokenizer_load_failed
    if _tokenizer is not None:
        return _tokenizer
    if _tokenizer_load_failed:
        return None
    try:
        from transformers import AutoTokenizer

        model_name = settings.embedding_model_local
        _tokenizer = AutoTokenizer.from_pretrained(model_name)
        logger.info("Loaded real tokenizer for chunking", extra={"model": model_name})
        return _tokenizer
    except Exception:
        _tokenizer_load_failed = True
        logger.info("Real tokenizer unavailable, using word-based heuristic for token counting")
        return None


@dataclass
class Section:
    heading_path: str
    heading_level: int
    content: str


@dataclass
class ChunkData:
    heading_path: str
    heading_level: int
    content: str
    token_count: int
    parent_content: str | None = None


def _estimate_tokens(text: str) -> int:
    """Count tokens using the real model tokenizer, falling back to heuristic.

    When the real tokenizer is available (from transformers), uses it for exact
    counts. Otherwise falls back to word-based heuristic (len(words) * 1.3).
    """
    if not text:
        return 1
    tokenizer = _get_tokenizer()
    if tokenizer is not None:
        return max(1, len(tokenizer.encode(text, add_special_tokens=False)))
    words = text.split()
    return max(1, int(len(words) * 1.3))


def _split_into_blocks(text: str) -> list[str]:
    """Split text into atomic blocks: code fences, tables, and paragraphs.

    Code blocks and tables are never split across chunks.
    """
    protected: list[tuple[int, int, str]] = []
    for m in _CODE_BLOCK_RE.finditer(text):
        protected.append((m.start(), m.end(), m.group()))
    for m in _TABLE_RE.finditer(text):
        if not any(s <= m.start() < e for s, e, _ in protected):
            protected.append((m.start(), m.end(), m.group()))
    protected.sort(key=lambda x: x[0])

    blocks: list[str] = []
    cursor = 0
    for start, end, matched in protected:
        before = text[cursor:start].strip()
        if before:
            for para in re.split(r"\n\n+", before):
                p = para.strip()
                if p:
                    blocks.append(p)
        blocks.append(matched.strip())
        cursor = end

    tail = text[cursor:].strip()
    if tail:
        for para in re.split(r"\n\n+", tail):
            p = para.strip()
            if p:
                blocks.append(p)

    return blocks


def _split_text(text: str, max_tokens: int) -> list[str]:
    """Split text into pieces respecting code blocks, tables, and paragraph boundaries.

    Adds OVERLAP_PARAGRAPHS trailing blocks from the previous piece to the next
    for better retrieval at chunk boundaries.
    """
    blocks = _split_into_blocks(text)
    if not blocks:
        return [text] if text.strip() else []

    raw_pieces: list[list[str]] = []
    current: list[str] = []
    current_tokens = 0

    for block in blocks:
        block_tokens = _estimate_tokens(block)
        if current_tokens + block_tokens > max_tokens and current:
            raw_pieces.append(current)
            current = []
            current_tokens = 0
        current.append(block)
        current_tokens += block_tokens

    if current:
        raw_pieces.append(current)

    if len(raw_pieces) <= 1:
        return ["\n\n".join(p) for p in raw_pieces]

    pieces: list[str] = ["\n\n".join(raw_pieces[0])]
    for i in range(1, len(raw_pieces)):
        overlap = raw_pieces[i - 1][-OVERLAP_PARAGRAPHS:]
        combined = overlap + raw_pieces[i]
        pieces.append("\n\n".join(combined))

    return pieces


def chunk_sections(
    sections: list[Section],
    max_tokens: int | None = None,
    min_tokens: int | None = None,
) -> list[ChunkData]:
    """Convert parsed sections into chunks, splitting large and merging small ones."""
    if max_tokens is None:
        max_tokens = settings.chunk_max_tokens
    if min_tokens is None:
        min_tokens = settings.chunk_min_tokens

    if not sections:
        return []

    chunks: list[ChunkData] = []

    for section in sections:
        content = section.content.strip()
        if not content:
            continue

        tokens = _estimate_tokens(content)

        if tokens > max_tokens:
            pieces = _split_text(content, max_tokens)
            parent = content if len(pieces) > 1 else None
            for i, piece in enumerate(pieces):
                suffix = f" (part {i + 1})" if len(pieces) > 1 else ""
                chunks.append(ChunkData(
                    heading_path=section.heading_path + suffix,
                    heading_level=section.heading_level,
                    content=piece.strip(),
                    token_count=_estimate_tokens(piece),
                    parent_content=parent,
                ))
        else:
            chunks.append(ChunkData(
                heading_path=section.heading_path,
                heading_level=section.heading_level,
                content=content,
                token_count=tokens,
            ))

    merged = _merge_small_chunks(chunks, min_tokens, max_tokens)
    return merged


def _merge_small_chunks(
    chunks: list[ChunkData],
    min_tokens: int,
    max_tokens: int,
) -> list[ChunkData]:
    """Merge consecutive small chunks that share the same parent heading.

    When merging, heading_path combines both paths (if different) and
    token_count is recalculated on the merged text for accuracy.
    """
    if not chunks:
        return []

    result: list[ChunkData] = []
    buffer: ChunkData | None = None

    for chunk in chunks:
        if buffer is None:
            buffer = chunk
            continue

        combined_tokens = buffer.token_count + chunk.token_count
        same_parent = _parent_heading(buffer.heading_path) == _parent_heading(chunk.heading_path)

        if buffer.token_count < min_tokens and same_parent and combined_tokens <= max_tokens:
            merged_parent = buffer.parent_content or chunk.parent_content
            merged_content = buffer.content + "\n\n" + chunk.content
            if buffer.heading_path != chunk.heading_path:
                merged_heading = f"{buffer.heading_path} + {chunk.heading_path}"
            else:
                merged_heading = buffer.heading_path
            buffer = ChunkData(
                heading_path=merged_heading,
                heading_level=buffer.heading_level,
                content=merged_content,
                token_count=_estimate_tokens(merged_content),
                parent_content=merged_parent,
            )
        else:
            result.append(buffer)
            buffer = chunk

    if buffer is not None:
        result.append(buffer)

    return result


def _parent_heading(heading_path: str) -> str:
    """Extract parent heading from a heading_path.

    Handles merged paths like "Parent > A + Parent > B" by taking the
    first component before " + " for parent extraction.
    """
    base = heading_path.split(" + ")[0]
    parts = base.split(" > ")
    return " > ".join(parts[:-1]) if len(parts) > 1 else parts[0]
