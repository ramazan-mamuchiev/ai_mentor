"""Vector search service: pgvector cosine similarity + heading_path exact match."""

import logging
import time

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.embedder import embed_query

logger = logging.getLogger(__name__)


def _deduplicate_chunks(results: list[dict], limit: int) -> list[dict]:
    """Remove near-duplicate chunks (same content from different document uploads)."""
    seen: set[tuple[str, str]] = set()
    unique: list[dict] = []
    for r in results:
        key = (r["heading_path"], r["content"][:200])
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)
        if len(unique) >= limit:
            break
    return unique


async def search_documents(
    session: AsyncSession,
    query: str,
    product: str | None = None,
    version: str | None = None,
    doc_context: str | None = None,
    limit: int = 5,
) -> list[dict]:
    """Semantic search across all indexed documentation.

    Returns list of dicts with content, heading_path, similarity, product info.
    Fetches extra candidates and deduplicates to handle multiple uploads of the same doc.

    Args:
        doc_context: If set, restricts search to documents whose title matches this value.
    """
    t0 = time.perf_counter()

    t_embed = time.perf_counter()
    query_embedding = embed_query(query)
    embed_ms = round((time.perf_counter() - t_embed) * 1000, 1)

    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    fetch_limit = limit * 3

    where_clauses = ["d.status = 'ready'"]
    params: dict = {"embedding": embedding_str, "limit": fetch_limit}

    if product:
        where_clauses.append("p.name ILIKE '%' || :product || '%'")
        params["product"] = product
    if version:
        where_clauses.append("fw.version = :version")
        params["version"] = version
    if doc_context:
        where_clauses.append("d.title = :doc_context")
        params["doc_context"] = doc_context

    where_sql = " AND ".join(where_clauses)

    sql = text(f"""
        SELECT
            c.content,
            c.heading_path,
            c.heading_level,
            c.token_count,
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
        extra={"query": query, "product": product, "version": version, "embed_ms": embed_ms},
    )

    t_db = time.perf_counter()
    result = await session.execute(sql, params)
    db_ms = round((time.perf_counter() - t_db) * 1000, 1)

    rows = result.mappings().all()
    raw_results = [
        {
            "content": row["content"],
            "heading_path": row["heading_path"],
            "heading_level": row["heading_level"],
            "token_count": row["token_count"],
            "doc_title": row["doc_title"],
            "product_name": row["product_name"],
            "manufacturer": row["manufacturer"],
            "firmware_version": row["firmware_version"],
            "similarity": round(float(row["similarity"]), 4),
        }
        for row in rows
    ]

    results = _deduplicate_chunks(raw_results, limit)

    duration_ms = round((time.perf_counter() - t0) * 1000, 1)
    result_count = len(results)
    dedup_removed = len(raw_results) - result_count
    top_similarity = results[0]["similarity"] if results else 0.0

    log_extra = {
        "query": query, "product": product, "version": version,
        "result_count": result_count, "top_similarity": top_similarity,
        "duration_ms": duration_ms, "embed_ms": embed_ms, "db_ms": db_ms,
        "raw_candidates": len(raw_results), "dedup_removed": dedup_removed,
    }

    if result_count == 0:
        logger.warning("Search returned 0 results", extra=log_extra)
    else:
        logger.info("Search completed", extra=log_extra)

    return results


async def search_endpoint(
    session: AsyncSession,
    endpoint: str,
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

    if product:
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
                "endpoint": endpoint, "product": product,
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
        extra={"endpoint": endpoint, "product": product},
    )
    return await search_documents(session, f"API endpoint {endpoint}", product=product, limit=5)
