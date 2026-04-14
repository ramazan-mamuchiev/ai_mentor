"""Hybrid search service: pgvector cosine + PostgreSQL BM25 + RRF fusion + cross-encoder re-ranking."""

import hashlib
import json
import logging
import time
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.ingestion.embedder import embed_query
from app.llm.http_client import gemini_client

logger = logging.getLogger(__name__)


@dataclass
class ResolveResult:
    product_id: int | None = None
    product_name: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str | None = None
    resolve_ms: float = 0.0


async def _fetch_products_with_keys(session: AsyncSession) -> list[dict]:
    """Load all products with their search keys for LLM context."""
    rows = (await session.execute(text("""
        SELECT p.id, p.name, p.manufacturer, p.category,
               COALESCE(
                   (SELECT array_agg(DISTINCT psk.key)
                    FROM product_search_keys psk
                    WHERE psk.product_id = p.id),
                   ARRAY[]::text[]
               ) AS keys
        FROM products p
        ORDER BY p.id
    """))).mappings().all()
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "manufacturer": row["manufacturer"] or "",
            "category": row["category"] or "",
            "keys": list(row["keys"]) if row["keys"] else [],
        }
        for row in rows
    ]


async def _llm_resolve_product(name: str, products: list[dict]) -> ResolveResult:
    """Use Gemini Flash to match user input to a product from the catalog."""
    products_context = "\n".join(
        f"- id={p['id']}, name=\"{p['name']}\", manufacturer=\"{p['manufacturer']}\", "
        f"category=\"{p['category']}\", keys={p['keys']}"
        for p in products
    )

    prompt = f"""\
You are a product name resolver for a documentation system.

User typed: "{name}"

Product catalog:
{products_context}

Which product (if any) matches the user's input?
Consider: exact name, abbreviations, transliterations (Cyrillic↔Latin),
partial matches, manufacturer/category hints, and search keys.

If you find a match, return JSON: {{"id": <product_id>, "name": "<product_name>"}}
If no match, return JSON: {{"id": null, "name": null}}
Return ONLY valid JSON, nothing else."""

    url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": settings.product_resolve_model,
        "messages": [
            {"role": "system", "content": "You match user input to products. Return only JSON."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": 128,
        "reasoning_effort": "none",
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.gemini_api_key}",
    }

    t0 = time.perf_counter()
    try:
        resp = await gemini_client().post(url, json=payload, headers=headers, timeout=15.0)
        resp.raise_for_status()
        data = resp.json()

        raw_text = data["choices"][0]["message"]["content"].strip()
        api_usage = data.get("usage", {})
        resolve_ms = round((time.perf_counter() - t0) * 1000, 1)

        if raw_text.startswith("```"):
            lines = raw_text.split("\n")
            raw_text = "\n".join(lines[1:])
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3].strip()

        parsed = json.loads(raw_text)
        product_id = parsed.get("id")
        product_name = parsed.get("name")

        result = ResolveResult(
            product_id=int(product_id) if product_id is not None else None,
            product_name=product_name,
            prompt_tokens=api_usage.get("prompt_tokens", 0),
            completion_tokens=api_usage.get("completion_tokens", 0),
            model=settings.product_resolve_model,
            resolve_ms=resolve_ms,
        )

        if product_id is not None:
            logger.info(
                "LLM product resolved: %r → %r (id=%s, %.0fms)",
                name, product_name, product_id, resolve_ms,
            )
        else:
            logger.info("LLM product resolve: no match for %r (%.0fms)", name, resolve_ms)

        return result

    except Exception:
        resolve_ms = round((time.perf_counter() - t0) * 1000, 1)
        logger.warning("LLM product resolve failed for %r", name, exc_info=True)
        return ResolveResult(
            model=settings.product_resolve_model,
            resolve_ms=resolve_ms,
        )


async def resolve_product(
    session: AsyncSession,
    name: str,
) -> ResolveResult:
    """Resolve a product name to product_id using exact match + LLM fallback.

    Returns ResolveResult with product info and LLM usage stats.
    """
    if not name or not name.strip():
        return ResolveResult()

    name = name.strip()

    row = (await session.execute(
        text("SELECT id, name FROM products WHERE name = :n LIMIT 1"),
        {"n": name},
    )).mappings().first()
    if row:
        return ResolveResult(product_id=row["id"], product_name=row["name"])

    products = await _fetch_products_with_keys(session)
    if not products:
        return ResolveResult()

    return await _llm_resolve_product(name, products)


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _deduplicate_chunks(results: list[dict], limit: int) -> list[dict]:
    """Remove near-duplicate chunks (same content from different document uploads).

    Uses SHA-256 of full content instead of a prefix to avoid false collisions.
    """
    seen: set[tuple[str, str]] = set()
    unique: list[dict] = []
    for r in results:
        key = (r["heading_path"], _content_hash(r["content"]))
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)
        if len(unique) >= limit:
            break
    return unique


_NEUTRAL_BOOST: dict[str, float] = {
    "user_guide": 1.00, "overview": 1.00, "troubleshooting": 1.00,
    "configuration": 1.00, "release_notes": 1.00, "changelog": 1.00,
    "api_reference": 1.00, "protocol": 1.00, "model_schema": 1.00, "other": 1.00,
}

_DOC_TYPE_BOOST_PROFILES: dict[str, dict[str, float]] = {
    "overview": {
        "user_guide": 1.20, "overview": 1.15, "troubleshooting": 1.05,
        "configuration": 1.00, "release_notes": 1.00, "changelog": 1.00,
        "api_reference": 0.90, "protocol": 0.85, "model_schema": 0.85, "other": 1.00,
    },
    "technical": {
        "user_guide": 1.05, "overview": 1.00, "troubleshooting": 1.00,
        "configuration": 1.00, "release_notes": 1.00, "changelog": 1.00,
        "api_reference": 1.15, "protocol": 1.10, "model_schema": 1.10, "other": 1.00,
    },
    "code": {
        "user_guide": 0.95, "overview": 0.90, "troubleshooting": 0.90,
        "configuration": 1.00, "release_notes": 1.00, "changelog": 1.00,
        "api_reference": 1.20, "protocol": 1.15, "model_schema": 1.15, "other": 1.00,
    },
    "troubleshooting": {
        "user_guide": 1.10, "overview": 1.00, "troubleshooting": 1.20,
        "configuration": 1.10, "release_notes": 1.00, "changelog": 1.00,
        "api_reference": 0.90, "protocol": 0.85, "model_schema": 0.85, "other": 1.00,
    },
    "comparison": {
        "user_guide": 1.10, "overview": 1.10, "troubleshooting": 1.00,
        "configuration": 1.00, "release_notes": 1.00, "changelog": 1.00,
        "api_reference": 1.00, "protocol": 1.00, "model_schema": 1.00, "other": 1.00,
    },
    "chitchat": _NEUTRAL_BOOST,
}


def _apply_doc_type_boost(results: list[dict], query_type: str | None = None) -> list[dict]:
    """Re-sort results by similarity x doc_type multiplier.

    The boost profile is chosen by query_type: how-to queries prefer guides,
    code/technical queries prefer API references, etc.
    """
    profile = _DOC_TYPE_BOOST_PROFILES.get(query_type or "overview",
                                           _DOC_TYPE_BOOST_PROFILES["overview"])
    boosted = []
    for r in results:
        factor = profile.get(r.get("doc_type", "other"), 1.0)
        boosted.append((r, r["similarity"] * factor))
    boosted.sort(key=lambda x: x[1], reverse=True)
    return [r for r, _ in boosted]


def _rrf_fuse(
    vector_results: list[dict],
    bm25_results: list[dict],
    k: int = 60,
    vector_weight: float = 0.7,
    bm25_weight: float = 0.3,
) -> list[dict]:
    """Reciprocal Rank Fusion: merge vector and BM25 result lists.

    RRF score = w_vec / (k + rank_vec) + w_bm25 / (k + rank_bm25)
    Chunks appearing in only one list get rank = len(list) + 1 for the missing list.
    """
    all_chunks: dict[str, dict] = {}
    vec_rank: dict[str, int] = {}
    bm25_rank: dict[str, int] = {}

    for rank, r in enumerate(vector_results, 1):
        cid = (r["heading_path"], _content_hash(r["content"]))
        key = f"{cid[0]}||{cid[1]}"
        all_chunks[key] = r
        vec_rank[key] = rank

    for rank, r in enumerate(bm25_results, 1):
        cid = (r["heading_path"], _content_hash(r["content"]))
        key = f"{cid[0]}||{cid[1]}"
        if key not in all_chunks:
            all_chunks[key] = r
        bm25_rank[key] = rank

    default_vec_rank = len(vector_results) + 1
    default_bm25_rank = len(bm25_results) + 1

    scored: list[tuple[str, float]] = []
    for key in all_chunks:
        vr = vec_rank.get(key, default_vec_rank)
        br = bm25_rank.get(key, default_bm25_rank)
        score = vector_weight / (k + vr) + bm25_weight / (k + br)
        scored.append((key, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [all_chunks[key] for key, _ in scored]


async def _bm25_search(
    session: AsyncSession,
    query: str,
    where_sql: str,
    params: dict,
    fetch_limit: int,
) -> list[dict]:
    """Full-text search using PostgreSQL tsvector/tsquery.

    When ``multilang_bm25_enabled`` the search targets the *stemmed*
    ``tsv_lang`` column with a combined tsquery (simple | english | russian)
    so that morphological forms are matched correctly.
    """
    bm25_params = {**params, "tsquery": query}

    if settings.multilang_bm25_enabled:
        tsquery_expr = (
            "(plainto_tsquery('simple', :tsquery)"
            " || plainto_tsquery('english', :tsquery)"
            " || plainto_tsquery('russian', :tsquery))"
        )
        tsv_col = "c.tsv_lang"
    else:
        tsquery_expr = "plainto_tsquery('simple', :tsquery)"
        tsv_col = "c.tsv"

    sql = text(f"""
        SELECT
            c.document_id,
            c.content,
            c.parent_content,
            c.heading_path,
            c.heading_level,
            c.token_count,
            c.doc_type,
            c.entities,
            c.layer,
            c.topic,
            c.doc_number,
            c.related_docs,
            d.title AS doc_title,
            p.id AS product_id,
            p.name AS product_name,
            p.manufacturer,
            p.version AS firmware_version,
            ts_rank_cd({tsv_col}, {tsquery_expr}) AS bm25_score
        FROM chunks c
        JOIN documents d ON c.document_id = d.id
        JOIN products p ON d.product_id = p.id
        WHERE {where_sql}
          AND {tsv_col} @@ {tsquery_expr}
        ORDER BY bm25_score DESC
        LIMIT :limit
    """)

    result = await session.execute(sql, bm25_params)
    rows = result.mappings().all()
    return [
        {
            "document_id": row["document_id"],
            "content": row["content"],
            "parent_content": row["parent_content"],
            "heading_path": row["heading_path"],
            "heading_level": row["heading_level"],
            "token_count": row["token_count"],
            "doc_type": row["doc_type"] or "other",
            "entities": row["entities"] or {},
            "layer": row["layer"],
            "topic": row["topic"],
            "doc_number": row["doc_number"],
            "related_docs": row["related_docs"] or [],
            "doc_title": row["doc_title"],
            "product_id": row["product_id"],
            "product_name": row["product_name"],
            "manufacturer": row["manufacturer"],
            "firmware_version": row["firmware_version"],
            "similarity": round(float(row["bm25_score"]), 4),
        }
        for row in rows
    ]


async def search_documents(
    session: AsyncSession,
    query: str,
    product_id: int | None = None,
    version: str | None = None,
    doc_context: str | None = None,
    doc_type: str | None = None,
    source_folder: str | None = None,
    layer: str | None = None,
    limit: int = 5,
    metadata: dict | None = None,
    query_type: str | None = None,
) -> list[dict]:
    """Hybrid search: vector similarity + BM25 full-text, fused via RRF.

    Returns list of dicts with content, heading_path, similarity, product info.
    Fetches extra candidates and deduplicates to handle multiple uploads of the same doc.

    Product resolution is done by the caller — this function only accepts product_id.
    """
    t0 = time.perf_counter()

    embed_text = query
    if settings.hyde_enabled:
        from app.search.hyde import generate_hyde
        hyde_text, hyde_meta = await generate_hyde(query, query_type)
        if metadata is not None:
            metadata.update(hyde_meta)
        if hyde_text:
            embed_text = hyde_text

    t_embed = time.perf_counter()
    query_embedding, embedding_api_tokens = embed_query(embed_text)
    embed_ms = round((time.perf_counter() - t_embed) * 1000, 1)

    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    if settings.rerank_enabled:
        fetch_limit = max(limit * 3, settings.rerank_candidates)
    else:
        fetch_limit = limit * 3

    where_clauses = ["d.status = 'ready'"]
    params: dict = {"embedding": embedding_str, "limit": fetch_limit}

    if product_id is not None:
        where_clauses.append("d.product_id = :product_id")
        params["product_id"] = product_id
    if version:
        where_clauses.append("p.version = :version")
        params["version"] = version
    if doc_context:
        where_clauses.append("d.title = :doc_context")
        params["doc_context"] = doc_context
    if doc_type:
        where_clauses.append("c.doc_type = :doc_type")
        params["doc_type"] = doc_type
    if source_folder:
        where_clauses.append("d.source_folder LIKE :source_folder")
        params["source_folder"] = f"%{source_folder}%"
    if layer:
        where_clauses.append("c.layer = :layer")
        params["layer"] = layer

    where_sql = " AND ".join(where_clauses)

    vector_sql = text(f"""
        SELECT
            c.document_id,
            c.content,
            c.parent_content,
            c.heading_path,
            c.heading_level,
            c.token_count,
            c.doc_type,
            c.entities,
            c.layer,
            c.topic,
            c.doc_number,
            c.related_docs,
            d.title AS doc_title,
            p.id AS product_id,
            p.name AS product_name,
            p.manufacturer,
            p.version AS firmware_version,
            1 - (c.embedding <=> CAST(:embedding AS halfvec)) AS similarity
        FROM chunks c
        JOIN documents d ON c.document_id = d.id
        JOIN products p ON d.product_id = p.id
        WHERE {where_sql}
        ORDER BY c.embedding <=> CAST(:embedding AS halfvec)
        LIMIT :limit
    """)

    logger.debug(
        "Search query executing",
        extra={"query": query, "product_id": product_id, "version": version, "embed_ms": embed_ms},
    )

    t_db = time.perf_counter()
    ef_val = int(settings.hnsw_ef_search)
    await session.execute(text(f"SET LOCAL hnsw.ef_search = {ef_val}"))
    result = await session.execute(vector_sql, params)
    rows = result.mappings().all()
    vector_results = [
        {
            "document_id": row["document_id"],
            "content": row["content"],
            "parent_content": row["parent_content"],
            "heading_path": row["heading_path"],
            "heading_level": row["heading_level"],
            "token_count": row["token_count"],
            "doc_type": row["doc_type"] or "other",
            "entities": row["entities"] or {},
            "layer": row["layer"],
            "topic": row["topic"],
            "doc_number": row["doc_number"],
            "related_docs": row["related_docs"] or [],
            "doc_title": row["doc_title"],
            "product_id": row["product_id"],
            "product_name": row["product_name"],
            "manufacturer": row["manufacturer"],
            "firmware_version": row["firmware_version"],
            "similarity": round(float(row["similarity"]), 4),
        }
        for row in rows
    ]

    bm25_results: list[dict] = []
    bm25_ms = 0.0
    if settings.hybrid_search_enabled:
        t_bm25 = time.perf_counter()
        try:
            bm25_results = await _bm25_search(session, query, where_sql, params, fetch_limit)
        except Exception:
            logger.warning("BM25 search failed, falling back to vector-only", exc_info=True)
        bm25_ms = round((time.perf_counter() - t_bm25) * 1000, 1)

    db_ms = round((time.perf_counter() - t_db) * 1000, 1)

    if bm25_results:
        raw_results = _rrf_fuse(
            vector_results, bm25_results,
            k=settings.hybrid_rrf_k,
            vector_weight=settings.hybrid_vector_weight,
            bm25_weight=settings.hybrid_bm25_weight,
        )
    else:
        raw_results = vector_results

    deduped = _deduplicate_chunks(raw_results, fetch_limit)
    dedup_removed = len(raw_results) - len(deduped)

    if settings.doc_type_boost_enabled:
        deduped = _apply_doc_type_boost(deduped, query_type=query_type)

    rerank_ms = 0.0
    rerank_prompt_tokens = 0
    rerank_completion_tokens = 0
    rerank_total_tokens = 0
    rerank_model = ""
    if settings.rerank_enabled and len(deduped) > 1:
        from app.search.reranker import rerank

        t_rerank = time.perf_counter()
        rerank_result = await rerank(query, deduped, top_k=limit)
        results = rerank_result.results
        rerank_ms = round((time.perf_counter() - t_rerank) * 1000, 1)
        rerank_prompt_tokens = rerank_result.usage.prompt_tokens
        rerank_completion_tokens = rerank_result.usage.completion_tokens
        rerank_total_tokens = rerank_result.usage.total_tokens
        rerank_model = rerank_result.usage.model
    else:
        results = deduped[:limit]

    duration_ms = round((time.perf_counter() - t0) * 1000, 1)
    result_count = len(results)
    top_similarity = results[0]["similarity"] if results else 0.0

    log_extra = {
        "query": query, "product_id": product_id, "version": version,
        "result_count": result_count, "top_similarity": top_similarity,
        "duration_ms": duration_ms, "embed_ms": embed_ms, "db_ms": db_ms,
        "bm25_ms": bm25_ms, "rerank_ms": rerank_ms,
        "rerank_prompt_tokens": rerank_prompt_tokens,
        "rerank_completion_tokens": rerank_completion_tokens,
        "rerank_total_tokens": rerank_total_tokens,
        "vector_candidates": len(vector_results),
        "bm25_candidates": len(bm25_results),
        "raw_candidates": len(raw_results), "dedup_removed": dedup_removed,
        "hybrid_enabled": settings.hybrid_search_enabled,
        "embed_source": "hyde" if (embed_text != query) else "original",
        "hyde_enabled": settings.hyde_enabled,
    }

    if metadata is not None:
        metadata.update({
            "rerank_ms": rerank_ms,
            "rerank_prompt_tokens": rerank_prompt_tokens,
            "rerank_completion_tokens": rerank_completion_tokens,
            "rerank_total_tokens": rerank_total_tokens,
            "rerank_model": rerank_model,
            "embedding_api_tokens": embedding_api_tokens,
        })

    if result_count == 0:
        logger.warning("Search returned 0 results", extra=log_extra)
    else:
        logger.info("Search completed", extra=log_extra)

    if results:
        try:
            async with session.begin_nested():
                await _update_rag_hit_counts(session, results)
        except Exception:
            logger.warning("Failed to update RAG hit counts", exc_info=True)

    return results


async def _update_rag_hit_counts(session: AsyncSession, results: list[dict]) -> None:
    """Increment rag_hit_count and update rag_avg_similarity for documents used in search results.

    Does NOT commit — the caller is responsible for committing the transaction.
    """
    from collections import defaultdict
    doc_sims: dict[int, list[float]] = defaultdict(list)
    for r in results:
        doc_id = r.get("document_id")
        if doc_id:
            doc_sims[doc_id].append(r["similarity"])

    if not doc_sims:
        return

    for doc_id, sims in doc_sims.items():
        avg_sim = round(sum(sims) / len(sims), 4)
        await session.execute(text("""
            UPDATE documents
            SET rag_hit_count = rag_hit_count + :hits,
                rag_avg_similarity = CASE
                    WHEN rag_hit_count = 0 THEN :avg_sim
                    ELSE ROUND(CAST((rag_avg_similarity * rag_hit_count + :sum_sim) / (rag_hit_count + :hits) AS NUMERIC), 4)
                END,
                rag_last_used_at = NOW()
            WHERE id = :doc_id
        """), {"doc_id": doc_id, "hits": len(sims), "avg_sim": avg_sim, "sum_sim": sum(sims)})


async def search_endpoint(
    session: AsyncSession,
    endpoint: str,
    product_id: int | None = None,
    metadata: dict | None = None,
) -> list[dict]:
    """Find documentation for a specific API endpoint path.

    First tries exact heading_path match (ILIKE), then falls back to vector search.
    Product resolution is done by the caller.
    """
    t0 = time.perf_counter()

    where_clauses = [
        "d.status = 'ready'",
        "c.heading_path ILIKE '%' || :endpoint || '%'",
    ]
    params: dict = {"endpoint": endpoint}

    if product_id is not None:
        where_clauses.append("d.product_id = :product_id")
        params["product_id"] = product_id

    where_sql = " AND ".join(where_clauses)

    sql = text(f"""
        SELECT
            c.document_id,
            c.content,
            c.parent_content,
            c.heading_path,
            c.heading_level,
            c.token_count,
            c.doc_type,
            c.entities,
            c.layer,
            c.topic,
            c.doc_number,
            c.related_docs,
            d.title AS doc_title,
            p.id AS product_id,
            p.name AS product_name,
            p.manufacturer,
            p.version AS firmware_version
        FROM chunks c
        JOIN documents d ON c.document_id = d.id
        JOIN products p ON d.product_id = p.id
        WHERE {where_sql}
        ORDER BY c.heading_level, c.chunk_index
        LIMIT 10
    """)

    result = await session.execute(sql, params)
    rows = result.mappings().all()

    if rows:
        duration_ms = round((time.perf_counter() - t0) * 1000, 1)
        if metadata is not None:
            metadata["search_ms"] = duration_ms
        logger.info(
            "Endpoint search: exact match",
            extra={
                "endpoint": endpoint, "product_id": product_id,
                "result_count": len(rows), "match_type": "exact",
                "duration_ms": duration_ms,
            },
        )
        return [
            {
                "document_id": row["document_id"],
                "content": row["content"],
                "parent_content": row["parent_content"],
                "heading_path": row["heading_path"],
                "heading_level": row["heading_level"],
                "token_count": row["token_count"],
                "doc_type": row["doc_type"] or "other",
                "entities": row["entities"] or {},
                "layer": row["layer"],
                "topic": row["topic"],
                "doc_number": row["doc_number"],
                "related_docs": row["related_docs"] or [],
                "doc_title": row["doc_title"],
                "product_id": row["product_id"],
                "product_name": row["product_name"],
                "manufacturer": row["manufacturer"],
                "firmware_version": row["firmware_version"],
                "match_type": "exact",
                "similarity": 1.0,
            }
            for row in rows
        ]

    logger.warning(
        "Endpoint search: no exact match, falling back to vector search",
        extra={"endpoint": endpoint, "product_id": product_id},
    )
    return await search_documents(session, f"API endpoint {endpoint}", product_id=product_id, limit=5, metadata=metadata)
