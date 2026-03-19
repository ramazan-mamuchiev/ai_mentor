"""MCP tools for IPCodex: semantic search over product documentation for writing integration code."""

import logging
import time

from sqlalchemy import text

from app.database import async_session
from app.search.service import search_documents, search_endpoint

logger = logging.getLogger(__name__)


async def tool_search_documentation(
    query: str,
    product: str | None = None,
    version: str | None = None,
    limit: int = 5,
) -> str:
    """Search IPCodex knowledge base for product integration documentation.

    IPCodex indexes API documentation for hardware devices (IP cameras, access controllers,
    intercoms, sensors) and software platforms (VMS, PSIM, IoT platforms, SDKs).

    Use this tool when you need to write integration code and need to find:
    - REST/HTTP/gRPC/SOAP API endpoints and their parameters
    - Authentication methods (API keys, OAuth, digest, ONVIF)
    - Request/response formats, data models, and protocol details
    - Code examples and integration patterns
    - Configuration parameters and supported values

    Args:
        query: Describe what you need in natural language.
            Good: "how to open a door via HikCentral HTTP API"
            Good: "Axxon One gRPC camera registration with analytics metadata"
            Good: "ONVIF PTZ continuous move command"
            Good: "RTSP stream URL format for Hikvision cameras"
            Bad: "door" (too vague)
        product: Filter by product name. Use list_products first to see available products.
            Examples: "HikCentral", "Axxon One", "DS-2CD2347G2-LU"
        version: Filter by firmware or API version. Examples: "V2.6.1", "5.0"
        limit: Number of results (1-20, default 5). Use higher values for broad queries.
    """
    limit = max(1, min(limit, 20))
    logger.debug(
        "MCP search_documentation called",
        extra={"query": query, "product": product, "version": version, "limit": limit},
    )

    t0 = time.perf_counter()
    async with async_session() as session:
        results = await search_documents(session, query, product=product, version=version, limit=limit)
    duration_ms = round((time.perf_counter() - t0) * 1000, 1)

    result_count = len(results)
    top_similarity = results[0]["similarity"] if results else 0.0

    log_extra = {
        "tool": "search_documentation",
        "result_count": result_count,
        "top_similarity": top_similarity,
        "duration_ms": duration_ms,
    }
    if duration_ms > 10000:
        logger.warning("MCP search_documentation slow", extra=log_extra)
    else:
        logger.info("MCP search_documentation completed", extra=log_extra)

    if not results:
        return "No results found. Try a different query or check available products with list_products."

    parts: list[str] = []
    for i, r in enumerate(results, 1):
        meta = f"[{i}] {r['product_name']} | {r['firmware_version']} | {r['doc_title']} > {r['heading_path']} (similarity: {r['similarity']})"
        parts.append(f"{meta}\n\n{r['content']}")

    return "\n\n---\n\n".join(parts)


async def tool_get_api_endpoint(
    endpoint: str,
    product: str | None = None,
) -> str:
    """Look up documentation for a specific API endpoint path.

    Use this when you already know the exact endpoint path and need its full documentation
    (parameters, request body, response format, authentication, examples).

    This performs an exact path match first, then falls back to semantic search.

    Args:
        endpoint: The API endpoint path to look up.
            Examples: "/acs/v1/door/doControl", "/ISAPI/AccessControl/Door/param",
            "/api/v2/cameras/{id}/streams", "POST /event/notification/alertStream"
        product: Filter by product name. Examples: "HikCentral", "Axxon One"
    """
    logger.debug(
        "MCP get_api_endpoint called",
        extra={"endpoint": endpoint, "product": product},
    )

    t0 = time.perf_counter()
    try:
        async with async_session() as session:
            results = await search_endpoint(session, endpoint, product=product)
        duration_ms = round((time.perf_counter() - t0) * 1000, 1)
    except Exception as e:
        duration_ms = round((time.perf_counter() - t0) * 1000, 1)
        logger.error(
            "MCP get_api_endpoint failed",
            extra={"tool": "get_api_endpoint", "duration_ms": duration_ms, "error_type": type(e).__name__},
            exc_info=True,
        )
        raise

    result_count = len(results)
    log_extra = {
        "tool": "get_api_endpoint",
        "result_count": result_count,
        "duration_ms": duration_ms,
    }
    if duration_ms > 10000:
        logger.warning("MCP get_api_endpoint slow", extra=log_extra)
    else:
        logger.info("MCP get_api_endpoint completed", extra=log_extra)

    if not results:
        return f"No documentation found for endpoint '{endpoint}'. Try search_documentation with a broader query."

    parts: list[str] = []
    for r in results:
        match_type = r.get("match_type", "vector")
        meta = f"{r['product_name']} | {r['firmware_version']} | {r['doc_title']} > {r['heading_path']} ({match_type} match)"
        parts.append(f"{meta}\n\n{r['content']}")

    return "\n\n---\n\n".join(parts)


async def tool_list_products(
    category: str | None = None,
    query: str | None = None,
) -> str:
    """List products with indexed documentation available in IPCodex.

    Call this FIRST to discover what products are available before using search_documentation.

    Products include both hardware devices (IP cameras, access controllers, intercoms, NVRs)
    and software platforms (VMS like Axxon One, PSIM, IoT platforms, SDKs).

    Args:
        category: Filter by product category.
            Examples: "camera", "vms", "access_control", "intercom", "nvr", "sdk"
        query: Search products by name or manufacturer.
            Examples: "Hikvision", "Axxon", "DS-2CD"
    """
    logger.debug("MCP list_products called", extra={"category": category, "query": query})

    t0 = time.perf_counter()
    async with async_session() as session:
        where_clauses: list[str] = []
        params: dict = {}

        if category:
            where_clauses.append("p.category ILIKE :category")
            params["category"] = f"%{category}%"
        if query:
            where_clauses.append(
                "(p.name ILIKE :query OR p.manufacturer ILIKE :query)"
            )
            params["query"] = f"%{query}%"

        where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        sql = text(f"""
            SELECT
                p.name,
                p.manufacturer,
                p.category,
                COALESCE(STRING_AGG(DISTINCT fw.version, ', ' ORDER BY fw.version), '') AS versions,
                COUNT(DISTINCT d.id) FILTER (WHERE d.status = 'ready') AS doc_count,
                COUNT(c.id) FILTER (WHERE d.status = 'ready') AS chunk_count
            FROM products p
            LEFT JOIN firmware_versions fw ON fw.product_id = p.id
            LEFT JOIN documents d ON d.product_id = p.id
            LEFT JOIN chunks c ON c.document_id = d.id
            {where_sql}
            GROUP BY p.id, p.name, p.manufacturer, p.category
            ORDER BY p.name
        """)

        result = await session.execute(sql, params)
        rows = result.mappings().all()

    duration_ms = round((time.perf_counter() - t0) * 1000, 1)
    logger.info(
        "MCP list_products completed",
        extra={"tool": "list_products", "result_count": len(rows), "duration_ms": duration_ms},
    )

    if not rows:
        if category or query:
            return f"No products found matching your filter. Try list_products without filters to see all available products."
        return "No products indexed yet."

    parts: list[str] = []
    for row in rows:
        line = f"- {row['name']}"
        if row["manufacturer"]:
            line += f" ({row['manufacturer']})"
        if row["category"]:
            line += f" [{row['category']}]"
        if row["versions"]:
            line += f" — versions: {row['versions']}"
        line += f" — {row['doc_count']} docs, {row['chunk_count']} chunks"
        parts.append(line)

    return f"Available products ({len(rows)}):\n" + "\n".join(parts)
