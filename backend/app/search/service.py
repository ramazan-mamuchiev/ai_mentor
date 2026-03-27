"""Hybrid search service: pgvector cosine + PostgreSQL BM25 + RRF fusion + cross-encoder re-ranking."""

import hashlib
import logging
import time

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.ingestion.embedder import embed_query

logger = logging.getLogger(__name__)


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
    """Full-text search using PostgreSQL tsvector/tsquery."""
    bm25_params = {**params, "tsquery": query}

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
            d.title AS doc_title,
            p.name AS product_name,
            p.manufacturer,
            fw.version AS firmware_version,
            ts_rank_cd(c.tsv, plainto_tsquery('simple', :tsquery)) AS bm25_score
        FROM chunks c
        JOIN documents d ON c.document_id = d.id
        JOIN products p ON d.product_id = p.id
        JOIN firmware_versions fw ON d.firmware_version_id = fw.id
        WHERE {where_sql}
          AND c.tsv @@ plainto_tsquery('simple', :tsquery)
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
            "doc_title": row["doc_title"],
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
    product: str | None = None,
    version: str | None = None,
    doc_context: str | None = None,
    doc_type: str | None = None,
    limit: int = 5,
    metadata: dict | None = None,
) -> list[dict]:
    """Hybrid search: vector similarity + BM25 full-text, fused via RRF.

    Returns list of dicts with content, heading_path, similarity, product info.
    Fetches extra candidates and deduplicates to handle multiple uploads of the same doc.

    Args:
        product_id: Exact product ID filter (preferred, used for explicit lock).
        product: Product name filter (fallback, partial match via ILIKE).
    """
    t0 = time.perf_counter()

    t_embed = time.perf_counter()
    query_embedding, embedding_api_tokens = embed_query(query)
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
    elif product:
        where_clauses.append("p.name ILIKE '%' || :product || '%'")
        params["product"] = product
    if version:
        where_clauses.append("fw.version = :version")
        params["version"] = version
    if doc_context:
        where_clauses.append("d.title = :doc_context")
        params["doc_context"] = doc_context
    if doc_type:
        where_clauses.append("c.doc_type = :doc_type")
        params["doc_type"] = doc_type

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
            d.title AS doc_title,
            p.name AS product_name,
            p.manufacturer,
            fw.version AS firmware_version,
            1 - (c.embedding <=> CAST(:embedding AS vector)) AS similarity
        FROM chunks c
        JOIN documents d ON c.document_id = d.id
        JOIN products p ON d.product_id = p.id
        JOIN firmware_versions fw ON d.firmware_version_id = fw.id
        WHERE {where_sql}
        ORDER BY c.embedding <=> CAST(:embedding AS vector)
        LIMIT :limit
    """)

    logger.debug(
        "Search query executing",
        extra={"query": query, "product_id": product_id, "product": product, "version": version, "embed_ms": embed_ms},
    )

    t_db = time.perf_counter()
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
            "doc_title": row["doc_title"],
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
        "query": query, "product_id": product_id, "product": product, "version": version,
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
    product: str | None = None,
) -> list[dict]:
    """Find documentation for a specific API endpoint path.

    First tries exact heading_path match (ILIKE), then falls back to vector search.
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
    elif product:
        where_clauses.append("p.name ILIKE '%' || :product || '%'")
        params["product"] = product

    where_sql = " AND ".join(where_clauses)

    sql = text(f"""
        SELECT
            c.content,
            c.heading_path,
            c.heading_level,
            d.title AS doc_title,
            p.name AS product_name,
            fw.version AS firmware_version
        FROM chunks c
        JOIN documents d ON c.document_id = d.id
        JOIN products p ON d.product_id = p.id
        JOIN firmware_versions fw ON d.firmware_version_id = fw.id
        WHERE {where_sql}
        ORDER BY c.heading_level, c.chunk_index
        LIMIT 10
    """)

    result = await session.execute(sql, params)
    rows = result.mappings().all()

    if rows:
        duration_ms = round((time.perf_counter() - t0) * 1000, 1)
        logger.info(
            "Endpoint search: exact match",
            extra={
                "endpoint": endpoint, "product_id": product_id, "product": product,
                "result_count": len(rows), "match_type": "exact",
                "duration_ms": duration_ms,
            },
        )
        return [
            {
                "content": row["content"],
                "heading_path": row["heading_path"],
                "doc_title": row["doc_title"],
                "product_name": row["product_name"],
                "firmware_version": row["firmware_version"],
                "match_type": "exact",
            }
            for row in rows
        ]

    logger.warning(
        "Endpoint search: no exact match, falling back to vector search",
        extra={"endpoint": endpoint, "product_id": product_id, "product": product},
    )
    return await search_documents(session, f"API endpoint {endpoint}", product_id=product_id, product=product, limit=5)
