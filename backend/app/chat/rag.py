"""RAG (Retrieval Augmented Generation) service for chat."""

import logging
import time

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import ChatMessage
from app.search.service import search_documents

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are IPCodex AI — a technical assistant that helps developers integrate security devices and systems.

Your primary goal is to provide ACTIONABLE, CODE-READY answers based on the documentation context provided below.

## CRITICAL: How to answer

1. **Your answer MUST be based on the "Documentation context" section below.** Read ALL the source chunks carefully. If any chunk contains information relevant to the user's question — USE IT in your answer.
2. **Do NOT say "I don't have information" if the information IS present in the sources below.** Search through every source chunk for relevant functions, APIs, parameters, and details before concluding that information is missing.
3. **Cite your sources** (e.g., "[Honeywell IPM SDK, Section 4.2.8]") so the user can verify.

## Anti-hallucination rules

4. **NEVER mix up different systems.** If the user asks about system A, do NOT answer using documentation from system B.
5. **NEVER fabricate API endpoints, parameters, URLs, or code not present in the context.**
6. **NEVER guess API details by analogy with other systems.**
7. **Only say "I don't have documentation about [X]" if you have carefully checked ALL source chunks below and NONE of them contain relevant information.**

## Response format

8. Include working code examples (Python with `requests`/`httpx`, or `curl`) when relevant.
9. Show API endpoints with full URLs, HTTP methods, headers, and request/response bodies from the documentation.
10. Structure: **Overview** → **Step-by-step** → **Code example** → **Notes**.
11. Include API specs, auth details, code samples, headers, and parameter tables verbatim. Do NOT skip details.
12. ALWAYS respond in the same language as the user's question.
13. Use rich markdown: `##` headers, code blocks with language tags, tables, **bold** for key terms."""


async def _detect_product_from_query(db: AsyncSession, query: str) -> str | None:
    """Match product/manufacturer names mentioned in the user query against the products table.

    Returns the product name if found, or None.
    """
    result = await db.execute(
        text("SELECT name, manufacturer FROM products WHERE name != 'TestDevice'")
    )
    products = result.mappings().all()

    query_lower = query.lower()
    for prod in products:
        name = prod["name"] or ""
        manufacturer = prod["manufacturer"] or ""
        for keyword in [name, manufacturer]:
            if keyword and keyword.lower() in query_lower:
                return name
        for word in name.split():
            if len(word) >= 4 and word.lower() in query_lower:
                return name
    return None


def _format_context(chunks: list[dict]) -> str:
    """Format retrieved chunks into a context string for the LLM."""
    if not chunks:
        return "No relevant documentation found."

    parts = []
    for i, chunk in enumerate(chunks, 1):
        source = f"[{chunk['doc_title']}] {chunk['heading_path']}"
        if chunk.get("product_name"):
            source += f" (Product: {chunk['product_name']}"
            if chunk.get("firmware_version"):
                source += f", FW: {chunk['firmware_version']}"
            source += ")"
        parts.append(f"--- Source {i}: {source} (similarity: {chunk['similarity']}) ---\n{chunk['content']}")

    return "\n\n".join(parts)


def _build_history_messages(history: list[ChatMessage], max_messages: int) -> list[dict]:
    """Convert DB message history to Ollama message format."""
    recent = history[-max_messages:] if len(history) > max_messages else history
    return [{"role": msg.role, "content": msg.content} for msg in recent]


def _enrich_query(query: str, history: list[ChatMessage] | None) -> str:
    """Enrich a short follow-up query with context from recent user messages."""
    if not history or len(query) > 200:
        return query

    recent_user_msgs = [m.content for m in history if m.role == "user"][-3:]
    if not recent_user_msgs:
        return query

    context_words: list[str] = []
    for msg in recent_user_msgs:
        words = msg.split()[:10]
        context_words.extend(words)

    if not context_words:
        return query

    context_prefix = " ".join(dict.fromkeys(context_words))
    return f"{context_prefix} {query}"


async def build_rag_prompt(
    db: AsyncSession,
    query: str,
    history: list[ChatMessage] | None = None,
    product_filter: str | None = None,
    version_filter: str | None = None,
    doc_context: str | None = None,
) -> tuple[list[dict], list[dict], dict]:
    """Build a complete prompt with RAG context for the LLM.

    Returns:
        Tuple of (messages for LLM, source chunks for the client, rag_debug dict).
    """
    t0 = time.perf_counter()

    auto_product = None
    if not product_filter and not doc_context:
        auto_product = await _detect_product_from_query(db, query)
        if auto_product:
            product_filter = auto_product
            logger.info("Auto-detected product from query", extra={"product": auto_product, "query": query[:100]})

    search_query = _enrich_query(query, history) if history else query

    t_search = time.perf_counter()
    chunks = await search_documents(
        session=db,
        query=search_query,
        product=product_filter,
        version=version_filter,
        doc_context=doc_context,
        limit=settings.rag_top_k,
    )
    search_ms = round((time.perf_counter() - t_search) * 1000, 1)

    detected_product = auto_product or product_filter
    detected_doc = doc_context
    if not doc_context and chunks:
        titles = set(c["doc_title"] for c in chunks)
        if len(titles) == 1:
            detected_doc = next(iter(titles))

    context = _format_context(chunks)
    context_tokens = sum(c.get("token_count", 0) for c in chunks)

    context_header = "## Documentation context\n\n"
    if detected_product:
        context_header += f"Product: **{detected_product}**\n\n"
    combined_system = f"{SYSTEM_PROMPT}\n\n---\n\n{context_header}{context}"
    messages: list[dict] = [
        {"role": "system", "content": combined_system},
    ]

    if history:
        messages.extend(_build_history_messages(history, settings.rag_history_messages))

    messages.append({"role": "user", "content": query})

    sources = [
        {
            "doc_title": c["doc_title"],
            "heading_path": c["heading_path"],
            "similarity": c["similarity"],
            "content_preview": c["content"][:500],
            "product_name": c.get("product_name", ""),
            "firmware_version": c.get("firmware_version", ""),
        }
        for c in chunks
    ]

    total_ms = round((time.perf_counter() - t0) * 1000, 1)
    top_sim = round(chunks[0]["similarity"], 4) if chunks else 0
    min_sim = round(chunks[-1]["similarity"], 4) if chunks else 0

    rag_debug = {
        "chunks_found": len(chunks),
        "top_similarity": top_sim,
        "min_similarity": min_sim,
        "context_tokens": context_tokens,
        "search_ms": search_ms,
        "rag_build_ms": total_ms,
        "history_messages": len(history) if history else 0,
        "prompt_messages": len(messages),
        "embedding_model": settings.embedding_model_local if settings.embedding_provider == "local" else settings.embedding_model_openai,
        "doc_context": doc_context,
        "auto_product": auto_product,
        "detected_doc_context": detected_doc,
    }

    logger.info(
        "RAG prompt built",
        extra={
            "query": query[:100],
            "search_query": search_query[:200] if search_query != query else None,
            "product_filter": product_filter,
            **rag_debug,
        },
    )

    return messages, sources, rag_debug
