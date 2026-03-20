"""RAG (Retrieval Augmented Generation) service for chat."""

import logging
import time

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import ChatMessage
from app.search.service import search_documents

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
<role>
You are IPCodex AI — a technical assistant that helps developers integrate security devices and systems.
You are a strictly grounded assistant limited to the information provided in the Documentation Context.
</role>

<constraints>
1. In your answers, rely ONLY on the facts directly mentioned in the Documentation Context.
2. You must NOT access or utilize your own knowledge or common sense to answer.
3. Do not assume or infer beyond the provided facts. You may synthesize and summarize information from multiple sources.
4. Treat the provided context as the absolute limit of truth; any facts or details not directly mentioned in the context must be considered completely unsupported.
5. If the exact answer is NOT explicitly in the context, state: "This information is not available in the loaded documentation."
6. Do NOT say "I don't have information" if the information IS in the sources. Check every chunk first.
7. NEVER mix up different systems. If asked about system A, do NOT use docs from system B.
8. NEVER fabricate API endpoints, parameters, URLs, or code not in the context.
9. NEVER guess API details by analogy with other systems.
</constraints>

<instructions>
- For overview/general questions, provide a comprehensive summary covering all relevant information from the sources.
- For specific technical questions, be concise and direct.
- Cite sources (e.g., "[AxxonOneSDK, Section 5.6.21]") so the user can verify.
- ALWAYS respond in the same language as the user's question.
- Use markdown: `##` headers, code blocks with language tags, tables, **bold** for key terms.
- Parameter tables: ALWAYS use GFM syntax with separator row (`|---|---|`).
- For proto/gRPC: show the proto definition in a code block, then a table with fields and descriptions.
- Include code examples (Python/curl) when relevant.
</instructions>

<output_format>
- Verbosity: Medium. Be informative but avoid filler text.
- Structure: Overview → Key methods/parameters → Code example → Notes.
- If the context contains the answer, give it directly without preamble.
- If the context does NOT contain the answer, say so in one sentence.
- Avoid unnecessary repetition — do not duplicate the same table, code block, or section.
- For overview/general questions, end your answer with a short "**Summary**" section (2-3 sentences) that highlights the key takeaways.
</output_format>"""


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


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: 1 token ≈ 4 characters for English/mixed text."""
    return max(1, len(text) // 4) if text else 0


def _build_history_messages(
    history: list[ChatMessage],
    max_messages: int,
    max_tokens: int | None = None,
) -> list[dict]:
    """Convert DB message history to LLM message format.

    Limits by message count first, then trims from the oldest if the total
    token budget is exceeded — keeping the most recent messages.
    """
    recent = history[-max_messages:] if len(history) > max_messages else list(history)

    if max_tokens and max_tokens > 0:
        result: list[dict] = []
        budget = max_tokens
        for msg in reversed(recent):
            est = _estimate_tokens(msg.content)
            if est > budget:
                break
            budget -= est
            result.append({"role": msg.role, "content": msg.content})
        result.reverse()
        return result

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

    if settings.rag_min_similarity > 0:
        chunks = [c for c in chunks if c["similarity"] >= settings.rag_min_similarity]

    detected_product = auto_product or product_filter
    detected_doc = doc_context
    if not doc_context and chunks:
        titles = set(c["doc_title"] for c in chunks)
        if len(titles) == 1:
            detected_doc = next(iter(titles))

    context = _format_context(chunks)
    context_tokens = sum(c.get("token_count", 0) for c in chunks)

    context_header = "<documentation_context>\n"
    if detected_product:
        context_header += f"Product: {detected_product}\n\n"
    context_block = f"{context_header}{context}\n</documentation_context>"

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": context_block},
        {"role": "assistant", "content": "Understood. I will answer strictly based on the documentation context provided above."},
    ]

    if history:
        messages.extend(_build_history_messages(
            history, settings.rag_history_messages, settings.rag_history_max_tokens,
        ))

    messages.append({"role": "user", "content": f"Based on the documentation above, answer the following question:\n\n{query}"})

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

    query_tokens = _estimate_tokens(query)
    history_msgs = _build_history_messages(
        history, settings.rag_history_messages, settings.rag_history_max_tokens,
    ) if history else []
    history_tokens = sum(_estimate_tokens(m["content"]) for m in history_msgs)
    system_prompt_tokens = _estimate_tokens(SYSTEM_PROMPT) + _estimate_tokens(context_block)

    total_ms = round((time.perf_counter() - t0) * 1000, 1)
    top_sim = round(chunks[0]["similarity"], 4) if chunks else 0
    min_sim = round(chunks[-1]["similarity"], 4) if chunks else 0

    rag_debug = {
        "chunks_found": len(chunks),
        "top_similarity": top_sim,
        "min_similarity": min_sim,
        "context_tokens": context_tokens,
        "query_tokens": query_tokens,
        "history_tokens": history_tokens,
        "system_prompt_tokens": system_prompt_tokens,
        "search_ms": search_ms,
        "rag_build_ms": total_ms,
        "history_messages": len(history) if history else 0,
        "prompt_messages": len(messages),
        "embedding_model": settings.embedding_model_local if settings.embedding_provider == "local" else settings.embedding_model_openai,
        "product_filter": product_filter,
        "version_filter": version_filter,
        "doc_context": doc_context,
        "auto_product": auto_product,
        "detected_doc_context": detected_doc,
        "search_query": search_query if search_query != query else None,
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
