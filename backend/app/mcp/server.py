"""MCP tools for Lexiro: semantic search over product documentation for writing integration code."""

import hashlib
import logging
import time
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import text

from app.billing.pricing import calculate_mcp_charge, calculate_mcp_cogs
from app.billing.usage_writer import write_usage_log
from app.config import settings
from app.database import async_session
from app.mcp.auth_middleware import (
    current_api_key_id,
    current_client_ip,
    current_tenant_id,
    current_user_agent,
)
from app.models import McpRequestLog, SearchAnalytics
from app.search.service import resolve_product, search_documents, search_endpoint

logger = logging.getLogger(__name__)


def _format_mcp_body(chunk: dict, seen_parents: set[str]) -> str:
    """Return the best available text for an MCP result.

    Prefers parent_content (full section) over chunk content.
    Deduplicates repeated parent sections and caps length to avoid
    blowing up the Cursor context window.
    """
    max_chars = settings.rag_max_context_tokens_per_source * 4

    parent = chunk.get("parent_content")
    if parent:
        parent_key = hashlib.sha256(parent.encode("utf-8")).hexdigest()
        if parent_key in seen_parents:
            return chunk["content"]
        seen_parents.add(parent_key)
        if len(parent) > max_chars:
            snippet = chunk["content"][:100]
            pos = parent.find(snippet)
            if pos >= 0:
                start = max(0, pos - max_chars // 3)
                return parent[start : start + max_chars] + "\n..."
            return parent[:max_chars] + "\n..."
        return parent
    return chunk["content"]


def _format_mcp_meta(index: int, r: dict) -> str:
    """Build a structured metadata header for one MCP search result."""
    doc_type = r.get("doc_type", "other")
    type_tag = f" [{doc_type}]" if doc_type and doc_type != "other" else ""

    entities = r.get("entities") or {}
    entity_line = ""
    if entities:
        flat = []
        for vals in entities.values():
            if isinstance(vals, list):
                flat.extend(str(v) for v in vals if v)
        if flat:
            entity_line = f"\nEntities: {', '.join(flat[:15])}"

    sim_info = f"similarity: {r.get('similarity', 0)}"
    if "rerank_score" in r:
        sim_info += f", rerank: {r['rerank_score']}"

    return (
        f"[{index}] {r['product_name']} | {r.get('firmware_version', '')} | "
        f"{r['doc_title']} > {r['heading_path']}{type_tag}"
        f"{entity_line}\n({sim_info})"
    )


def _embedding_model_name() -> str:
    return settings.embedding_model_gemini


def _calc_mcp_costs(metadata: dict) -> tuple[Decimal, Decimal]:
    """Calculate real COGS and charge for an MCP request from search metadata."""
    emb_model = settings.embedding_model_gemini
    emb_tokens = metadata.get("embedding_api_tokens", 0)
    rerank_model = metadata.get("rerank_model", "") or ""
    rerank_pt = metadata.get("rerank_prompt_tokens", 0)
    rerank_ct = metadata.get("rerank_completion_tokens", 0)
    cogs = calculate_mcp_cogs(emb_model, emb_tokens, rerank_model, rerank_pt, rerank_ct)
    charge = calculate_mcp_charge(emb_model, emb_tokens, rerank_model, rerank_pt, rerank_ct)
    return cogs, charge


async def _save_search_analytics(
    source: str,
    tool_name: str,
    query: str,
    duration_ms: float,
    result_count: int = 0,
    top_similarity: float = 0.0,
    product_filter: str | None = None,
    version_filter: str | None = None,
    tenant_id: str | None = None,
    api_key_id: str | None = None,
) -> None:
    """Persist a search analytics record (fire-and-forget, errors logged)."""
    try:
        async with async_session() as session:
            session.add(SearchAnalytics(
                source=source,
                tool_name=tool_name,
                query=query,
                product_filter=product_filter,
                version_filter=version_filter,
                result_count=result_count,
                top_similarity=top_similarity,
                duration_ms=duration_ms,
                embedding_model=_embedding_model_name(),
                tenant_id=tenant_id,
                api_key_id=api_key_id,
            ))
            await session.commit()
    except Exception:
        logger.warning("Failed to save search analytics", exc_info=True)


async def _save_mcp_request_log(
    *,
    request_id: str,
    tool_name: str,
    query_text: str | None = None,
    product_filter: str | None = None,
    version_filter: str | None = None,
    doc_type_filter: str | None = None,
    result_count: int = 0,
    top_similarity: float = 0.0,
    response_length: int = 0,
    query_tokens: int = 0,
    response_tokens: int = 0,
    metadata: dict | None = None,
    duration_ms: float = 0.0,
    cogs_usd: Decimal = Decimal("0"),
    charge_usd: Decimal = Decimal("0"),
    error: str | None = None,
) -> None:
    """Persist a detailed MCP request log record (fire-and-forget)."""
    meta = metadata or {}
    try:
        async with async_session() as session:
            session.add(McpRequestLog(
                tenant_id=current_tenant_id.get(),
                api_key_id=current_api_key_id.get(),
                request_id=request_id,
                tool_name=tool_name,
                query_text=query_text,
                product_filter=product_filter,
                version_filter=version_filter,
                doc_type_filter=doc_type_filter,
                result_count=result_count,
                top_similarity=top_similarity,
                response_length=response_length,
                query_tokens=query_tokens,
                response_tokens=response_tokens,
                embedding_tokens=meta.get("embedding_api_tokens", 0),
                rerank_prompt_tokens=meta.get("rerank_prompt_tokens", 0),
                rerank_completion_tokens=meta.get("rerank_completion_tokens", 0),
                rerank_total_tokens=meta.get("rerank_total_tokens", 0),
                rerank_model=meta.get("rerank_model"),
                duration_ms=duration_ms,
                embed_ms=meta.get("embed_ms", 0.0),
                search_ms=meta.get("search_ms", 0.0),
                rerank_ms=meta.get("rerank_ms", 0.0),
                cogs_usd=cogs_usd,
                charge_usd=charge_usd,
                client_ip=current_client_ip.get(),
                user_agent=current_user_agent.get(),
                error=error,
                status="error" if error else "ok",
            ))
            await session.commit()
    except Exception:
        logger.warning("Failed to save mcp_request_log", exc_info=True)


async def tool_search_documentation(
    query: str,
    product: str | None = None,
    version: str | None = None,
    doc_type: str | None = None,
    limit: int | None = None,
) -> str:
    """Search Lexiro knowledge base for product integration documentation.

    Lexiro indexes API documentation for hardware devices (IP cameras, access controllers,
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
        doc_type: Filter by documentation type.
            Examples: "api_reference", "guide", "example", "configuration", "protocol"
        limit: Number of results (1-20, default 10). Use higher values for broad queries.
    """
    if limit is None:
        limit = settings.mcp_default_limit
    limit = max(1, min(limit, 20))
    request_id = str(uuid4())
    logger.debug(
        "MCP search_documentation called",
        extra={"query": query, "product": product, "version": version, "limit": limit, "request_id": request_id},
    )

    metadata: dict = {}
    t0 = time.perf_counter()
    async with async_session() as session:
        results = await search_documents(
            session, query, product=product, version=version,
            doc_type=doc_type, limit=limit, metadata=metadata,
        )
    duration_ms = round((time.perf_counter() - t0) * 1000, 1)

    min_sim = settings.rag_min_similarity
    results = [r for r in results if r.get("similarity", 0) >= min_sim]
    if settings.rerank_enabled:
        results = [r for r in results if r.get("rerank_score", 1.0) >= settings.rerank_min_score]

    result_count = len(results)
    top_similarity = results[0]["similarity"] if results else 0.0

    log_extra = {
        "tool": "search_documentation",
        "result_count": result_count,
        "top_similarity": top_similarity,
        "duration_ms": duration_ms,
        "request_id": request_id,
    }
    if duration_ms > 10000:
        logger.warning("MCP search_documentation slow", extra=log_extra)
    else:
        logger.info("MCP search_documentation completed", extra=log_extra)

    await _save_search_analytics(
        source="mcp",
        tool_name="search_documentation",
        query=query,
        duration_ms=duration_ms,
        result_count=result_count,
        top_similarity=top_similarity,
        product_filter=product,
        version_filter=version,
        tenant_id=current_tenant_id.get(),
        api_key_id=current_api_key_id.get(),
    )

    if not results:
        response_text = "No results found. Try a different query or check available products with list_products."
    else:
        seen_parents: set[str] = set()
        parts: list[str] = []
        for i, r in enumerate(results, 1):
            meta = _format_mcp_meta(i, r)
            body = _format_mcp_body(r, seen_parents)
            parts.append(f"{meta}\n\n{body}")
        response_text = "\n\n---\n\n".join(parts)

    response_tokens = max(1, len(response_text) // 4)
    query_tokens = max(1, len(query) // 4)
    await write_usage_log(
        channel="mcp",
        action="search_documentation",
        request_id=request_id,
        query_text=query,
        query_tokens=query_tokens,
        result_count=result_count,
        response_tokens=response_tokens,
        response_length=len(response_text),
        top_similarity=top_similarity,
        product_filter=product,
        version_filter=version,
        duration_ms=duration_ms,
        embedding_ms=metadata.get("embed_ms", 0.0),
        search_ms=metadata.get("search_ms", 0.0),
        tenant_id=current_tenant_id.get(),
        api_key_id=current_api_key_id.get(),
    )

    cogs, charge = _calc_mcp_costs(metadata)
    await _save_mcp_request_log(
        request_id=request_id,
        tool_name="search_documentation",
        query_text=query,
        product_filter=product,
        version_filter=version,
        doc_type_filter=doc_type,
        result_count=result_count,
        top_similarity=top_similarity,
        response_length=len(response_text),
        query_tokens=query_tokens,
        response_tokens=response_tokens,
        metadata=metadata,
        duration_ms=duration_ms,
        cogs_usd=cogs,
        charge_usd=charge,
    )

    return response_text


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
    request_id = str(uuid4())
    logger.debug(
        "MCP get_api_endpoint called",
        extra={"endpoint": endpoint, "product": product, "request_id": request_id},
    )

    metadata: dict = {}
    error_msg: str | None = None
    t0 = time.perf_counter()
    try:
        async with async_session() as session:
            results = await search_endpoint(session, endpoint, product=product, metadata=metadata)
        duration_ms = round((time.perf_counter() - t0) * 1000, 1)
    except Exception as e:
        duration_ms = round((time.perf_counter() - t0) * 1000, 1)
        error_msg = f"{type(e).__name__}: {e}"
        logger.error(
            "MCP get_api_endpoint failed",
            extra={"tool": "get_api_endpoint", "duration_ms": duration_ms, "error_type": type(e).__name__, "request_id": request_id},
            exc_info=True,
        )
        await _save_mcp_request_log(
            request_id=request_id,
            tool_name="get_api_endpoint",
            query_text=endpoint,
            product_filter=product,
            duration_ms=duration_ms,
            metadata=metadata,
            error=error_msg,
        )
        raise

    result_count = len(results)
    top_similarity = results[0].get("similarity", 0.0) if results else 0.0
    log_extra = {
        "tool": "get_api_endpoint",
        "result_count": result_count,
        "duration_ms": duration_ms,
        "request_id": request_id,
    }
    if duration_ms > 10000:
        logger.warning("MCP get_api_endpoint slow", extra=log_extra)
    else:
        logger.info("MCP get_api_endpoint completed", extra=log_extra)

    await _save_search_analytics(
        source="mcp",
        tool_name="get_api_endpoint",
        query=endpoint,
        duration_ms=duration_ms,
        result_count=result_count,
        top_similarity=top_similarity,
        product_filter=product,
        tenant_id=current_tenant_id.get(),
        api_key_id=current_api_key_id.get(),
    )

    if not results:
        response_text = f"No documentation found for endpoint '{endpoint}'. Try search_documentation with a broader query."
    else:
        seen_parents: set[str] = set()
        parts: list[str] = []
        for i, r in enumerate(results, 1):
            match_type = r.get("match_type", "vector")
            meta = _format_mcp_meta(i, r)
            meta += f" [{match_type} match]"
            body = _format_mcp_body(r, seen_parents)
            parts.append(f"{meta}\n\n{body}")
        response_text = "\n\n---\n\n".join(parts)

    response_tokens = max(1, len(response_text) // 4)
    query_tokens = max(1, len(endpoint) // 4)
    await write_usage_log(
        channel="mcp",
        action="get_api_endpoint",
        request_id=request_id,
        query_text=endpoint,
        query_tokens=query_tokens,
        result_count=result_count,
        response_tokens=response_tokens,
        response_length=len(response_text),
        top_similarity=top_similarity,
        product_filter=product,
        duration_ms=duration_ms,
        embedding_ms=metadata.get("embed_ms", 0.0),
        search_ms=metadata.get("search_ms", 0.0),
        tenant_id=current_tenant_id.get(),
        api_key_id=current_api_key_id.get(),
    )

    cogs, charge = _calc_mcp_costs(metadata)
    await _save_mcp_request_log(
        request_id=request_id,
        tool_name="get_api_endpoint",
        query_text=endpoint,
        product_filter=product,
        result_count=result_count,
        top_similarity=top_similarity,
        response_length=len(response_text),
        query_tokens=query_tokens,
        response_tokens=response_tokens,
        metadata=metadata,
        duration_ms=duration_ms,
        cogs_usd=cogs,
        charge_usd=charge,
    )

    return response_text


async def tool_list_products(
    category: str | None = None,
    query: str | None = None,
) -> str:
    """List products with indexed documentation available in Lexiro.

    Call this FIRST to discover what products are available before using search_documentation.

    Products include both hardware devices (IP cameras, access controllers, intercoms, NVRs)
    and software platforms (VMS like Axxon One, PSIM, IoT platforms, SDKs).

    Args:
        category: Filter by category slug.
            Examples: "video_surveillance", "access_control", "intercom", "protocols", "software"
        query: Search products by name or manufacturer.
            Examples: "Hikvision", "Axxon", "DS-2CD"
    """
    request_id = str(uuid4())
    logger.debug("MCP list_products called", extra={"category": category, "query": query, "request_id": request_id})

    t0 = time.perf_counter()
    async with async_session() as session:
        where_clauses: list[str] = []
        params: dict = {}
        extra_joins: list[str] = []

        if category:
            where_clauses.append("p.category ILIKE '%' || :category || '%'")
            params["category"] = category
        if query:
            normalized = query.replace(" ", "").replace("-", "").replace("_", "")
            where_clauses.append(
                "(p.name ILIKE :query OR p.manufacturer ILIKE :query"
                " OR REPLACE(REPLACE(REPLACE(p.name, ' ', ''), '-', ''), '_', '') ILIKE :query_norm"
                " OR similarity(p.name, :query_raw) > 0.25)"
            )
            params["query"] = f"%{query}%"
            params["query_norm"] = f"%{normalized}%"
            params["query_raw"] = query

        where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        joins_sql = "\n".join(extra_joins)

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
            {joins_sql}
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

    await _save_search_analytics(
        source="mcp",
        tool_name="list_products",
        query=query or "",
        duration_ms=duration_ms,
        result_count=len(rows),
        tenant_id=current_tenant_id.get(),
        api_key_id=current_api_key_id.get(),
    )

    if not rows:
        if category or query:
            response_text = "No products found matching your filter. Try list_products without filters to see all available products."
        else:
            response_text = "No products indexed yet."
    else:
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
        response_text = f"Available products ({len(rows)}):\n" + "\n".join(parts)

    query_tokens = max(1, len(query) // 4) if query else 0
    await write_usage_log(
        channel="mcp",
        action="list_products",
        request_id=request_id,
        query_text=query,
        query_tokens=query_tokens,
        result_count=len(rows),
        response_length=len(response_text),
        duration_ms=duration_ms,
        cogs_usd=Decimal("0"),
        charge_usd=Decimal("0"),
        tenant_id=current_tenant_id.get(),
        api_key_id=current_api_key_id.get(),
    )

    await _save_mcp_request_log(
        request_id=request_id,
        tool_name="list_products",
        query_text=query,
        result_count=len(rows),
        response_length=len(response_text),
        query_tokens=query_tokens,
        duration_ms=duration_ms,
        cogs_usd=Decimal("0"),
        charge_usd=Decimal("0"),
    )

    return response_text


async def tool_get_document_outline(
    product: str,
    document_title: str | None = None,
) -> str:
    """Get the table of contents (heading structure) of a product's documentation.

    Use this tool to understand the structure of available documentation before diving
    into specific sections. This helps you navigate large API references and find
    the right section to read.

    Args:
        product: Product name (use list_products to discover available products).
            Examples: "HikCentral", "Axxon One", "DS-2CD2347G2-LU"
        document_title: Optional document title to narrow down to a specific document.
            If omitted, returns outlines for all documents of the product.
    """
    request_id = str(uuid4())
    logger.debug(
        "MCP get_document_outline called",
        extra={"product": product, "document_title": document_title, "request_id": request_id},
    )

    t0 = time.perf_counter()
    async with async_session() as session:
        product_id, resolved_name = await resolve_product(session, product)

        if product_id is None:
            duration_ms = round((time.perf_counter() - t0) * 1000, 1)
            return f"No product matching '{product}' found. Use list_products to see available products."

        where_clauses = ["d.status = 'ready'", "d.product_id = :product_id"]
        params: dict = {"product_id": product_id}

        if document_title:
            where_clauses.append("d.title ILIKE '%' || :doc_title || '%'")
            params["doc_title"] = document_title

        where_sql = " AND ".join(where_clauses)

        sql = text(f"""
            SELECT DISTINCT
                d.id AS document_id,
                d.title AS doc_title,
                c.heading_path,
                c.heading_level,
                c.doc_type,
                c.chunk_index
            FROM chunks c
            JOIN documents d ON c.document_id = d.id
            JOIN products p ON d.product_id = p.id
            WHERE {where_sql}
            ORDER BY d.id, c.chunk_index
        """)

        result = await session.execute(sql, params)
        rows = result.mappings().all()

    duration_ms = round((time.perf_counter() - t0) * 1000, 1)
    logger.info(
        "MCP get_document_outline completed",
        extra={"tool": "get_document_outline", "result_count": len(rows), "duration_ms": duration_ms, "request_id": request_id},
    )

    if not rows:
        response_text = f"No documentation found for product '{product}'. Use list_products to see available products."
    else:
        docs: dict[int, dict] = {}
        for row in rows:
            doc_id = row["document_id"]
            if doc_id not in docs:
                docs[doc_id] = {"title": row["doc_title"], "headings": []}
            indent = "  " * max(0, row["heading_level"] - 1)
            type_tag = f" [{row['doc_type']}]" if row["doc_type"] and row["doc_type"] != "other" else ""
            docs[doc_id]["headings"].append(f"{indent}- {row['heading_path']}{type_tag}")

        parts: list[str] = []
        for doc_id, doc in docs.items():
            seen: set[str] = set()
            unique_headings: list[str] = []
            for h in doc["headings"]:
                if h not in seen:
                    seen.add(h)
                    unique_headings.append(h)
            parts.append(f"## {doc['title']} (doc_id: {doc_id})\n" + "\n".join(unique_headings))
        response_text = "\n\n".join(parts)

    await _save_search_analytics(
        source="mcp",
        tool_name="get_document_outline",
        query=product,
        duration_ms=duration_ms,
        result_count=len(rows),
        product_filter=product,
        tenant_id=current_tenant_id.get(),
        api_key_id=current_api_key_id.get(),
    )

    await write_usage_log(
        channel="mcp",
        action="get_document_outline",
        request_id=request_id,
        query_text=product,
        query_tokens=0,
        result_count=len(rows),
        response_length=len(response_text),
        duration_ms=duration_ms,
        cogs_usd=Decimal("0"),
        charge_usd=Decimal("0"),
        tenant_id=current_tenant_id.get(),
        api_key_id=current_api_key_id.get(),
    )

    await _save_mcp_request_log(
        request_id=request_id,
        tool_name="get_document_outline",
        query_text=product,
        product_filter=product,
        result_count=len(rows),
        response_length=len(response_text),
        duration_ms=duration_ms,
        cogs_usd=Decimal("0"),
        charge_usd=Decimal("0"),
    )

    return response_text


async def tool_get_section(
    document_id: int,
    heading: str,
) -> str:
    """Get the full text of a specific section from a document.

    Use this after search_documentation or get_document_outline when you need the
    complete, untruncated content of a section. This is especially useful when a search
    result was truncated or you need surrounding context (sibling/child sections).

    Args:
        document_id: The document ID (returned by search_documentation and get_document_outline).
        heading: The heading path to retrieve. Partial match supported.
            Examples: "Authentication", "POST /api/v1/doors", "Error Codes"
    """
    request_id = str(uuid4())
    logger.debug(
        "MCP get_section called",
        extra={"document_id": document_id, "heading": heading, "request_id": request_id},
    )

    t0 = time.perf_counter()
    async with async_session() as session:
        sql = text("""
            SELECT
                c.content,
                c.parent_content,
                c.heading_path,
                c.heading_level,
                c.doc_type,
                c.entities,
                c.chunk_index,
                d.title AS doc_title,
                p.name AS product_name,
                fw.version AS firmware_version
            FROM chunks c
            JOIN documents d ON c.document_id = d.id
            JOIN products p ON d.product_id = p.id
            JOIN firmware_versions fw ON d.firmware_version_id = fw.id
            WHERE c.document_id = :doc_id
              AND c.heading_path ILIKE '%' || :heading || '%'
            ORDER BY c.chunk_index
            LIMIT 20
        """)
        result = await session.execute(sql, {"doc_id": document_id, "heading": heading})
        rows = result.mappings().all()

    duration_ms = round((time.perf_counter() - t0) * 1000, 1)
    logger.info(
        "MCP get_section completed",
        extra={"tool": "get_section", "result_count": len(rows), "duration_ms": duration_ms, "request_id": request_id},
    )

    if not rows:
        response_text = (
            f"No section matching '{heading}' found in document {document_id}. "
            "Use get_document_outline to see available sections."
        )
    else:
        first = rows[0]
        header = (
            f"{first['product_name']} | {first['firmware_version']} | "
            f"{first['doc_title']}"
        )
        seen_parents: set[str] = set()
        parts: list[str] = []
        for row in rows:
            type_tag = f" [{row['doc_type']}]" if row["doc_type"] and row["doc_type"] != "other" else ""
            meta = f"### {row['heading_path']}{type_tag}"
            body = _format_mcp_body(dict(row), seen_parents)
            parts.append(f"{meta}\n\n{body}")
        response_text = f"# {header}\n\n" + "\n\n---\n\n".join(parts)

    response_tokens = max(1, len(response_text) // 4)
    await _save_search_analytics(
        source="mcp",
        tool_name="get_section",
        query=heading,
        duration_ms=duration_ms,
        result_count=len(rows),
        tenant_id=current_tenant_id.get(),
        api_key_id=current_api_key_id.get(),
    )

    await write_usage_log(
        channel="mcp",
        action="get_section",
        request_id=request_id,
        query_text=heading,
        query_tokens=max(1, len(heading) // 4),
        result_count=len(rows),
        response_tokens=response_tokens,
        response_length=len(response_text),
        duration_ms=duration_ms,
        cogs_usd=Decimal("0"),
        charge_usd=Decimal("0"),
        tenant_id=current_tenant_id.get(),
        api_key_id=current_api_key_id.get(),
    )

    await _save_mcp_request_log(
        request_id=request_id,
        tool_name="get_section",
        query_text=heading,
        result_count=len(rows),
        response_length=len(response_text),
        query_tokens=max(1, len(heading) // 4),
        response_tokens=response_tokens,
        duration_ms=duration_ms,
        cogs_usd=Decimal("0"),
        charge_usd=Decimal("0"),
    )

    return response_text


async def tool_get_code_examples(
    product: str,
    topic: str | None = None,
    language: str | None = None,
) -> str:
    """Find code examples and integration patterns from product documentation.

    Use this when you need working code snippets, SDK usage patterns, or integration
    examples for a specific product. Results include code blocks extracted from
    documentation with surrounding context.

    Args:
        product: Product name. Examples: "HikCentral", "Axxon One"
        topic: What the code example should demonstrate.
            Examples: "authentication", "door control", "camera registration",
            "event subscription", "PTZ control"
        language: Programming language filter.
            Examples: "python", "csharp", "javascript", "curl", "xml", "json"
    """
    request_id = str(uuid4())
    logger.debug(
        "MCP get_code_examples called",
        extra={"product": product, "topic": topic, "language": language, "request_id": request_id},
    )

    t0 = time.perf_counter()
    async with async_session() as session:
        product_id, resolved_name = await resolve_product(session, product)

        if product_id is None:
            return f"No product matching '{product}' found. Use list_products to see available products."

        where_clauses = [
            "d.status = 'ready'",
            "d.product_id = :product_id",
            "(c.doc_type IN ('example', 'api_reference') OR c.content LIKE '%```%' OR c.content LIKE '%<code%' OR c.content LIKE '%curl %')",
        ]
        params: dict = {"product_id": product_id}

        if topic:
            where_clauses.append(
                "(c.heading_path ILIKE '%' || :topic || '%' OR c.content ILIKE '%' || :topic || '%')"
            )
            params["topic"] = topic

        if language:
            where_clauses.append(
                "(c.content ILIKE '%```' || :lang || '%' OR c.content ILIKE '%' || :lang || '%')"
            )
            params["lang"] = language

        where_sql = " AND ".join(where_clauses)

        sql = text(f"""
            SELECT
                c.document_id,
                c.content,
                c.parent_content,
                c.heading_path,
                c.heading_level,
                c.doc_type,
                c.entities,
                d.title AS doc_title,
                p.name AS product_name,
                fw.version AS firmware_version
            FROM chunks c
            JOIN documents d ON c.document_id = d.id
            JOIN products p ON d.product_id = p.id
            JOIN firmware_versions fw ON d.firmware_version_id = fw.id
            WHERE {where_sql}
            ORDER BY
                CASE WHEN c.doc_type = 'example' THEN 0 ELSE 1 END,
                c.chunk_index
            LIMIT 15
        """)

        result = await session.execute(sql, params)
        rows = result.mappings().all()

    duration_ms = round((time.perf_counter() - t0) * 1000, 1)
    result_count = len(rows)
    logger.info(
        "MCP get_code_examples completed",
        extra={"tool": "get_code_examples", "result_count": result_count, "duration_ms": duration_ms, "request_id": request_id},
    )

    if not rows:
        fallback_hint = ""
        if topic:
            fallback_hint = f" Try search_documentation with query '{topic} example code'."
        response_text = f"No code examples found for '{product}'.{fallback_hint}"
    else:
        seen_parents: set[str] = set()
        parts: list[str] = []
        for i, row in enumerate(rows, 1):
            meta = _format_mcp_meta(i, dict(row))
            body = _format_mcp_body(dict(row), seen_parents)
            parts.append(f"{meta}\n\n{body}")
        response_text = "\n\n---\n\n".join(parts)

    response_tokens = max(1, len(response_text) // 4)
    query_text = f"{product} {topic or ''} {language or ''}".strip()
    query_tokens = max(1, len(query_text) // 4)

    await _save_search_analytics(
        source="mcp",
        tool_name="get_code_examples",
        query=query_text,
        duration_ms=duration_ms,
        result_count=result_count,
        product_filter=product,
        tenant_id=current_tenant_id.get(),
        api_key_id=current_api_key_id.get(),
    )

    await write_usage_log(
        channel="mcp",
        action="get_code_examples",
        request_id=request_id,
        query_text=query_text,
        query_tokens=query_tokens,
        result_count=result_count,
        response_tokens=response_tokens,
        response_length=len(response_text),
        duration_ms=duration_ms,
        product_filter=product,
        cogs_usd=Decimal("0"),
        charge_usd=Decimal("0"),
        tenant_id=current_tenant_id.get(),
        api_key_id=current_api_key_id.get(),
    )

    await _save_mcp_request_log(
        request_id=request_id,
        tool_name="get_code_examples",
        query_text=query_text,
        product_filter=product,
        result_count=result_count,
        response_length=len(response_text),
        query_tokens=query_tokens,
        response_tokens=response_tokens,
        duration_ms=duration_ms,
        cogs_usd=Decimal("0"),
        charge_usd=Decimal("0"),
    )

    return response_text


async def tool_list_documents(
    product: str,
    doc_type: str | None = None,
) -> str:
    """List all documents indexed for a specific product.

    Use this to see what documentation is available before searching. Returns a compact
    list with document IDs, titles, chunk counts, and doc types — much lighter than
    get_document_outline for products with many documents.

    The returned document IDs can be used with get_section and get_document_outline
    (with document_title filter) to drill into specific documents.

    Args:
        product: Product name. Examples: "HikCentral", "Axxon One", "Elsys-SDK"
        doc_type: Optional filter by documentation type.
            Examples: "api_reference", "guide", "user_guide", "example", "configuration"
    """
    request_id = str(uuid4())
    logger.debug("MCP list_documents called", extra={"product": product, "doc_type": doc_type, "request_id": request_id})

    t0 = time.perf_counter()
    async with async_session() as session:
        product_id, resolved_name = await resolve_product(session, product)

        if product_id is None:
            return f"No product matching '{product}' found. Use list_products to see available products."

        where_clauses = ["d.status = 'ready'", "d.product_id = :product_id"]
        params: dict = {"product_id": product_id}

        if doc_type:
            where_clauses.append("c.doc_type = :doc_type")
            params["doc_type"] = doc_type

        where_sql = " AND ".join(where_clauses)

        sql = text(f"""
            SELECT
                d.id AS document_id,
                d.title,
                d.format,
                d.total_chunks,
                fw.version AS firmware_version,
                COUNT(c.id) AS chunk_count,
                COALESCE(
                    STRING_AGG(DISTINCT c.doc_type, ', ')
                    FILTER (WHERE c.doc_type IS NOT NULL AND c.doc_type != 'other'),
                    'other'
                ) AS doc_types
            FROM documents d
            JOIN firmware_versions fw ON d.firmware_version_id = fw.id
            LEFT JOIN chunks c ON c.document_id = d.id
            WHERE {where_sql}
            GROUP BY d.id, d.title, d.format, d.total_chunks, fw.version
            ORDER BY d.title
        """)

        result = await session.execute(sql, params)
        rows = result.mappings().all()

    duration_ms = round((time.perf_counter() - t0) * 1000, 1)
    result_count = len(rows)
    logger.info(
        "MCP list_documents completed",
        extra={"tool": "list_documents", "result_count": result_count, "duration_ms": duration_ms, "request_id": request_id},
    )

    if not rows:
        filter_hint = f" with doc_type='{doc_type}'" if doc_type else ""
        response_text = f"No documents found for '{resolved_name}'{filter_hint}."
    else:
        parts: list[str] = []
        for row in rows:
            types = row["doc_types"]
            type_tag = f" [{types}]" if types and types != "other" else ""
            parts.append(
                f"- [doc_id: {row['document_id']}] {row['title']}"
                f" (v{row['firmware_version']}, {row['chunk_count']} chunks){type_tag}"
            )
        response_text = f"Documents for {resolved_name} ({result_count}):\n" + "\n".join(parts)

    await _save_search_analytics(
        source="mcp", tool_name="list_documents", query=product,
        duration_ms=duration_ms, result_count=result_count, product_filter=product,
        tenant_id=current_tenant_id.get(), api_key_id=current_api_key_id.get(),
    )
    await write_usage_log(
        channel="mcp", action="list_documents", request_id=request_id,
        query_text=product, query_tokens=0, result_count=result_count,
        response_length=len(response_text), duration_ms=duration_ms,
        cogs_usd=Decimal("0"), charge_usd=Decimal("0"),
        tenant_id=current_tenant_id.get(), api_key_id=current_api_key_id.get(),
    )
    await _save_mcp_request_log(
        request_id=request_id, tool_name="list_documents",
        query_text=product, product_filter=product, result_count=result_count,
        response_length=len(response_text), duration_ms=duration_ms,
        cogs_usd=Decimal("0"), charge_usd=Decimal("0"),
    )

    return response_text


async def tool_grep_docs(
    pattern: str,
    product: str | None = None,
    document_id: int | None = None,
    include_context: bool = True,
) -> str:
    """Exact text search across documentation content (case-insensitive substring match).

    Use this instead of search_documentation when you need to find exact strings that
    semantic search handles poorly: IP addresses, error codes, parameter names, specific
    URLs, configuration keys, protocol commands, hex values, etc.

    Args:
        pattern: The exact text to search for (case-insensitive).
            Examples: "192.168.1", "error 0x8004", "Content-Type: application/xml",
            "/ISAPI/", "doControl", "rtsp://", "Basic realm="
        product: Optional product filter. Examples: "HikCentral", "Axxon One"
        document_id: Optional document ID to limit search to a specific document.
        include_context: If true, returns surrounding heading path and more content.
            Set to false for compact output when expecting many matches. Default: true.
    """
    request_id = str(uuid4())
    logger.debug(
        "MCP grep_docs called",
        extra={"pattern": pattern, "product": product, "document_id": document_id, "request_id": request_id},
    )

    t0 = time.perf_counter()
    async with async_session() as session:
        where_clauses = [
            "d.status = 'ready'",
            "c.content ILIKE '%' || :pattern || '%'",
        ]
        params: dict = {"pattern": pattern}

        if document_id is not None:
            where_clauses.append("c.document_id = :doc_id")
            params["doc_id"] = document_id
        elif product:
            product_id, _ = await resolve_product(session, product)
            if product_id:
                where_clauses.append("d.product_id = :product_id")
                params["product_id"] = product_id

        where_sql = " AND ".join(where_clauses)

        if include_context:
            select_cols = """
                c.document_id,
                c.content,
                c.heading_path,
                c.heading_level,
                c.doc_type,
                d.title AS doc_title,
                p.name AS product_name,
                fw.version AS firmware_version
            """
        else:
            select_cols = """
                c.document_id,
                c.heading_path,
                d.title AS doc_title,
                p.name AS product_name
            """

        sql = text(f"""
            SELECT {select_cols}
            FROM chunks c
            JOIN documents d ON c.document_id = d.id
            JOIN products p ON d.product_id = p.id
            JOIN firmware_versions fw ON d.firmware_version_id = fw.id
            WHERE {where_sql}
            ORDER BY p.name, d.title, c.chunk_index
            LIMIT 30
        """)

        result = await session.execute(sql, params)
        rows = result.mappings().all()

    duration_ms = round((time.perf_counter() - t0) * 1000, 1)
    result_count = len(rows)
    logger.info(
        "MCP grep_docs completed",
        extra={"tool": "grep_docs", "result_count": result_count, "duration_ms": duration_ms, "request_id": request_id},
    )

    if not rows:
        response_text = f"No matches for '{pattern}'."
        if not product:
            response_text += " Try narrowing with a product filter."
    elif include_context:
        parts: list[str] = []
        for i, row in enumerate(rows, 1):
            content = row["content"]
            lower_content = content.lower()
            lower_pattern = pattern.lower()
            pos = lower_content.find(lower_pattern)
            if pos >= 0:
                start = max(0, pos - 120)
                end = min(len(content), pos + len(pattern) + 120)
                snippet = content[start:end]
                if start > 0:
                    snippet = "..." + snippet
                if end < len(content):
                    snippet = snippet + "..."
            else:
                snippet = content[:250] + ("..." if len(content) > 250 else "")

            type_tag = f" [{row['doc_type']}]" if row.get("doc_type") and row["doc_type"] != "other" else ""
            meta = (
                f"[{i}] {row['product_name']} | {row['firmware_version']} | "
                f"{row['doc_title']} > {row['heading_path']}{type_tag}"
            )
            parts.append(f"{meta}\n{snippet}")
        response_text = f"Found {result_count} matches for '{pattern}':\n\n" + "\n\n---\n\n".join(parts)
    else:
        parts = []
        for row in rows:
            parts.append(f"- {row['product_name']} | {row['doc_title']} > {row['heading_path']} (doc_id: {row['document_id']})")
        response_text = f"Found {result_count} matches for '{pattern}':\n" + "\n".join(parts)

    response_tokens = max(1, len(response_text) // 4)
    query_tokens = max(1, len(pattern) // 4)

    await _save_search_analytics(
        source="mcp", tool_name="grep_docs", query=pattern,
        duration_ms=duration_ms, result_count=result_count, product_filter=product,
        tenant_id=current_tenant_id.get(), api_key_id=current_api_key_id.get(),
    )
    await write_usage_log(
        channel="mcp", action="grep_docs", request_id=request_id,
        query_text=pattern, query_tokens=query_tokens, result_count=result_count,
        response_tokens=response_tokens, response_length=len(response_text),
        duration_ms=duration_ms, product_filter=product,
        cogs_usd=Decimal("0"), charge_usd=Decimal("0"),
        tenant_id=current_tenant_id.get(), api_key_id=current_api_key_id.get(),
    )
    await _save_mcp_request_log(
        request_id=request_id, tool_name="grep_docs",
        query_text=pattern, product_filter=product, result_count=result_count,
        response_length=len(response_text), query_tokens=query_tokens,
        response_tokens=response_tokens, duration_ms=duration_ms,
        cogs_usd=Decimal("0"), charge_usd=Decimal("0"),
    )

    return response_text


async def tool_get_product_info(
    product: str,
) -> str:
    """Get a detailed summary about a specific product in the Lexiro knowledge base.

    Returns: manufacturer, category, available firmware/API versions, document count,
    total chunks, doc types breakdown, and top-level documentation topics.

    Use this as a first step before searching, to understand what documentation is
    available and how it's organized.

    Args:
        product: Product name. Examples: "HikCentral", "Axxon One", "Elsys-SDK"
    """
    request_id = str(uuid4())
    logger.debug("MCP get_product_info called", extra={"product": product, "request_id": request_id})

    t0 = time.perf_counter()
    async with async_session() as session:
        product_id, resolved_name = await resolve_product(session, product)

        if product_id is None:
            return f"No product matching '{product}' found. Use list_products to see available products."

        info_sql = text("""
            SELECT
                p.name,
                p.manufacturer,
                p.category,
                COALESCE(STRING_AGG(DISTINCT fw.version, ', ' ORDER BY fw.version), '') AS versions,
                COUNT(DISTINCT d.id) FILTER (WHERE d.status = 'ready') AS doc_count,
                COUNT(c.id) FILTER (WHERE d.status = 'ready') AS chunk_count,
                COALESCE(
                    STRING_AGG(DISTINCT c.doc_type, ', ')
                    FILTER (WHERE c.doc_type IS NOT NULL AND c.doc_type != 'other' AND d.status = 'ready'),
                    ''
                ) AS doc_types
            FROM products p
            LEFT JOIN firmware_versions fw ON fw.product_id = p.id
            LEFT JOIN documents d ON d.product_id = p.id
            LEFT JOIN chunks c ON c.document_id = d.id
            WHERE p.id = :pid
            GROUP BY p.id, p.name, p.manufacturer, p.category
        """)
        info_row = (await session.execute(info_sql, {"pid": product_id})).mappings().first()

        topics_sql = text("""
            SELECT
                c.doc_type,
                COUNT(*) AS cnt
            FROM chunks c
            JOIN documents d ON c.document_id = d.id
            WHERE d.product_id = :pid AND d.status = 'ready'
              AND c.doc_type IS NOT NULL AND c.doc_type != 'other'
            GROUP BY c.doc_type
            ORDER BY cnt DESC
        """)
        type_rows = (await session.execute(topics_sql, {"pid": product_id})).mappings().all()

        headings_sql = text("""
            SELECT DISTINCT c.heading_path
            FROM chunks c
            JOIN documents d ON c.document_id = d.id
            WHERE d.product_id = :pid AND d.status = 'ready'
              AND c.heading_level = 1
            ORDER BY c.heading_path
            LIMIT 30
        """)
        heading_rows = (await session.execute(headings_sql, {"pid": product_id})).mappings().all()

    duration_ms = round((time.perf_counter() - t0) * 1000, 1)
    logger.info("MCP get_product_info completed", extra={"tool": "get_product_info", "duration_ms": duration_ms, "request_id": request_id})

    if not info_row:
        return f"No data found for product ID {product_id}."

    r = info_row
    lines: list[str] = [
        f"# {r['name']}",
        f"- Manufacturer: {r['manufacturer'] or 'N/A'}",
        f"- Category: {r['category'] or 'N/A'}",
        f"- Versions: {r['versions'] or 'N/A'}",
        f"- Documents: {r['doc_count']}",
        f"- Chunks: {r['chunk_count']}",
    ]

    if type_rows:
        lines.append("\n## Documentation types")
        for tr in type_rows:
            lines.append(f"- {tr['doc_type']}: {tr['cnt']} chunks")

    if heading_rows:
        lines.append("\n## Top-level topics")
        for hr in heading_rows:
            lines.append(f"- {hr['heading_path']}")

    response_text = "\n".join(lines)

    await _save_search_analytics(
        source="mcp", tool_name="get_product_info", query=product,
        duration_ms=duration_ms, result_count=1, product_filter=product,
        tenant_id=current_tenant_id.get(), api_key_id=current_api_key_id.get(),
    )
    await write_usage_log(
        channel="mcp", action="get_product_info", request_id=request_id,
        query_text=product, query_tokens=0, result_count=1,
        response_length=len(response_text), duration_ms=duration_ms,
        cogs_usd=Decimal("0"), charge_usd=Decimal("0"),
        tenant_id=current_tenant_id.get(), api_key_id=current_api_key_id.get(),
    )
    await _save_mcp_request_log(
        request_id=request_id, tool_name="get_product_info",
        query_text=product, product_filter=product, result_count=1,
        response_length=len(response_text), duration_ms=duration_ms,
        cogs_usd=Decimal("0"), charge_usd=Decimal("0"),
    )

    return response_text
