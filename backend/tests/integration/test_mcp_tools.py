"""Integration tests for MCP tool functions with real PostgreSQL+pgvector."""

import pytest
from unittest.mock import patch

from app.ingestion.pipeline import ingest_file


class TestToolListDevices:
    async def test_empty_db(self, db_session):
        with patch("app.mcp.server.async_session") as mock_session_factory:
            mock_session_factory.return_value.__aenter__ = lambda s: db_session
            mock_session_factory.return_value.__aexit__ = lambda s, *a: None

            # Use a context manager mock
            from unittest.mock import AsyncMock
            mock_cm = AsyncMock()
            mock_cm.__aenter__.return_value = db_session
            mock_cm.__aexit__.return_value = None
            mock_session_factory.return_value = mock_cm

            from app.mcp.server import tool_list_devices
            result = await tool_list_devices()
            assert "No devices" in result or "no devices" in result.lower()

    async def test_after_ingest(self, db_session, sample_md_file):
        await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            device_name="ZKTeco InBio",
            firmware_version="1.0",
            manufacturer="ZKTeco",
        )

        from unittest.mock import AsyncMock
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = db_session
        mock_cm.__aexit__.return_value = None

        with patch("app.mcp.server.async_session", return_value=mock_cm):
            from app.mcp.server import tool_list_devices
            result = await tool_list_devices()

        assert "ZKTeco InBio" in result
        assert "ZKTeco" in result
        assert "1.0" in result


class TestToolSearchDocumentation:
    async def test_no_results(self, db_session):
        from unittest.mock import AsyncMock
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = db_session
        mock_cm.__aexit__.return_value = None

        with patch("app.mcp.server.async_session", return_value=mock_cm):
            from app.mcp.server import tool_search_documentation
            result = await tool_search_documentation(query="anything")

        assert "No results" in result

    async def test_returns_formatted_results(self, db_session, sample_md_file):
        await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            device_name="TestDevice",
            firmware_version="1.0",
        )

        from unittest.mock import AsyncMock
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = db_session
        mock_cm.__aexit__.return_value = None

        with patch("app.mcp.server.async_session", return_value=mock_cm):
            from app.mcp.server import tool_search_documentation
            result = await tool_search_documentation(query="door control", limit=2)

        assert "Result 1" in result
        assert "similarity:" in result
        assert "TestDevice" in result


class TestToolIngestDocument:
    async def test_successful_ingest(self, db_session, sample_md_file):
        from unittest.mock import AsyncMock
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = db_session
        mock_cm.__aexit__.return_value = None

        with patch("app.mcp.server.async_session", return_value=mock_cm):
            from app.mcp.server import tool_ingest_document
            result = await tool_ingest_document(
                file_path=sample_md_file,
                device_name="TestDevice",
                firmware_version="1.0",
            )

        assert "Ingested successfully" in result
        assert "Chunks:" in result

    async def test_file_not_found(self, db_session):
        from unittest.mock import AsyncMock
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = db_session
        mock_cm.__aexit__.return_value = None

        with patch("app.mcp.server.async_session", return_value=mock_cm):
            from app.mcp.server import tool_ingest_document
            result = await tool_ingest_document(
                file_path="/nonexistent/file.md",
                device_name="TestDevice",
            )

        assert "failed" in result.lower() or "error" in result.lower()


class TestToolGetApiEndpoint:
    async def test_finds_endpoint(self, db_session, sample_md_file):
        await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            device_name="TestDevice",
            firmware_version="1.0",
        )

        from unittest.mock import AsyncMock
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = db_session
        mock_cm.__aexit__.return_value = None

        with patch("app.mcp.server.async_session", return_value=mock_cm):
            from app.mcp.server import tool_get_api_endpoint
            result = await tool_get_api_endpoint(endpoint="Open Door")

        assert "TestDevice" in result

    async def test_no_match(self, db_session):
        from unittest.mock import AsyncMock
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = db_session
        mock_cm.__aexit__.return_value = None

        with patch("app.mcp.server.async_session", return_value=mock_cm):
            from app.mcp.server import tool_get_api_endpoint
            result = await tool_get_api_endpoint(endpoint="/nonexistent/api/v99")

        assert "No documentation" in result or "no results" in result.lower() or "No results" in result
