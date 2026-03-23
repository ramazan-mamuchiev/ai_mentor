"""RAG (Retrieval Augmented Generation) service for chat."""

import hashlib
import logging
import re
import time
from pathlib import Path

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.ingestion.text_cleaner import clean_for_embedding as _clean_md
from app.models import ChatMessage
from app.search.service import search_documents

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"

QUERY_TYPES = ("overview", "technical", "code", "comparison", "troubleshooting", "chitchat")


def _load_prompt_file(name: str) -> str:
    path = _PROMPTS_DIR / f"{name}.md"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    logger.warning("Prompt file not found: %s", path)
    return ""


_BASE_PROMPT = _load_prompt_file("base")
_TYPE_PROMPTS: dict[str, str] = {qt: _load_prompt_file(qt) for qt in QUERY_TYPES}


def _build_system_prompt(query_type: str) -> str:
    type_block = _TYPE_PROMPTS.get(query_type, "")
    if type_block:
        return f"{_BASE_PROMPT}\n\n{type_block}"
    return _BASE_PROMPT


def _embedding_model_name() -> str:
    return settings.embedding_model_gemini


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

_CLASSIFY_PROMPT = """\
Classify the user question into exactly ONE category. Return ONLY the category name, nothing else.

Categories:
- overview: general question about a product, system, or technology ("what is X", "tell me about X", "describe X", "расскажи про X")
- technical: specific API/protocol/configuration question ("how to get cameras list", "what endpoint for events", "какой формат ответа")
- code: request to write or generate code ("write Python example", "show curl command", "напиши пример на Go")
- comparison: comparing products, versions, or features ("difference between v1 and v2", "чем отличается X от Y")
- troubleshooting: error, problem, or debugging question ("why 403 error", "connection refused", "не работает авторизация")
- chitchat: greeting, off-topic, or meta-question ("hello", "what can you do", "привет")

Question: {query}
Category:"""


async def _classify_query(query: str) -> tuple[str, dict]:
    """Classify user query into a query type using a lightweight LLM call.

    Returns (query_type, usage_meta) where usage_meta contains token counts.
    """
    if not settings.classifier_enabled:
        return "overview", {}

    prompt = _CLASSIFY_PROMPT.format(query=query)
    messages = [{"role": "user", "content": prompt}]

    try:
        t0 = time.perf_counter()
        url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": settings.classifier_model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": 20,
            "reasoning_effort": "none",
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.gemini_api_key}",
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        classify_ms = round((time.perf_counter() - t0) * 1000, 1)

        raw = data["choices"][0]["message"]["content"].strip().lower()
        usage = data.get("usage", {})

        query_type = raw if raw in QUERY_TYPES else "overview"

        meta = {
            "classify_model": settings.classifier_model,
            "classify_ms": classify_ms,
            "classify_prompt_tokens": usage.get("prompt_tokens", 0),
            "classify_completion_tokens": usage.get("completion_tokens", 0),
            "classify_total_tokens": usage.get("total_tokens", 0),
            "query_type": query_type,
            "classify_raw": raw,
        }

        logger.info(
            "Query classified",
            extra={"query": query[:100], "query_type": query_type, "raw": raw, "ms": classify_ms},
        )
        return query_type, meta

    except Exception:
        logger.warning("Query classification failed, defaulting to overview", exc_info=True)
        return "overview", {"query_type": "overview", "classify_model": settings.classifier_model}


async def _has_any_documents(db: AsyncSession) -> bool:
    """Check whether the knowledge base has at least one ready document."""
    result = await db.execute(
        text("SELECT EXISTS(SELECT 1 FROM documents WHERE status = 'ready' LIMIT 1)")
    )
    return bool(result.scalar())


async def _detect_product_from_query(db: AsyncSession, query: str) -> str | None:
    """Match product/manufacturer names mentioned in the user query against the products table.

    Returns the product name if found, or None.
    Uses word-boundary matching and prioritises longer names to avoid
    false positives (e.g. a single-letter product name matching inside
    an unrelated word).
    """
    result = await db.execute(
        text("SELECT name, manufacturer FROM products WHERE name != 'TestDevice'")
    )
    products = result.mappings().all()

    query_lower = query.lower()

    def _word_boundary_match(keyword: str) -> bool:
        """Check if *keyword* appears in query as a whole word (not inside another word)."""
        escaped = re.escape(keyword.lower())
        return bool(re.search(rf"(?<!\w){escaped}(?!\w)", query_lower))

    # Pass 1: exact full-name / manufacturer match (longer names first).
    sorted_products = sorted(products, key=lambda p: len(p["name"] or ""), reverse=True)
    for prod in sorted_products:
        name = prod["name"] or ""
        manufacturer = prod["manufacturer"] or ""
        for keyword in [name, manufacturer]:
            if keyword and _word_boundary_match(keyword):
                return name

    # Pass 2: individual words from the product name (≥4 chars).
    for prod in sorted_products:
        name = prod["name"] or ""
        for word in name.split():
            if len(word) >= 4 and _word_boundary_match(word):
                return name

    return None


def _format_context(chunks: list[dict], *, no_documents_at_all: bool = False) -> str:
    """Format retrieved chunks into a context string for the LLM.

    Uses parent_content (full section) when available for richer context,
    falling back to the chunk content itself.  Deduplicates parent_content
    when multiple child chunks from the same section are retrieved.
    """
    if no_documents_at_all:
        return "The knowledge base is completely empty — no documents have been uploaded yet."
    if not chunks:
        return "No relevant documentation found for this query."

    seen_parents: set[str] = set()
    parts = []
    for i, chunk in enumerate(chunks, 1):
        source = f"[{chunk['doc_title']}] {chunk['heading_path']}"
        if chunk.get("product_name"):
            source += f" (Product: {chunk['product_name']}"
            if chunk.get("firmware_version"):
                source += f", FW: {chunk['firmware_version']}"
            source += ")"

        parent = chunk.get("parent_content")
        if parent:
            parent_key = hashlib.sha256(parent.encode("utf-8")).hexdigest()
            if parent_key in seen_parents:
                continue
            seen_parents.add(parent_key)
            body = _clean_md(parent)
        else:
            body = _clean_md(chunk["content"])

        parts.append(f"--- Source {i}: {source} (similarity: {chunk['similarity']}) ---\n{body}")

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
        "Authorization": f"Bearer {settings.gemini_api_key}",
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
            "embedding_model": _embedding_model_name(),
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

    auto_product = await _detect_product_from_query(db, query)
    if auto_product and auto_product != product_filter:
        logger.info(
            "Auto-detected product from query (overriding session filter)",
            extra={"product": auto_product, "previous": product_filter, "query": query[:100]},
        )
        product_filter = auto_product

    t_rewrite = time.perf_counter()
    search_query = await _rewrite_query(query, history) if history else query
    rewrite_ms = round((time.perf_counter() - t_rewrite) * 1000, 1)

    t_search = time.perf_counter()
    search_meta: dict = {}
    chunks = await search_documents(
        session=db,
        query=search_query,
        product=product_filter,
        version=version_filter,
        doc_context=doc_context,
        limit=settings.rag_top_k,
        metadata=search_meta,
    )
    search_ms = round((time.perf_counter() - t_search) * 1000, 1)

    all_chunks_before_filter = chunks
    if settings.rag_min_similarity > 0:
        chunks = [c for c in chunks if c["similarity"] >= settings.rag_min_similarity]

    if not chunks and all_chunks_before_filter and (product_filter or auto_product):
        chunks = all_chunks_before_filter[:settings.rag_top_k]
        logger.info(
            "Similarity fallback: product detected but all chunks below threshold, "
            "returning top chunks without threshold",
            extra={
                "product": product_filter or auto_product,
                "original_threshold": settings.rag_min_similarity,
                "chunks_recovered": len(chunks),
                "top_similarity": chunks[0]["similarity"] if chunks else 0,
            },
        )

    detected_product = auto_product or product_filter
    detected_doc = doc_context
    if not doc_context and chunks:
        titles = set(c["doc_title"] for c in chunks)
        if len(titles) == 1:
            detected_doc = next(iter(titles))

    context = _format_context(chunks)
    context_tokens = _estimate_tokens(context)

    context_header = "<documentation_context>\n"
    if detected_product:
        context_header += f"Product: {detected_product}\n\n"
    context_block = f"{context_header}{context}\n</documentation_context>"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": context_block},
        {"role": "assistant", "content": "Understood. I will use the documentation context above to answer questions. If the sources contain relevant information, I will summarize it."},
    ]

    if history:
        messages.extend(_build_history_messages(
            history, settings.rag_history_messages, settings.rag_history_max_tokens,
        ))

    if chunks:
        hint = (
            f"Note: {len(chunks)} relevant source chunks were found in the documentation. "
            "Use them to answer the question.\n\n"
        )
    else:
        hint = ""
    messages.append({"role": "user", "content": f"{hint}Based on the documentation above, answer the following question:\n\n{query}"})

    sources = [
        {
            "document_id": c.get("document_id"),
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
        "embedding_model": _embedding_model_name(),
        "product_filter": product_filter,
        "version_filter": version_filter,
        "doc_context": doc_context,
        "auto_product": auto_product,
        "detected_doc_context": detected_doc,
        "search_query": search_query,
        "no_documents": False,
        "rerank_prompt_tokens": search_meta.get("rerank_prompt_tokens", 0),
        "rerank_completion_tokens": search_meta.get("rerank_completion_tokens", 0),
        "rerank_total_tokens": search_meta.get("rerank_total_tokens", 0),
        "rerank_model": search_meta.get("rerank_model", ""),
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
