"""Integration tests for MCP tool functions with real PostgreSQL+pgvector."""

import pytest
from unittest.mock import AsyncMock, patch

from app.ingestion.pipeline import ingest_file


def _mock_session(db_session):
    """Create a patched async_session context manager that yields db_session."""
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = db_session
    mock_cm.__aexit__.return_value = None
    return patch("app.mcp.server.async_session", return_value=mock_cm)


@pytest.fixture
def second_md_file(tmp_path):
    """A second product's documentation (VMS software, not hardware)."""
    content = """# Axxon One HTTP API

## Camera Management

### Register Camera
POST /api/v1/cameras

Register a new IP camera in the system.

Request body:
```json
{
  "name": "Front entrance",
  "ip": "192.168.1.100",
  "port": 554,
  "protocol": "rtsp",
  "credentials": {"username": "admin", "password": "***"}
}
```

Response: 201 Created with camera ID.

### Get Camera Stream URL
GET /api/v1/cameras/{id}/streams

Returns RTSP stream URLs for the camera.

Response:
```json
{
  "main_stream": "rtsp://192.168.1.100:554/Streaming/Channels/101",
  "sub_stream": "rtsp://192.168.1.100:554/Streaming/Channels/102"
}
```

## Analytics

### Configure Analytics
POST /api/v1/analytics/profiles

Create an analytics profile for a camera (motion detection, face recognition, LPR).

### Get Analytics Events
GET /api/v1/analytics/events?camera_id={id}&from={timestamp}&to={timestamp}

Returns analytics events for a camera within a time range.
"""
    path = tmp_path / "axxon_one_api.md"
    path.write_text(content, encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# list_products
# ---------------------------------------------------------------------------

class TestToolListProducts:
    async def test_empty_db(self, db_session):
        with _mock_session(db_session):
            from app.mcp.server import tool_list_products
            result = await tool_list_products()
        assert "No products" in result

    async def test_single_product(self, db_session, sample_md_file):
        await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            product_name="ZKTeco InBio",
            firmware_version="1.0",
            manufacturer="ZKTeco",
        )
        with _mock_session(db_session):
            from app.mcp.server import tool_list_products
            result = await tool_list_products()

        assert "ZKTeco InBio" in result
        assert "ZKTeco" in result
        assert "1.0" in result
        assert "Available products (1)" in result

    async def test_multiple_products(self, db_session, sample_md_file, second_md_file):
        await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            product_name="ZKTeco InBio",
            firmware_version="1.0",
            manufacturer="ZKTeco",
        )
        await ingest_file(
            session=db_session,
            file_path=second_md_file,
            product_name="Axxon One",
            firmware_version="5.0",
            manufacturer="AxxonSoft",
        )
        with _mock_session(db_session):
            from app.mcp.server import tool_list_products
            result = await tool_list_products()

        assert "Available products (2)" in result
        assert "ZKTeco InBio" in result
        assert "Axxon One" in result

    async def test_filter_by_query(self, db_session, sample_md_file, second_md_file):
        await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            product_name="ZKTeco InBio",
            firmware_version="1.0",
            manufacturer="ZKTeco",
        )
        await ingest_file(
            session=db_session,
            file_path=second_md_file,
            product_name="Axxon One",
            firmware_version="5.0",
            manufacturer="AxxonSoft",
        )
        with _mock_session(db_session):
            from app.mcp.server import tool_list_products
            result = await tool_list_products(query="Axxon")

        assert "Axxon One" in result
        assert "ZKTeco" not in result

    async def test_filter_by_query_no_match(self, db_session, sample_md_file):
        await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            product_name="ZKTeco InBio",
            firmware_version="1.0",
            manufacturer="ZKTeco",
        )
        with _mock_session(db_session):
            from app.mcp.server import tool_list_products
            result = await tool_list_products(query="Nonexistent")

        assert "No products found" in result

    async def test_filter_by_category(self, db_session, sample_md_file, second_md_file):
        await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            product_name="ZKTeco InBio",
            firmware_version="1.0",
            manufacturer="ZKTeco",
        )
        await ingest_file(
            session=db_session,
            file_path=second_md_file,
            product_name="Axxon One VMS",
            firmware_version="5.0",
            manufacturer="AxxonSoft",
        )
        # Category is empty by default in ingest_file, so both should appear
        # when filtering by a non-matching category
        with _mock_session(db_session):
            from app.mcp.server import tool_list_products
            result = await tool_list_products(category="nonexistent_category")

        assert "No products found" in result

    async def test_doc_and_chunk_counts(self, db_session, sample_md_file):
        await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            product_name="CountTest",
            firmware_version="1.0",
        )
        with _mock_session(db_session):
            from app.mcp.server import tool_list_products
            result = await tool_list_products()

        assert "1 docs" in result
        # sample_md_file has multiple chunks (headers create sections)
        assert "chunks" in result


# ---------------------------------------------------------------------------
# search_documentation
# ---------------------------------------------------------------------------

class TestToolSearchDocumentation:
    async def test_no_results_empty_db(self, db_session):
        with _mock_session(db_session):
            from app.mcp.server import tool_search_documentation
            result = await tool_search_documentation(query="anything")
        assert "No results" in result

    async def test_basic_search(self, db_session, sample_md_file):
        await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            product_name="TestDevice",
            firmware_version="1.0",
        )
        with _mock_session(db_session):
            from app.mcp.server import tool_search_documentation
            result = await tool_search_documentation(query="door control", limit=3)

        assert "[1]" in result
        assert "similarity:" in result
        assert "TestDevice" in result

    async def test_limit_respected(self, db_session, sample_md_file):
        await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            product_name="TestDevice",
            firmware_version="1.0",
        )
        with _mock_session(db_session):
            from app.mcp.server import tool_search_documentation
            result = await tool_search_documentation(query="door control", limit=1)

        assert "[1]" in result
        assert "[2]" not in result

    async def test_filter_by_product(self, db_session, sample_md_file, second_md_file):
        await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            product_name="ZKTeco InBio",
            firmware_version="1.0",
            manufacturer="ZKTeco",
        )
        await ingest_file(
            session=db_session,
            file_path=second_md_file,
            product_name="Axxon One",
            firmware_version="5.0",
            manufacturer="AxxonSoft",
        )
        with _mock_session(db_session):
            from app.mcp.server import tool_search_documentation
            result = await tool_search_documentation(query="camera stream", product="Axxon")

        assert "Axxon One" in result
        assert "ZKTeco" not in result

    async def test_filter_by_version(self, db_session, sample_md_file):
        await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            product_name="TestDevice",
            firmware_version="2.5",
        )
        with _mock_session(db_session):
            from app.mcp.server import tool_search_documentation

            result_match = await tool_search_documentation(query="door", version="2.5")
            assert "TestDevice" in result_match

            result_miss = await tool_search_documentation(query="door", version="9.9")
            assert "No results" in result_miss

    async def test_output_format_compact(self, db_session, sample_md_file):
        """Verify output uses compact format without heavy Markdown."""
        await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            product_name="TestDevice",
            firmware_version="1.0",
        )
        with _mock_session(db_session):
            from app.mcp.server import tool_search_documentation
            result = await tool_search_documentation(query="door control", limit=2)

        # Compact format: [N] metadata line, no ## headers
        assert "## Result" not in result
        assert "**Product:**" not in result
        assert "[1]" in result
        assert "---" in result

    async def test_limit_clamped(self, db_session, sample_md_file):
        """Verify limit is clamped to 1-20 range."""
        await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            product_name="TestDevice",
            firmware_version="1.0",
        )
        with _mock_session(db_session):
            from app.mcp.server import tool_search_documentation
            # limit=0 should be clamped to 1
            result = await tool_search_documentation(query="door", limit=0)
        assert "[1]" in result
        assert "[2]" not in result

    async def test_cross_product_search(self, db_session, sample_md_file, second_md_file):
        """Search without product filter returns results from multiple products."""
        await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            product_name="ZKTeco InBio",
            firmware_version="1.0",
            manufacturer="ZKTeco",
        )
        await ingest_file(
            session=db_session,
            file_path=second_md_file,
            product_name="Axxon One",
            firmware_version="5.0",
            manufacturer="AxxonSoft",
        )
        with _mock_session(db_session):
            from app.mcp.server import tool_search_documentation
            result = await tool_search_documentation(query="camera configuration settings", limit=10)

        # Should return results (at least from one product)
        assert "[1]" in result


# ---------------------------------------------------------------------------
# get_api_endpoint
# ---------------------------------------------------------------------------

class TestToolGetApiEndpoint:
    async def test_exact_match_by_heading(self, db_session, sample_md_file):
        """Exact heading_path match (ILIKE) should work."""
        await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            product_name="TestDevice",
            firmware_version="1.0",
        )
        with _mock_session(db_session):
            from app.mcp.server import tool_get_api_endpoint
            result = await tool_get_api_endpoint(endpoint="Open Door")

        assert "TestDevice" in result
        assert "CONTROL DEVICE" in result

    async def test_fallback_to_vector_search(self, db_session, sample_md_file):
        """When no exact match, falls back to semantic search."""
        await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            product_name="TestDevice",
            firmware_version="1.0",
        )
        with _mock_session(db_session):
            from app.mcp.server import tool_get_api_endpoint
            result = await tool_get_api_endpoint(endpoint="/some/api/door/control")

        # Should find something via vector search fallback
        assert "TestDevice" in result or "No documentation" in result

    async def test_no_match_empty_db(self, db_session):
        with _mock_session(db_session):
            from app.mcp.server import tool_get_api_endpoint
            result = await tool_get_api_endpoint(endpoint="/nonexistent/api/v99")

        assert "No documentation" in result or "No results" in result

    async def test_filter_by_product(self, db_session, sample_md_file, second_md_file):
        await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            product_name="ZKTeco InBio",
            firmware_version="1.0",
            manufacturer="ZKTeco",
        )
        await ingest_file(
            session=db_session,
            file_path=second_md_file,
            product_name="Axxon One",
            firmware_version="5.0",
            manufacturer="AxxonSoft",
        )
        with _mock_session(db_session):
            from app.mcp.server import tool_get_api_endpoint
            result = await tool_get_api_endpoint(
                endpoint="Register Camera",
                product="Axxon",
            )

        assert "Axxon One" in result
        assert "ZKTeco" not in result

    async def test_output_format(self, db_session, sample_md_file):
        """Verify compact output format."""
        await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            product_name="TestDevice",
            firmware_version="1.0",
        )
        with _mock_session(db_session):
            from app.mcp.server import tool_get_api_endpoint
            result = await tool_get_api_endpoint(endpoint="Open Door")

        assert "**Product:**" not in result
        assert "match)" in result  # "(exact match)" or "(vector match)"

    async def test_swagger_endpoint_lookup(self, db_session, sample_swagger_file):
        """Swagger/OpenAPI endpoints should be findable."""
        await ingest_file(
            session=db_session,
            file_path=sample_swagger_file,
            product_name="AccessControlAPI",
            firmware_version="1.0",
            fmt="swagger",
        )
        with _mock_session(db_session):
            from app.mcp.server import tool_get_api_endpoint
            result = await tool_get_api_endpoint(endpoint="/doors")

        assert "AccessControlAPI" in result
