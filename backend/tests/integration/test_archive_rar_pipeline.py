"""Integration tests for RAR archive support.

Since creating RAR archives requires proprietary tools, these tests focus on:
- Error handling with invalid data
- Dispatch correctness
- Mock-based extraction with real pipeline
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from app.documents.archive import extract_archive, extract_rar
from app.ingestion.pipeline import ingest_file
from app.models import Chunk, Document, Product


SAMPLE_MD = b"""\
# RAR Test API Documentation

## Authentication
All API calls require Bearer token authentication.

## Endpoints

### GET /api/v1/devices
Returns a list of all registered devices.
"""


# ---------------------------------------------------------------------------
# Tests: RAR error handling (integration level)
# ---------------------------------------------------------------------------

class TestExtractRarIntegration:
    """Test RAR extraction error handling with real data."""

    def test_invalid_rar_data(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            extract_rar(b"definitely not a rar file " * 10)
        assert exc_info.value.status_code == 400

    def test_dispatch_rar_extension(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            extract_archive(b"not rar", "test.rar")
        assert exc_info.value.status_code == 400

    def test_rar_not_confused_with_other_formats(self):
        """Ensure .rar files don't accidentally get parsed as ZIP or tar."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            extract_archive(b"PK\x03\x04fake zip header", "test.rar")
        assert exc_info.value.status_code == 400
        assert "Invalid RAR file" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Tests: RAR ingestion pipeline with mocked extraction
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("_init_schema", "_mock_embedder")
class TestRarIngestionPipeline:
    """Integration test: ingest files that would come from a RAR archive."""

    async def test_ingest_md_from_rar_source(self, db_session, tmp_path):
        """Simulate extracting a file from RAR and ingesting it."""
        md_path = tmp_path / "rar_api_guide.md"
        md_path.write_bytes(SAMPLE_MD)

        result = await ingest_file(
            session=db_session,
            file_path=str(md_path),
            product_name="RarTestProduct",
            firmware_version="1.0",
            manufacturer="RarMfg",
        )

        assert result["status"] == "ok"
        assert result["chunks"] > 0

        product = (await db_session.execute(
            select(Product).where(Product.name == "RarTestProduct")
        )).scalar_one()
        assert product.manufacturer == "RarMfg"

        doc = (await db_session.execute(
            select(Document).where(Document.product_id == product.id)
        )).scalar_one()
        assert doc.status == "ready"

    async def test_dedup_rar_extracted_file(self, db_session, tmp_path):
        """Same file ingested twice should be detected as duplicate."""
        md_path = tmp_path / "rar_shared.md"
        md_path.write_bytes(SAMPLE_MD)

        r1 = await ingest_file(
            session=db_session, file_path=str(md_path),
            product_name="RarDedupProduct", firmware_version="1.0",
        )
        assert r1["status"] == "ok"

        r2 = await ingest_file(
            session=db_session, file_path=str(md_path),
            product_name="RarDedupProduct", firmware_version="1.0",
        )
        assert r2["status"] == "skipped"
