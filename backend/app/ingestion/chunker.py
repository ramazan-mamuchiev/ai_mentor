"""Chunking logic: split parsed sections into appropriately sized chunks.

Handles splitting large sections (>max_tokens) and merging small ones (<min_tokens).
"""

import re
from dataclasses import dataclass


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


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English, ~2 for mixed."""
    return max(1, len(text) // 3)


def _split_text(text: str, max_tokens: int) -> list[str]:
    """Split text into pieces of at most max_tokens, breaking at paragraph boundaries."""
    paragraphs = re.split(r"\n\n+", text)
    pieces: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for para in paragraphs:
        para_tokens = _estimate_tokens(para)
        if current_tokens + para_tokens > max_tokens and current:
            pieces.append("\n\n".join(current))
            current = []
            current_tokens = 0
        current.append(para)
        current_tokens += para_tokens

    if current:
        pieces.append("\n\n".join(current))

    return pieces


def chunk_sections(
    sections: list[Section],
    max_tokens: int = 1500,
    min_tokens: int = 100,
) -> list[ChunkData]:
    """Convert parsed sections into chunks, splitting large and merging small ones."""
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
            for i, piece in enumerate(pieces):
                suffix = f" (part {i + 1})" if len(pieces) > 1 else ""
                chunks.append(ChunkData(
                    heading_path=section.heading_path + suffix,
                    heading_level=section.heading_level,
                    content=piece.strip(),
                    token_count=_estimate_tokens(piece),
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
    """Merge consecutive small chunks that share the same parent heading."""
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
            buffer = ChunkData(
                heading_path=buffer.heading_path,
                heading_level=buffer.heading_level,
                content=buffer.content + "\n\n" + chunk.content,
                token_count=combined_tokens,
            )
        else:
            result.append(buffer)
            buffer = chunk

    if buffer is not None:
        result.append(buffer)

    return result


def _parent_heading(heading_path: str) -> str:
    parts = heading_path.split(" > ")
    return " > ".join(parts[:-1]) if len(parts) > 1 else heading_path
