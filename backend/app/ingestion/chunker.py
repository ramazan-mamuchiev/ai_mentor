"""Chunking logic: split parsed sections into appropriately sized chunks.

Handles splitting large sections (>max_tokens) and merging small ones (<min_tokens).
Preserves code blocks and tables as atomic units during splitting.
Adds configurable overlap between split pieces for better retrieval.
"""

import logging
import re
from dataclasses import dataclass

_CODE_BLOCK_RE = re.compile(r"```[\s\S]*?```|```[\s\S]*$", re.MULTILINE)
_TABLE_RE = re.compile(
    r"(?:^[^\S\n]*\|.+\|[^\S\n]*\n)(?:[^\S\n]*\|[-:\s|]+\|[^\S\n]*\n)(?:[^\S\n]*\|.+\|[^\S\n]*\n?)+",
    re.MULTILINE,
)

from app.config import settings

OVERLAP_PARAGRAPHS = settings.chunk_overlap_paragraphs

logger = logging.getLogger(__name__)


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
    """Count tokens using tiktoken (cl100k_base) with heuristic fallback."""
    from app.utils.tokenizer import count_tokens
    return count_tokens(text)


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


def _is_flat_section(section: Section) -> bool:
    """Check if section is 'flat' (no meaningful heading structure)."""
    hp = section.heading_path.strip()
    return hp in ("Document", "") or section.heading_level == 0


def _semantic_split(text: str, max_tokens: int) -> list[str]:
    """Split text using embedding similarity to find natural topic boundaries.

    Uses a sliding window of paragraphs, embeds each, and places split
    boundaries where cosine similarity between consecutive windows drops
    below a percentile threshold. Falls back to token-based split on error.

    WARNING: calls embed_texts synchronously (network I/O). Safe in Celery
    workers; will block the event loop if called from async code. Keep
    semantic_chunking_enabled=False for real-time async ingestion.
    """
    import numpy as np

    blocks = _split_into_blocks(text)
    if len(blocks) <= 2:
        return _split_text(text, max_tokens)

    try:
        from app.ingestion.embedder import embed_texts
        embeddings, _ = embed_texts(blocks)
    except Exception:
        logger.warning("Semantic chunking embedding failed, falling back to token split",
                        exc_info=True)
        return _split_text(text, max_tokens)

    if not embeddings or len(embeddings) < 2:
        return _split_text(text, max_tokens)

    vecs = np.array(embeddings, dtype=np.float32)

    similarities = np.array([
        float(np.dot(vecs[i], vecs[i + 1])) for i in range(len(vecs) - 1)
    ])

    threshold = float(np.percentile(similarities, settings.semantic_similarity_percentile))

    split_indices: list[int] = []
    for i, sim in enumerate(similarities):
        if sim < threshold:
            split_indices.append(i + 1)

    logger.info("Semantic split boundaries found", extra={
        "blocks": len(blocks), "boundaries": len(split_indices),
        "threshold": round(threshold, 4),
        "min_sim": round(float(similarities.min()), 4) if len(similarities) > 0 else 0,
        "max_sim": round(float(similarities.max()), 4) if len(similarities) > 0 else 0,
    })

    if not split_indices:
        return _split_text(text, max_tokens)

    groups: list[list[str]] = []
    prev = 0
    for idx in split_indices:
        group = blocks[prev:idx]
        if group:
            groups.append(group)
        prev = idx
    if prev < len(blocks):
        groups.append(blocks[prev:])

    pieces: list[str] = []
    for group in groups:
        piece = "\n\n".join(group)
        piece_tokens = _estimate_tokens(piece)
        if piece_tokens > max_tokens:
            pieces.extend(_split_text(piece, max_tokens))
        else:
            pieces.append(piece)

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

    semantic_enabled = settings.semantic_chunking_enabled
    semantic_threshold = settings.semantic_chunk_threshold

    chunks: list[ChunkData] = []

    for section in sections:
        content = section.content.strip()
        if not content:
            continue

        tokens = _estimate_tokens(content)

        if tokens > max_tokens:
            use_semantic = (
                semantic_enabled
                and _is_flat_section(section)
                and tokens >= semantic_threshold
            )
            if use_semantic:
                logger.info("Using semantic split for flat section", extra={
                    "heading_path": section.heading_path, "tokens": tokens,
                })
                pieces = _semantic_split(content, max_tokens)
            else:
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
