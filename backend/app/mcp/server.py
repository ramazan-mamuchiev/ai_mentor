"""MCP tools for IPCodex: search, get_endpoint, list_products, ingest."""

import logging
import time

from sqlalchemy import func, select

from app.database import async_session
from app.ingestion.pipeline import ingest_file, ingest_url
from app.models import Chunk, Product, Document, FirmwareVersion
from app.search.service import search_documents, search_endpoint

logger = logging.getLogger(__name__)


async def tool_search_documentation(
    query: str,
    product: str | None = None,
    version: str | None = None,
    limit: int = 5,
) -> str:
    """Search product API documentation by semantic similarity.

    Returns the most relevant chunks for your query.
    Use this to find API endpoints, parameters, data formats, and examples.

    Args:
        query: Natural language search query (e.g. "how to open a door via API")
        product: Optional product name filter (e.g. "HikCentral")
        version: Optional firmware version filter (e.g. "V2.6.1")
        limit: Number of results to return (1-20, default 5)
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
        return "No results found. Try a different query or check that documents have been ingested."

    parts: list[str] = []
    for i, r in enumerate(results, 1):
        header = f"## Result {i} (similarity: {r['similarity']})"
        meta = f"**Product:** {r['product_name']} | **Version:** {r['firmware_version']} | **Doc:** {r['doc_title']}"
        path = f"**Section:** {r['heading_path']}"
        parts.append(f"{header}\n{meta}\n{path}\n\n{r['content']}")

    return "\n\n---\n\n".join(parts)


async def tool_get_api_endpoint(
    endpoint: str,
    product: str | None = None,
) -> str:
    """Get detailed documentation for a specific API endpoint path.

    Use this when you know the exact endpoint path you need.

    Args:
        endpoint: API endpoint path (e.g. "/acs/v1/door/doControl")
        product: Optional product name filter
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
        meta = f"**Product:** {r['product_name']} | **Version:** {r['firmware_version']} | **Doc:** {r['doc_title']}"
        path = f"**Section:** {r['heading_path']}"
        match = f"**Match type:** {r.get('match_type', 'vector')}"
        parts.append(f"{meta}\n{path}\n{match}\n\n{r['content']}")

    return "\n\n---\n\n".join(parts)


async def tool_list_products() -> str:
    """List all indexed products with their firmware versions and document counts.

    Use this to see what documentation is available before searching.
    """
    logger.debug("MCP list_products called")

    t0 = time.perf_counter()
    async with async_session() as session:
        result = await session.execute(
            select(
                Product.id,
                Product.name,
                Product.manufacturer,
                Product.model,
                Product.category,
            ).order_by(Product.name)
        )
        products = result.all()

        if not products:
            duration_ms = round((time.perf_counter() - t0) * 1000, 1)
            logger.info(
                "MCP list_products completed",
                extra={"tool": "list_products", "result_count": 0, "duration_ms": duration_ms},
            )
            return "No products indexed yet. Use ingest_document to add documentation."

        parts: list[str] = []
        for prod in products:
            fw_result = await session.execute(
                select(FirmwareVersion.version).where(
                    FirmwareVersion.product_id == prod.id
                ).order_by(FirmwareVersion.version)
            )
            versions = [r[0] for r in fw_result.all()]

            doc_count_result = await session.execute(
                select(func.count(Document.id)).where(
                    Document.product_id == prod.id,
                    Document.status == "ready",
                )
            )
            doc_count = doc_count_result.scalar() or 0

            chunk_count_result = await session.execute(
                select(func.count(Chunk.id))
                .join(Document, Chunk.document_id == Document.id)
                .where(Document.product_id == prod.id, Document.status == "ready")
            )
            chunk_count = chunk_count_result.scalar() or 0

            info = f"- **{prod.name}**"
            if prod.manufacturer:
                info += f" ({prod.manufacturer})"
            info += f"\n  Versions: {', '.join(versions) if versions else 'none'}"
            info += f"\n  Documents: {doc_count} | Chunks: {chunk_count}"
            parts.append(info)

    duration_ms = round((time.perf_counter() - t0) * 1000, 1)
    logger.info(
        "MCP list_products completed",
        extra={"tool": "list_products", "result_count": len(products), "duration_ms": duration_ms},
    )
    return f"**Indexed products ({len(products)}):**\n\n" + "\n\n".join(parts)


async def tool_ingest_document(
    file_path: str,
    product_name: str,
    firmware_version: str = "1.0",
    manufacturer: str = "",
    format: str = "auto",
    ocr_mode: str = "auto",
    ocr_languages: str = "en",
) -> str:
    """Upload and index a documentation file for semantic search.

    Supported formats: Markdown (.md), Swagger/OpenAPI (.yaml, .json), PDF (.pdf).
    Format is auto-detected by default. PDF files support optional OCR for scanned pages.

    Args:
        file_path: Absolute path to the documentation file on the server
        product_name: Name of the product (e.g. "HikCentral Professional")
        firmware_version: Firmware/API version (e.g. "V2.6.1")
        manufacturer: Product manufacturer (e.g. "Hikvision")
        format: File format — "auto", "markdown", "swagger", or "pdf"
        ocr_mode: OCR mode for PDFs — "auto" (OCR pages with images), "always", or "off"
        ocr_languages: Comma-separated OCR language codes (e.g. "en", "en,ru")
    """
    import os

    file_size = 0
    try:
        file_size = os.path.getsize(file_path)
    except OSError:
        pass

    logger.debug(
        "MCP ingest_document called",
        extra={
            "file_path": file_path, "product_name": product_name,
            "firmware_version": firmware_version, "format": format,
            "file_size_bytes": file_size, "ocr_mode": ocr_mode,
        },
    )

    t0 = time.perf_counter()
    try:
        async with async_session() as session:
            result = await ingest_file(
                session=session,
                file_path=file_path,
                product_name=product_name,
                firmware_version=firmware_version,
                manufacturer=manufacturer,
                fmt=format,
                ocr_mode=ocr_mode,
                ocr_languages=ocr_languages,
            )
        duration_ms = round((time.perf_counter() - t0) * 1000, 1)
    except Exception as e:
        duration_ms = round((time.perf_counter() - t0) * 1000, 1)
        logger.error(
            "MCP ingest_document failed",
            extra={
                "tool": "ingest_document", "duration_ms": duration_ms,
                "error_type": type(e).__name__, "file_size_bytes": file_size,
            },
            exc_info=True,
        )
        raise

    log_extra = {
        "tool": "ingest_document",
        "status": result["status"],
        "duration_ms": duration_ms,
        "file_size_bytes": file_size,
        "chunks": result.get("chunks", 0),
    }
    if result["status"] == "error":
        logger.error("MCP ingest_document error", extra=log_extra)
    elif duration_ms > 10000:
        logger.warning("MCP ingest_document slow", extra=log_extra)
    else:
        logger.info("MCP ingest_document completed", extra=log_extra)

    if result["status"] == "ok":
        lines = [
            "Ingested successfully.",
            f"Product: {result['product']} (fw: {result['firmware_version']})",
            f"Format: {result['format']}",
            f"Chunks: {result['chunks']}",
            f"Duration: {result['duration_sec']}s",
        ]
        meta = result.get("convert_metadata", {})
        if meta.get("ocr_applied"):
            lines.append(f"OCR: applied ({meta.get('ocr_stats', {}).get('images_ocr_ok', 0)} images recognized)")
        if meta.get("endpoints"):
            lines.append(f"Endpoints: {meta['endpoints']} | Models: {meta.get('models', 0)}")
        return "\n".join(lines)
    elif result["status"] == "skipped":
        return result.get("message", "Document already ingested (same hash).")
    else:
        return f"Ingestion failed: {result.get('error', 'unknown error')}"


async def tool_ingest_url(
    url: str,
    product_name: str,
    firmware_version: str = "1.0",
    manufacturer: str = "",
) -> str:
    """Ingest documentation from a URL for semantic search.

    Auto-detects content type:
    - Direct Swagger/OpenAPI spec (JSON/YAML) — parsed into structured docs
    - Swagger UI / ReDoc page — spec URL extracted from HTML, then parsed
    - Generic web page — rendered via headless browser fallback

    Args:
        url: HTTP(S) URL pointing to API docs, Swagger UI, or a raw OpenAPI spec
        product_name: Name of the product (e.g. "HikCentral Professional")
        firmware_version: Firmware/API version (e.g. "V2.6.1")
        manufacturer: Product manufacturer (e.g. "Hikvision")
    """
    logger.debug(
        "MCP ingest_url called",
        extra={"url": url, "product_name": product_name, "firmware_version": firmware_version},
    )

    t0 = time.perf_counter()
    try:
        async with async_session() as session:
            result = await ingest_url(
                session=session,
                url=url,
                product_name=product_name,
                firmware_version=firmware_version,
                manufacturer=manufacturer,
            )
        duration_ms = round((time.perf_counter() - t0) * 1000, 1)
    except Exception as e:
        duration_ms = round((time.perf_counter() - t0) * 1000, 1)
        logger.error(
            "MCP ingest_url failed",
            extra={
                "tool": "ingest_url", "duration_ms": duration_ms,
                "error_type": type(e).__name__,
            },
            exc_info=True,
        )
        raise

    log_extra = {
        "tool": "ingest_url",
        "status": result["status"],
        "duration_ms": duration_ms,
        "chunks": result.get("chunks", 0),
    }
    if result["status"] == "error":
        logger.error("MCP ingest_url error", extra=log_extra)
    elif duration_ms > 10000:
        logger.warning("MCP ingest_url slow", extra=log_extra)
    else:
        logger.info("MCP ingest_url completed", extra=log_extra)

    if result["status"] == "ok":
        detection = result.get("detection_method", "unknown")
        method_label = {
            "direct_openapi_spec": "Direct OpenAPI spec",
            "swagger_ui_extracted": "Extracted from Swagger UI",
            "crawl4ai_fallback": "Web page (Crawl4AI)",
            "raw_html_fallback": "Raw HTML",
        }.get(detection, detection)

        lines = [
            "Ingested successfully from URL.",
            f"Product: {result['product']} (fw: {result['firmware_version']})",
            f"Detection: {method_label}",
            f"Chunks: {result['chunks']}",
            f"Duration: {result['duration_sec']}s",
        ]
        meta = result.get("convert_metadata", {})
        if meta.get("endpoints"):
            lines.append(f"Endpoints: {meta['endpoints']} | Models: {meta.get('models', 0)}")
        return "\n".join(lines)
    elif result["status"] == "skipped":
        return result.get("message", "Content already ingested (same hash).")
    else:
        return f"URL ingestion failed: {result.get('error', 'unknown error')}"
