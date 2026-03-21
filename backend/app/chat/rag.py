"""RAG (Retrieval Augmented Generation) service for chat."""

import logging
import time

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import ChatMessage
from app.search.service import search_documents

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_NO_DOCS = """\
<role>
You are IPCodex AI — a technical assistant that helps developers integrate security devices and systems.
</role>

<situation>
The knowledge base is currently EMPTY — no documentation has been uploaded yet.
</situation>

<instructions>
- CRITICAL: ALWAYS respond in the same language as the user's question. If the user writes in Russian, your ENTIRE response must be in Russian. If in English — respond in English.
- Politely explain that the knowledge base is empty and no documents have been uploaded yet.
- You may briefly describe what IPCodex can do once documentation is loaded: semantic search across documentation, answering technical questions about APIs and protocols, generating code examples based on documentation.
- Do NOT suggest the user to upload documents or give instructions on how to do it.
- Do NOT make up any technical details about specific products or APIs.
- Keep the response concise and helpful.
</instructions>"""

SYSTEM_PROMPT = """\
<role>
You are IPCodex AI — a technical assistant that helps developers integrate security devices and systems.
You are a strictly grounded assistant limited to the information provided in the Documentation Context.
</role>

<constraints>
1. In your answers, rely ONLY on the facts directly mentioned in the Documentation Context.
2. You must NOT access or utilize your own knowledge for FACTS (endpoints, parameters, URLs, protocols). You MAY use general programming knowledge to write code examples that use the APIs described in the context.
3. Do not assume or infer beyond the provided facts. You may synthesize and summarize information from multiple sources.
4. Treat the provided context as the absolute limit of truth for API details; any endpoints, parameters, or URLs not in the context must be considered unsupported.
5. If the context contains NO relevant information at all, say so briefly in the user's language.
6. Do NOT say "I don't have information" if the information IS in the sources. Check every chunk first.
7. NEVER mix up different systems. If asked about system A, do NOT use docs from system B.
8. NEVER fabricate API endpoints, parameters, or URLs not in the context. You MAY generate code examples in any programming language using the API details from the context.
9. NEVER guess API details by analogy with other systems.
</constraints>

<instructions>
- CRITICAL: ALWAYS respond in the same language as the user's question. If the user writes in Russian, your ENTIRE response must be in Russian. If in English — respond in English.
- For overview/general questions, provide a comprehensive summary covering all relevant information from the sources.
- For specific technical questions, be concise and direct.
- Cite sources (e.g., "[AxxonOneSDK, Section 5.6.21]") so the user can verify.
- Use markdown: `##` headers, code blocks with language tags, tables, **bold** for key terms.
- Parameter tables: ALWAYS use GFM syntax with separator row (`|---|---|`).
- For proto/gRPC: show the proto definition in a code block, then a table with fields and descriptions.
- IMPORTANT: When the user asks for a code example in ANY programming language (Go, Python, Java, C#, curl, etc.), you MUST generate it. Use the API details (endpoints, methods, parameters, JSON structures) from the context as the basis. Apply your general programming knowledge for language syntax, HTTP clients, and boilerplate. If no language is specified, use Python or curl.
- Code examples must use real endpoints and parameters from the documentation — never invent API details, but DO write the surrounding code.
</instructions>

<output_format>
- Verbosity: Medium. Be informative but avoid filler text.
- Structure: Overview → Key methods/parameters → Code example → Notes.
- If the context contains the answer, give it directly without preamble.
- If the context does NOT contain the answer, say so in one sentence.
- Avoid unnecessary repetition — do not duplicate the same table, code block, or section.
- For overview/general questions, end your answer with a short summary section (2-3 sentences) that highlights the key takeaways. The section header must be in the same language as the rest of the answer.
</output_format>"""


async def _has_any_documents(db: AsyncSession) -> bool:
    """Check whether the knowledge base has at least one ready document."""
    result = await db.execute(
        text("SELECT EXISTS(SELECT 1 FROM documents WHERE status = 'ready' LIMIT 1)")
    )
    return bool(result.scalar())


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


def _format_context(chunks: list[dict], *, no_documents_at_all: bool = False) -> str:
    """Format retrieved chunks into a context string for the LLM."""
    if no_documents_at_all:
        return "The knowledge base is completely empty — no documents have been uploaded yet."
    if not chunks:
        return "No relevant documentation found for this query."

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


_REWRITE_PROMPT = (
    "Given the conversation history and a new user question, "
    "rewrite the question so it is fully self-contained and can be understood "
    "without the conversation history. "
    "If the question is already self-contained, return it unchanged. "
    "Return ONLY the rewritten question, nothing else."
)


async def _rewrite_query(query: str, history: list[ChatMessage] | None) -> str:
    """Use LLM to rewrite a follow-up query into a standalone question.

    Falls back to the original query on any error or if there is no history.
    """
    if not history:
        return query

    recent = [m for m in history if m.role == "user"][-3:]
    if not recent:
        return query

    messages = [{"role": "system", "content": _REWRITE_PROMPT}]
    for msg in recent:
        messages.append({"role": "user", "content": msg.content})
    messages.append({"role": "user", "content": f"New question: {query}"})

    try:
        if settings.llm_provider == "openai":
            result = await _llm_rewrite_openai(messages)
        else:
            result = await _llm_rewrite_ollama(messages)
        if result and len(result) < 500:
            logger.info("Query rewritten", extra={"original": query[:100], "rewritten": result[:200]})
            return result
    except Exception:
        logger.warning("Query rewrite failed, using original", exc_info=True)

    return query


async def _llm_rewrite_openai(messages: list[dict]) -> str:
    url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": settings.openai_llm_model,
        "messages": messages,
        "temperature": 0,
        "max_tokens": 256,
        "reasoning_effort": "none",
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.openai_llm_api_key}",
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0)) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()


async def _llm_rewrite_ollama(messages: list[dict]) -> str:
    url = f"{settings.ollama_url}/api/chat"
    payload = {
        "model": settings.llm_model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0, "num_predict": 256},
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0)) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["message"]["content"].strip()


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

    has_docs = await _has_any_documents(db)

    if not has_docs:
        query_tokens = _estimate_tokens(query)
        system_prompt_tokens = _estimate_tokens(SYSTEM_PROMPT_NO_DOCS)

        messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT_NO_DOCS},
        ]
        if history:
            messages.extend(_build_history_messages(
                history, settings.rag_history_messages, settings.rag_history_max_tokens,
            ))
        messages.append({"role": "user", "content": query})

        history_msgs = _build_history_messages(
            history, settings.rag_history_messages, settings.rag_history_max_tokens,
        ) if history else []
        history_tokens = sum(_estimate_tokens(m["content"]) for m in history_msgs)

        total_ms = round((time.perf_counter() - t0) * 1000, 1)
        rag_debug = {
            "chunks_found": 0,
            "top_similarity": 0,
            "min_similarity": 0,
            "context_tokens": 0,
            "query_tokens": query_tokens,
            "history_tokens": history_tokens,
            "system_prompt_tokens": system_prompt_tokens,
            "rewrite_ms": 0,
            "search_ms": 0,
            "rag_build_ms": total_ms,
            "history_messages": len(history) if history else 0,
            "prompt_messages": len(messages),
            "embedding_model": settings.embedding_model_local if settings.embedding_provider == "local" else settings.embedding_model_openai,
            "product_filter": product_filter,
            "version_filter": version_filter,
            "doc_context": doc_context,
            "auto_product": None,
            "detected_doc_context": None,
            "search_query": query,
            "no_documents": True,
        }

        logger.info(
            "RAG prompt built (no documents in system)",
            extra={"query": query[:100], **rag_debug},
        )

        return messages, [], rag_debug

    auto_product = None
    if not product_filter and not doc_context:
        auto_product = await _detect_product_from_query(db, query)
        if auto_product:
            product_filter = auto_product
            logger.info("Auto-detected product from query", extra={"product": auto_product, "query": query[:100]})

    t_rewrite = time.perf_counter()
    search_query = await _rewrite_query(query, history) if history else query
    rewrite_ms = round((time.perf_counter() - t_rewrite) * 1000, 1)

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

    messages = [
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
        "rewrite_ms": rewrite_ms if history else 0,
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
        "no_documents": False,
    }

    logger.info(
        "RAG prompt built",
        extra={
            "query": query[:100],
            "search_query": search_query[:200] if search_query != query else None,
            "rewrite_ms": rewrite_ms if history else 0,
            "product_filter": product_filter,
            **rag_debug,
        },
    )

    return messages, sources, rag_debug
