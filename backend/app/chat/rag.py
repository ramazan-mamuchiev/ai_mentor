"""RAG (Retrieval Augmented Generation) service for chat."""

import logging
import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import ChatMessage
from app.search.service import search_documents

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are IPCodex AI Assistant — an expert on device integration documentation.

Rules:
- Answer questions based ONLY on the provided documentation context.
- If the context doesn't contain the answer, say so honestly.
- Always cite the source document and section when referencing information.
- Format code examples with proper syntax highlighting using markdown code blocks.
- Be concise but thorough.
- Respond in the same language as the user's question."""


def _format_context(chunks: list[dict]) -> str:
    """Format retrieved chunks into a context string for the LLM."""
    if not chunks:
        return "No relevant documentation found."

    parts = []
    for i, chunk in enumerate(chunks, 1):
        source = f"[{chunk['doc_title']}] {chunk['heading_path']}"
        if chunk.get("device_name"):
            source += f" (Device: {chunk['device_name']}"
            if chunk.get("firmware_version"):
                source += f", FW: {chunk['firmware_version']}"
            source += ")"
        parts.append(f"--- Source {i}: {source} (similarity: {chunk['similarity']}) ---\n{chunk['content']}")

    return "\n\n".join(parts)


def _build_history_messages(history: list[ChatMessage], max_messages: int) -> list[dict]:
    """Convert DB message history to Ollama message format."""
    recent = history[-max_messages:] if len(history) > max_messages else history
    return [{"role": msg.role, "content": msg.content} for msg in recent]


async def build_rag_prompt(
    db: AsyncSession,
    query: str,
    history: list[ChatMessage] | None = None,
    device_filter: str | None = None,
    version_filter: str | None = None,
) -> tuple[list[dict], list[dict]]:
    """Build a complete prompt with RAG context for the LLM.

    Returns:
        Tuple of (messages for Ollama, source chunks for the client).
    """
    t0 = time.perf_counter()

    t_search = time.perf_counter()
    chunks = await search_documents(
        session=db,
        query=query,
        device=device_filter,
        version=version_filter,
        limit=settings.rag_top_k,
    )
    search_ms = round((time.perf_counter() - t_search) * 1000, 1)

    context = _format_context(chunks)
    context_tokens = sum(c.get("token_count", 0) for c in chunks)

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": f"Documentation context:\n\n{context}"},
    ]

    if history:
        messages.extend(_build_history_messages(history, settings.rag_history_messages))

    messages.append({"role": "user", "content": query})

    sources = [
        {
            "doc_title": c["doc_title"],
            "heading_path": c["heading_path"],
            "similarity": c["similarity"],
            "content_preview": c["content"][:200],
            "device_name": c.get("device_name", ""),
            "firmware_version": c.get("firmware_version", ""),
        }
        for c in chunks
    ]

    total_ms = round((time.perf_counter() - t0) * 1000, 1)

    logger.info(
        "RAG prompt built",
        extra={
            "query": query[:100],
            "chunks_found": len(chunks),
            "top_similarity": chunks[0]["similarity"] if chunks else 0,
            "history_messages": len(history) if history else 0,
            "device_filter": device_filter,
            "context_tokens": context_tokens,
            "search_ms": search_ms,
            "rag_build_ms": total_ms,
            "prompt_messages": len(messages),
        },
    )

    return messages, sources
