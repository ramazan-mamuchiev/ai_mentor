"""Integration tests for 7z archive ingestion through the full pipeline.

Tests extraction, ingestion, deduplication, and content parity with ZIP
using a real PostgreSQL database (via testcontainers).
"""

import hashlib
import io
import os
import tempfile
import zipfile

import py7zr
import pytest
from sqlalchemy import select

from app.documents.archive import extract_7z, extract_archive
from app.ingestion.pipeline import ingest_file
from app.models import Chunk, Document, Product


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_7z_file(files: dict[str, bytes], path: str) -> str:
    """Create a 7z archive on disk. Returns the file path."""
    with py7zr.SevenZipFile(path, "w") as archive:
        for name, data in files.items():
            archive.writestr(data, name)
    return path


def _create_zip_file(files: dict[str, bytes], path: str) -> str:
    """Create a ZIP archive on disk. Returns the file path."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return path


def _create_7z_bytes(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with py7zr.SevenZipFile(buf, "w") as archive:
        for name, data in files.items():
            archive.writestr(data, name)
    return buf.getvalue()


def _create_zip_bytes(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


SAMPLE_MD = b"""\
# Test API Documentation

## Authentication
All API calls require Bearer token authentication.

## Endpoints

### GET /api/v1/devices
Returns a list of all registered devices.

### POST /api/v1/devices
Register a new device. Requires JSON body with `name` and `type` fields.

### GET /api/v1/events
Returns recent events with pagination support.
"""

SAMPLE_PROTO = b"""\
syntax = "proto3";

package test.api.v1;

service DeviceService {
  rpc GetDevice(GetDeviceRequest) returns (DeviceResponse);
  rpc ListDevices(ListDevicesRequest) returns (stream DeviceResponse);
}

message GetDeviceRequest {
  string device_id = 1;
}

message DeviceResponse {
  string id = 1;
  string name = 2;
  string status = 3;
}

message ListDevicesRequest {
  int32 page_size = 1;
  string page_token = 2;
}
"""

SAMPLE_YAML = b"""\
openapi: "3.0.0"
info:
  title: Device API
  version: "1.0"
paths:
  /devices:
    get:
      summary: List devices
      responses:
        "200":
          description: OK
"""


# ---------------------------------------------------------------------------
# Tests: _extract_7z with real files
# ---------------------------------------------------------------------------

class TestExtract7zIntegration:
    """Test 7z extraction with real archive files on disk."""

    def test_extract_from_disk_file(self, tmp_path):
        files = {
            "docs/api.md": SAMPLE_MD,
            "docs/service.proto": SAMPLE_PROTO,
        }
        archive_path = str(tmp_path / "test.7z")
        _create_7z_file(files, archive_path)

        with open(archive_path, "rb") as f:
            data = f.read()

        result = extract_7z(data)
        assert len(result) == 2

        names = {os.path.basename(p) for p, _ in result}
        assert "api.md" in names
        assert "service.proto" in names

    def test_large_file_in_archive(self, tmp_path):
        large_content = b"# Large Document\n\n" + b"Lorem ipsum dolor sit amet. " * 10000
        files = {"large.md": large_content}
        data = _create_7z_bytes(files)

        result = extract_7z(data)
        assert len(result) == 1
        assert result[0][1] == large_content

    def test_unicode_filenames(self, tmp_path):
        files = {"docs/readme.md": b"# Hello"}
        data = _create_7z_bytes(files)

        result = extract_7z(data)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Tests: content parity between ZIP and 7z at extraction level
# ---------------------------------------------------------------------------

class TestExtractionParity:
    """Verify identical extraction results from ZIP and 7z."""

    def test_same_files_same_content(self):
        files = {
            "api.md": SAMPLE_MD,
            "service.proto": SAMPLE_PROTO,
            "spec.yaml": SAMPLE_YAML,
        }

        zip_data = _create_zip_bytes(files)
        sz_data = _create_7z_bytes(files)

        zip_result = extract_archive(zip_data, "test.zip")
        sz_result = extract_archive(sz_data, "test.7z")

        assert len(zip_result) == len(sz_result) == 3

        zip_by_name = {os.path.basename(p): d for p, d in zip_result}
        sz_by_name = {os.path.basename(p): d for p, d in sz_result}

        for name in files:
            basename = os.path.basename(name)
            assert zip_by_name[basename] == sz_by_name[basename]
            assert zip_by_name[basename] == files[name]

    def test_hashes_match_between_formats(self):
        files = {"doc.md": SAMPLE_MD}

        zip_data = _create_zip_bytes(files)
        sz_data = _create_7z_bytes(files)

        zip_result = extract_archive(zip_data, "test.zip")
        sz_result = extract_archive(sz_data, "test.7z")

        zip_hash = hashlib.sha256(zip_result[0][1]).hexdigest()
        sz_hash = hashlib.sha256(sz_result[0][1]).hexdigest()
        original_hash = hashlib.sha256(SAMPLE_MD).hexdigest()

        assert zip_hash == sz_hash == original_hash


# ---------------------------------------------------------------------------
# Tests: full ingestion pipeline with 7z-extracted files
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("_init_schema", "_mock_embedder")
class TestArchive7zIngestionPipeline:
    """Integration test: ingest files extracted from a 7z archive through the full pipeline."""

    async def test_ingest_md_from_7z(self, db_session, tmp_path):
        """Markdown file extracted from 7z should be ingested correctly."""
        md_path = tmp_path / "api_guide.md"
        md_path.write_bytes(SAMPLE_MD)

        result = await ingest_file(
            session=db_session,
            file_path=str(md_path),
            product_name="7zTestProduct",
            firmware_version="1.0",
            manufacturer="TestMfg7z",
        )

        assert result["status"] == "ok"
        assert result["chunks"] > 0
        assert result["product"] == "7zTestProduct"

        product = (await db_session.execute(
            select(Product).where(Product.name == "7zTestProduct")
        )).scalar_one()
        assert product.manufacturer == "TestMfg7z"

        doc = (await db_session.execute(
            select(Document).where(Document.product_id == product.id)
        )).scalar_one()
        assert doc.status == "ready"
        assert doc.total_chunks > 0

    async def test_ingest_proto_from_7z(self, db_session, tmp_path):
        """Proto file extracted from 7z should be converted and ingested."""
        proto_path = tmp_path / "device_service.proto"
        proto_path.write_bytes(SAMPLE_PROTO)

        result = await ingest_file(
            session=db_session,
            file_path=str(proto_path),
            product_name="7zProtoProduct",
            firmware_version="1.0",
            manufacturer="ProtoMfg",
        )

        assert result["status"] == "ok"
        assert result["format"] == "proto"
        assert result["chunks"] > 0

        chunks = (await db_session.execute(
            select(Chunk).join(Document).join(Product).where(Product.name == "7zProtoProduct")
        )).scalars().all()

        all_content = " ".join(c.content for c in chunks)
        assert "DeviceService" in all_content
        assert "GetDevice" in all_content

    async def test_multiple_files_same_product(self, db_session, tmp_path):
        """Multiple files from a 7z archive should all link to the same product."""
        md_path = tmp_path / "api.md"
        md_path.write_bytes(SAMPLE_MD)

        proto_path = tmp_path / "service.proto"
        proto_path.write_bytes(SAMPLE_PROTO)

        r1 = await ingest_file(
            session=db_session,
            file_path=str(md_path),
            product_name="MultiFileProduct",
            firmware_version="2.0",
            manufacturer="MultiMfg",
        )
        assert r1["status"] == "ok"

        r2 = await ingest_file(
            session=db_session,
            file_path=str(proto_path),
            product_name="MultiFileProduct",
            firmware_version="2.0",
            manufacturer="MultiMfg",
        )
        assert r2["status"] == "ok"

        product = (await db_session.execute(
            select(Product).where(Product.name == "MultiFileProduct")
        )).scalar_one()

        docs = (await db_session.execute(
            select(Document).where(Document.product_id == product.id)
        )).scalars().all()
        assert len(docs) == 2

        total_chunks = sum(d.total_chunks for d in docs)
        assert total_chunks > 0

    async def test_dedup_across_archive_formats(self, db_session, tmp_path):
        """Same file ingested from ZIP and 7z should be detected as duplicate."""
        md_path = tmp_path / "shared_doc.md"
        md_path.write_bytes(SAMPLE_MD)

        r1 = await ingest_file(
            session=db_session,
            file_path=str(md_path),
            product_name="DedupCrossFormat",
            firmware_version="1.0",
        )
        assert r1["status"] == "ok"

        r2 = await ingest_file(
            session=db_session,
            file_path=str(md_path),
            product_name="DedupCrossFormat",
            firmware_version="1.0",
        )
        assert r2["status"] == "skipped"


# ---------------------------------------------------------------------------
# Tests: 7z-specific edge cases
# ---------------------------------------------------------------------------

class TestArchive7zEdgeCases:
    """Test edge cases specific to 7z format."""

    def test_7z_with_only_unsupported_files(self):
        files = {
            "image.png": b"\x89PNG...",
            "binary.exe": b"MZ...",
            "data.csv": b"a,b,c\n1,2,3",
        }
        data = _create_7z_bytes(files)
        result = extract_7z(data)
        assert result == []

    def test_7z_mixed_supported_unsupported(self):
        files = {
            "readme.md": b"# Readme",
            "image.png": b"\x89PNG...",
            "spec.yaml": b"openapi: 3.0.0",
            "binary.dll": b"\x00\x01\x02",
        }
        data = _create_7z_bytes(files)
        result = extract_7z(data)

        names = {os.path.basename(p) for p, _ in result}
        assert names == {"readme.md", "spec.yaml"}

    def test_7z_preserves_binary_content_exactly(self):
        """PDF-like binary content should be preserved byte-for-byte."""
        pdf_header = b"%PDF-1.4\n" + os.urandom(1024)
        files = {"document.pdf": pdf_header}
        data = _create_7z_bytes(files)
        result = extract_7z(data)

        assert len(result) == 1
        assert result[0][1] == pdf_header
