"""MCP tools for IPCodex: search, get_endpoint, list_devices, ingest."""

import logging

from sqlalchemy import func, select

from app.database import async_session
from app.ingestion.pipeline import ingest_file
from app.models import Chunk, Device, Document, FirmwareVersion
from app.search.service import search_documents, search_endpoint

logger = logging.getLogger(__name__)


async def tool_search_documentation(
    query: str,
    device: str | None = None,
    version: str | None = None,
    limit: int = 5,
) -> str:
    """Search device API documentation by semantic similarity.

    Returns the most relevant chunks for your query.
    Use this to find API endpoints, parameters, data formats, and examples.

    Args:
        query: Natural language search query (e.g. "how to open a door via API")
        device: Optional device name filter (e.g. "HikCentral")
        version: Optional firmware version filter (e.g. "V2.6.1")
        limit: Number of results to return (1-20, default 5)
    """
    limit = max(1, min(limit, 20))

    async with async_session() as session:
        results = await search_documents(session, query, device=device, version=version, limit=limit)

    if not results:
        return "No results found. Try a different query or check that documents have been ingested."

    parts: list[str] = []
    for i, r in enumerate(results, 1):
        header = f"## Result {i} (similarity: {r['similarity']})"
        meta = f"**Device:** {r['device_name']} | **Version:** {r['firmware_version']} | **Doc:** {r['doc_title']}"
        path = f"**Section:** {r['heading_path']}"
        parts.append(f"{header}\n{meta}\n{path}\n\n{r['content']}")

    return "\n\n---\n\n".join(parts)


async def tool_get_api_endpoint(
    endpoint: str,
    device: str | None = None,
) -> str:
    """Get detailed documentation for a specific API endpoint path.

    Use this when you know the exact endpoint path you need.

    Args:
        endpoint: API endpoint path (e.g. "/acs/v1/door/doControl")
        device: Optional device name filter
    """
    async with async_session() as session:
        results = await search_endpoint(session, endpoint, device=device)

    if not results:
        return f"No documentation found for endpoint '{endpoint}'. Try search_documentation with a broader query."

    parts: list[str] = []
    for r in results:
        meta = f"**Device:** {r['device_name']} | **Version:** {r['firmware_version']} | **Doc:** {r['doc_title']}"
        path = f"**Section:** {r['heading_path']}"
        match = f"**Match type:** {r.get('match_type', 'vector')}"
        parts.append(f"{meta}\n{path}\n{match}\n\n{r['content']}")

    return "\n\n---\n\n".join(parts)


async def tool_list_devices() -> str:
    """List all indexed devices with their firmware versions and document counts.

    Use this to see what documentation is available before searching.
    """
    async with async_session() as session:
        result = await session.execute(
            select(
                Device.id,
                Device.name,
                Device.manufacturer,
                Device.model,
                Device.category,
            ).order_by(Device.name)
        )
        devices = result.all()

        if not devices:
            return "No devices indexed yet. Use ingest_document to add documentation."

        parts: list[str] = []
        for dev in devices:
            fw_result = await session.execute(
                select(FirmwareVersion.version).where(
                    FirmwareVersion.device_id == dev.id
                ).order_by(FirmwareVersion.version)
            )
            versions = [r[0] for r in fw_result.all()]

            doc_count_result = await session.execute(
                select(func.count(Document.id)).where(
                    Document.device_id == dev.id,
                    Document.status == "ready",
                )
            )
            doc_count = doc_count_result.scalar() or 0

            chunk_count_result = await session.execute(
                select(func.count(Chunk.id))
                .join(Document, Chunk.document_id == Document.id)
                .where(Document.device_id == dev.id, Document.status == "ready")
            )
            chunk_count = chunk_count_result.scalar() or 0

            info = f"- **{dev.name}**"
            if dev.manufacturer:
                info += f" ({dev.manufacturer})"
            info += f"\n  Versions: {', '.join(versions) if versions else 'none'}"
            info += f"\n  Documents: {doc_count} | Chunks: {chunk_count}"
            parts.append(info)

        return f"**Indexed devices ({len(devices)}):**\n\n" + "\n\n".join(parts)


async def tool_ingest_document(
    file_path: str,
    device_name: str,
    firmware_version: str = "1.0",
    manufacturer: str = "",
    format: str = "auto",
) -> str:
    """Upload and index a documentation file for semantic search.

    Supported formats: Markdown (.md), Swagger/OpenAPI (.yaml, .json), PDF (.pdf).
    Format is auto-detected by default.

    Args:
        file_path: Absolute path to the documentation file on the server
        device_name: Name of the device (e.g. "HikCentral Professional")
        firmware_version: Firmware/API version (e.g. "V2.6.1")
        manufacturer: Device manufacturer (e.g. "Hikvision")
        format: File format — "auto", "markdown", "swagger", or "pdf"
    """
    async with async_session() as session:
        result = await ingest_file(
            session=session,
            file_path=file_path,
            device_name=device_name,
            firmware_version=firmware_version,
            manufacturer=manufacturer,
            fmt=format,
        )

    if result["status"] == "ok":
        return (
            f"Ingested successfully.\n"
            f"Device: {result['device']} (fw: {result['firmware_version']})\n"
            f"Format: {result['format']}\n"
            f"Chunks: {result['chunks']}\n"
            f"Duration: {result['duration_sec']}s"
        )
    elif result["status"] == "skipped":
        return result.get("message", "Document already ingested (same hash).")
    else:
        return f"Ingestion failed: {result.get('error', 'unknown error')}"
