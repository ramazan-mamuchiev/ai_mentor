"""Vector search service: pgvector cosine similarity + heading_path exact match."""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.embedder import embed_query

logger = logging.getLogger(__name__)


async def search_documents(
    session: AsyncSession,
    query: str,
    device: str | None = None,
    version: str | None = None,
    limit: int = 5,
) -> list[dict]:
    """Semantic search across all indexed documentation.

    Returns list of dicts with content, heading_path, similarity, device info.
    """
    query_embedding = embed_query(query)

    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    where_clauses = ["d.status = 'ready'"]
    params: dict = {"embedding": embedding_str, "limit": limit}

    if device:
        where_clauses.append("dev.name ILIKE '%' || :device || '%'")
        params["device"] = device
    if version:
        where_clauses.append("fw.version = :version")
        params["version"] = version

    where_sql = " AND ".join(where_clauses)

    sql = text(f"""
        SELECT
            c.content,
            c.heading_path,
            c.heading_level,
            c.token_count,
            d.title AS doc_title,
            dev.name AS device_name,
            dev.manufacturer,
            fw.version AS firmware_version,
            1 - (c.embedding <=> CAST(:embedding AS vector)) AS similarity
        FROM chunks c
        JOIN documents d ON c.document_id = d.id
        JOIN devices dev ON d.device_id = dev.id
        JOIN firmware_versions fw ON d.firmware_version_id = fw.id
        WHERE {where_sql}
        ORDER BY c.embedding <=> CAST(:embedding AS vector)
        LIMIT :limit
    """)

    result = await session.execute(sql, params)

    rows = result.mappings().all()
    return [
        {
            "content": row["content"],
            "heading_path": row["heading_path"],
            "heading_level": row["heading_level"],
            "token_count": row["token_count"],
            "doc_title": row["doc_title"],
            "device_name": row["device_name"],
            "manufacturer": row["manufacturer"],
            "firmware_version": row["firmware_version"],
            "similarity": round(float(row["similarity"]), 4),
        }
        for row in rows
    ]


async def search_endpoint(
    session: AsyncSession,
    endpoint: str,
    device: str | None = None,
) -> list[dict]:
    """Find documentation for a specific API endpoint path.

    First tries exact heading_path match (ILIKE), then falls back to vector search.
    """
    where_clauses = [
        "d.status = 'ready'",
        "c.heading_path ILIKE '%' || :endpoint || '%'",
    ]
    params: dict = {"endpoint": endpoint}

    if device:
        where_clauses.append("dev.name ILIKE '%' || :device || '%'")
        params["device"] = device

    where_sql = " AND ".join(where_clauses)

    sql = text(f"""
        SELECT
            c.content,
            c.heading_path,
            c.heading_level,
            d.title AS doc_title,
            dev.name AS device_name,
            fw.version AS firmware_version
        FROM chunks c
        JOIN documents d ON c.document_id = d.id
        JOIN devices dev ON d.device_id = dev.id
        JOIN firmware_versions fw ON d.firmware_version_id = fw.id
        WHERE {where_sql}
        ORDER BY c.heading_level, c.chunk_index
        LIMIT 10
    """)

    result = await session.execute(sql, params)
    rows = result.mappings().all()

    if rows:
        return [
            {
                "content": row["content"],
                "heading_path": row["heading_path"],
                "doc_title": row["doc_title"],
                "device_name": row["device_name"],
                "firmware_version": row["firmware_version"],
                "match_type": "exact",
            }
            for row in rows
        ]

    logger.info("No exact match for endpoint '%s', falling back to vector search", endpoint)
    return await search_documents(session, f"API endpoint {endpoint}", device=device, limit=5)
