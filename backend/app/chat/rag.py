"""RAG (Retrieval Augmented Generation) service for chat."""

import hashlib
import json as json_lib
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

_TAG_RE = re.compile(r"<(\w+)>(.*?)</\1>", re.DOTALL)


def _load_prompts() -> tuple[str, dict[str, str], dict[str, str], dict[str, int]]:
    """Scan prompts/ directory and build prompt registry.

    Returns (base_prompt, type_prompts, classifier_hints, type_max_tokens) where:
    - base_prompt: contents of base.md
    - type_prompts: {query_type: full file content} for each type .md
    - classifier_hints: {query_type: hint text} for building the classify prompt
    - type_max_tokens: {query_type: max_tokens} from <max_response_tokens> tags
    """
    base_path = _PROMPTS_DIR / "base.md"
    base = base_path.read_text(encoding="utf-8").strip() if base_path.exists() else ""

    type_prompts: dict[str, str] = {}
    hints: dict[str, str] = {}
    max_tokens_map: dict[str, int] = {}

    for md_file in sorted(_PROMPTS_DIR.glob("*.md")):
        if md_file.stem in ("base", "README"):
            continue
        content = md_file.read_text(encoding="utf-8").strip()
        tags = {m.group(1): m.group(2).strip() for m in _TAG_RE.finditer(content)}

        qtype = tags.get("task_type", md_file.stem)
        type_prompts[qtype] = content
        if "classifier_hint" in tags:
            hints[qtype] = tags["classifier_hint"]
        else:
            logger.warning("Prompt %s has no <classifier_hint>, using filename as hint", md_file.name)
            hints[qtype] = qtype

        if "max_response_tokens" in tags:
            try:
                max_tokens_map[qtype] = int(tags["max_response_tokens"])
            except ValueError:
                logger.warning("Invalid <max_response_tokens> in %s: %s", md_file.name, tags["max_response_tokens"])

    logger.info(
        "Loaded %d prompt types: %s (max_tokens: %s)",
        len(type_prompts), ", ".join(sorted(type_prompts)),
        {k: v for k, v in sorted(max_tokens_map.items())},
    )
    return base, type_prompts, hints, max_tokens_map


_BASE_PROMPT, _TYPE_PROMPTS, _CLASSIFIER_HINTS, _TYPE_MAX_TOKENS = _load_prompts()
QUERY_TYPES = tuple(_TYPE_PROMPTS.keys())


def _build_classify_prompt() -> str:
    lines = [
        "Classify the user question and detect the product mentioned.",
        "Return ONLY a JSON object with two fields, no other text:",
        '  {{"category": "<category>", "product": "<exact_product_name or null>"}}',
        "",
        "Rules for product field:",
        "- Copy the product name EXACTLY as written in the list below (preserve spelling, spacing, capitalization).",
        "- If the user mentions a product by any variation (abbreviation, translation, misspelling), map it to the EXACT name from the list.",
        "- If no product is mentioned or cannot be determined, return null.",
        "",
        "Categories:",
    ]
    for qtype, hint in _CLASSIFIER_HINTS.items():
        lines.append(f"- {qtype}: {hint}")
    lines.append("")
    lines.append("Available products (use EXACTLY these names in the response):")
    lines.append("{products}")
    lines.append("")
    lines.append("Question: {query}")
    return "\n".join(lines)


_CLASSIFY_PROMPT_TEMPLATE = _build_classify_prompt()


async def _load_product_names(db: AsyncSession) -> list[str]:
    """Load product names from the database for classify prompt."""
    result = await db.execute(
        text("SELECT name FROM products WHERE name != 'TestDevice' ORDER BY name")
    )
    return [row[0] for row in result.fetchall()]


def _build_system_prompt(query_type: str) -> str:
    type_block = _TYPE_PROMPTS.get(query_type, "")
    if type_block:
        return f"{_BASE_PROMPT}\n\n{type_block}"
    return _BASE_PROMPT


def _embedding_model_name() -> str:
    return settings.embedding_model_gemini


from app.chat.prompts import REWRITE_PROMPT as _REWRITE_PROMPT_IMPORTED
from app.chat.prompts import REPHRASE_FOR_SEARCH_PROMPT, SYSTEM_PROMPT_NO_DOCS

async def _classify_query(db: AsyncSession, query: str) -> tuple[str, str | None, dict]:
    """Classify user query and detect product using a single LLM call.

    Returns (query_type, detected_product, usage_meta).
    """
    if not settings.classifier_enabled:
        return "overview", None, {}

    product_names = await _load_product_names(db)
    products_str = ", ".join(product_names) if product_names else "(no products in database)"

    prompt = _CLASSIFY_PROMPT_TEMPLATE.format(query=query, products=products_str)
    messages = [{"role": "user", "content": prompt}]

    try:
        t0 = time.perf_counter()
        url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": settings.classifier_model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": 60,
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

        raw = data["choices"][0]["message"]["content"].strip()
        usage = data.get("usage", {})

        query_type = "overview"
        detected_product: str | None = None

        try:
            clean = raw
            if clean.startswith("```"):
                clean = "\n".join(clean.split("\n")[1:])
                if clean.endswith("```"):
                    clean = clean[:-3]
            parsed = json_lib.loads(clean)
            if isinstance(parsed, dict):
                cat = (parsed.get("category") or "").strip().lower()
                query_type = cat if cat in QUERY_TYPES else "overview"
                prod = parsed.get("product")
                if prod and isinstance(prod, str) and prod.lower() != "null":
                    if prod in product_names:
                        detected_product = prod
                    else:
                        for pn in product_names:
                            if pn.lower() == prod.lower():
                                detected_product = pn
                                break
        except (json_lib.JSONDecodeError, KeyError):
            raw_lower = raw.lower().strip()
            query_type = raw_lower if raw_lower in QUERY_TYPES else "overview"

        meta = {
            "classify_model": settings.classifier_model,
            "classify_ms": classify_ms,
            "classify_prompt_tokens": usage.get("prompt_tokens", 0),
            "classify_completion_tokens": usage.get("completion_tokens", 0),
            "classify_total_tokens": usage.get("total_tokens", 0),
            "query_type": query_type,
            "classify_product": detected_product,
            "classify_raw": raw,
        }

        logger.info(
            "Query classified",
            extra={
                "query": query[:100],
                "query_type": query_type,
                "detected_product": detected_product,
                "raw": raw,
                "ms": classify_ms,
            },
        )
        return query_type, detected_product, meta

    except Exception:
        logger.warning("Query classification failed, defaulting to overview", exc_info=True)
        return "overview", None, {"query_type": "overview", "classify_model": settings.classifier_model}


async def _has_any_documents(db: AsyncSession) -> bool:
    """Check whether the knowledge base has at least one ready document."""
    result = await db.execute(
        text("SELECT EXISTS(SELECT 1 FROM documents WHERE status = 'ready' LIMIT 1)")
    )
    return bool(result.scalar())




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

        doc_type = chunk.get("doc_type", "other")
        if doc_type and doc_type != "other":
            source += f" [type: {doc_type}]"

        parent = chunk.get("parent_content")
        if parent:
            parent_key = hashlib.sha256(parent.encode("utf-8")).hexdigest()
            if parent_key in seen_parents:
                continue
            seen_parents.add(parent_key)
            body = _clean_md(parent)
        else:
            body = _clean_md(chunk["content"])

        entities = chunk.get("entities", {})
        entity_line = ""
        if entities:
            flat = []
            for vals in entities.values():
                if isinstance(vals, list):
                    flat.extend(str(v) for v in vals if v)
            if flat:
                entity_line = f"Entities: {', '.join(flat[:15])}\n"

        parts.append(f"--- Source {i}: {source} (similarity: {chunk['similarity']}) ---\n{entity_line}{body}")

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


_REWRITE_PROMPT = _REWRITE_PROMPT_IMPORTED


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


async def _rephrase_for_retry(query: str) -> str | None:
    """Rephrase a failed search query using LLM for a retry attempt."""
    messages = [
        {"role": "system", "content": REPHRASE_FOR_SEARCH_PROMPT},
        {"role": "user", "content": query},
    ]
    try:
        result = await _llm_rewrite_openai(messages)
        if result and result.lower() != query.lower() and len(result) < 500:
            return result
    except Exception:
        logger.warning("Query rephrase for retry failed", exc_info=True)
    return None


async def build_rag_prompt(
    db: AsyncSession,
    query: str,
    history: list[ChatMessage] | None = None,
    product_filter: str | None = None,
    version_filter: str | None = None,
    doc_context: str | None = None,
    product_filter_source: str | None = None,
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
            "type_max_tokens": None,
        }

        logger.info(
            "RAG prompt built (no documents in system)",
            extra={"query": query[:100], **rag_debug},
        )

        return messages, [], rag_debug

    query_type, classify_product, classify_meta = await _classify_query(db, query)

    auto_product = classify_product
    if auto_product and auto_product != product_filter:
        if product_filter_source == "explicit":
            logger.info(
                "Auto-detected product ignored (explicit lock)",
                extra={"detected": auto_product, "locked": product_filter, "query": query[:100]},
            )
        else:
            logger.info(
                "Auto-detected product from query via LLM classify",
                extra={"product": auto_product, "previous": product_filter, "query": query[:100]},
            )
            product_filter = auto_product

    type_max_tokens = _TYPE_MAX_TOKENS.get(query_type)

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

    retry_used = False
    rephrase_ms = 0.0
    rephrase_query: str | None = None

    if not chunks and query_type != "chitchat" and settings.search_retry_enabled:
        t_rephrase = time.perf_counter()
        rephrased = await _rephrase_for_retry(search_query)
        rephrase_ms = round((time.perf_counter() - t_rephrase) * 1000, 1)

        if rephrased:
            logger.info(
                "Search retry: rephrasing query",
                extra={"original": search_query[:200], "rephrased": rephrased[:200]},
            )
            retry_meta: dict = {}
            retry_chunks = await search_documents(
                session=db,
                query=rephrased,
                product=product_filter,
                version=version_filter,
                doc_context=doc_context,
                limit=settings.rag_top_k,
                metadata=retry_meta,
            )

            if settings.rag_min_similarity > 0:
                retry_chunks = [c for c in retry_chunks if c["similarity"] >= settings.rag_min_similarity]

            if retry_chunks:
                chunks = retry_chunks
                search_query = rephrased
                rephrase_query = rephrased
                retry_used = True
                logger.info(
                    "Search retry succeeded",
                    extra={"chunks_found": len(chunks), "top_sim": chunks[0]["similarity"]},
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
        context_header += f"Product: {detected_product}\n"

    doc_types_found = set(c.get("doc_type", "other") for c in chunks)
    if doc_types_found - {"other"}:
        context_header += f"Source types: {', '.join(sorted(doc_types_found - {'other'}))}\n"

    context_header += "\n"
    context_block = f"{context_header}{context}\n</documentation_context>"

    system_prompt = _build_system_prompt(query_type)
    prompt_hash = hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()[:12]

    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
    ]

    if query_type == "chitchat":
        if history:
            messages.extend(_build_history_messages(
                history, settings.rag_history_messages, settings.rag_history_max_tokens,
            ))
        messages.append({"role": "user", "content": query})
    else:
        messages.append({"role": "user", "content": context_block})
        messages.append({"role": "assistant", "content": "Understood. I will use the documentation context above to answer questions. If the sources contain relevant information, I will summarize it."})

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
            "doc_type": c.get("doc_type", "other"),
            "entities": c.get("entities", {}),
        }
        for c in chunks
    ]

    query_tokens = _estimate_tokens(query)
    history_msgs = _build_history_messages(
        history, settings.rag_history_messages, settings.rag_history_max_tokens,
    ) if history else []
    history_tokens = sum(_estimate_tokens(m["content"]) for m in history_msgs)
    system_prompt_tokens = _estimate_tokens(system_prompt) + _estimate_tokens(context_block)

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
        "query_type": query_type,
        "prompt_hash": prompt_hash,
        "retry_used": retry_used,
        "rephrase_ms": rephrase_ms,
        "rephrase_query": rephrase_query,
        "type_max_tokens": type_max_tokens,
        **classify_meta,
    }

    logger.info(
        "RAG prompt built",
        extra={
            "query": query[:100],
            "search_query": search_query[:200] if search_query != query else None,
            "rewrite_ms": rewrite_ms if history else 0,
            "product_filter": product_filter,
            "query_type": query_type,
            **rag_debug,
        },
    )

    return messages, sources, rag_debug
