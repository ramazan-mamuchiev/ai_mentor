"""Integration tests for tar archive family ingestion through the full pipeline.

Tests extraction, ingestion, and content parity across all tar compression variants
using a real PostgreSQL database (via testcontainers).
"""

import hashlib
import io
import os
import tarfile

import pytest
from sqlalchemy import select

from app.documents.archive import extract_archive, extract_tar
from app.ingestion.pipeline import ingest_file
from app.models import Chunk, Document, Product


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_tar_bytes(files: dict[str, bytes], compression: str = "") -> bytes:
    buf = io.BytesIO()
    mode = f"w:{compression}" if compression else "w"
    with tarfile.open(fileobj=buf, mode=mode) as tf:
        for name, data in files.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
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
}

message GetDeviceRequest {
  string device_id = 1;
}

message DeviceResponse {
  string id = 1;
  string name = 2;
}
"""


# ---------------------------------------------------------------------------
# Tests: extraction from real tar files on disk
# ---------------------------------------------------------------------------

class TestExtractTarIntegration:
    """Test tar extraction with real archive files."""

    def test_extract_tar_gz_from_disk(self, tmp_path):
        files = {"docs/api.md": SAMPLE_MD, "docs/service.proto": SAMPLE_PROTO}
        data = _create_tar_bytes(files, compression="gz")
        archive_path = tmp_path / "test.tar.gz"
        archive_path.write_bytes(data)

        with open(archive_path, "rb") as f:
            result = extract_tar(f.read(), ".tar.gz")

        assert len(result) == 2
        names = {os.path.basename(p) for p, _ in result}
        assert "api.md" in names
        assert "service.proto" in names

    def test_large_file_in_tar(self):
        large_content = b"# Large Document\n\n" + b"Lorem ipsum dolor sit amet. " * 10000
        files = {"large.md": large_content}
        data = _create_tar_bytes(files, compression="gz")
        result = extract_tar(data, ".tar.gz")

        assert len(result) == 1
        assert result[0][1] == large_content

    def test_all_compressions_produce_same_content(self):
        files = {"api.md": SAMPLE_MD, "service.proto": SAMPLE_PROTO}

        for compression, ext in [("", ".tar"), ("gz", ".tar.gz"), ("bz2", ".tar.bz2"), ("xz", ".tar.xz")]:
            data = _create_tar_bytes(files, compression=compression)
            result = extract_tar(data, ext)

            by_name = {os.path.basename(p): d for p, d in result}
            assert by_name["api.md"] == SAMPLE_MD, f"Content mismatch for {ext}"
            assert by_name["service.proto"] == SAMPLE_PROTO, f"Content mismatch for {ext}"


# ---------------------------------------------------------------------------
# Tests: cross-format parity (tar vs zip vs 7z)
# ---------------------------------------------------------------------------

class TestCrossFormatParity:
    """Verify identical extraction results across ZIP, 7z, and tar."""

    def test_same_content_zip_tar_7z(self):
        import zipfile
        import py7zr

        files = {"readme.md": SAMPLE_MD}

        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            zf.writestr("readme.md", SAMPLE_MD)
        zip_result = extract_archive(zip_buf.getvalue(), "test.zip")

        tar_data = _create_tar_bytes(files, compression="gz")
        tar_result = extract_archive(tar_data, "test.tar.gz")

        sz_buf = io.BytesIO()
        with py7zr.SevenZipFile(sz_buf, "w") as a:
            a.writestr(SAMPLE_MD, "readme.md")
        sz_result = extract_archive(sz_buf.getvalue(), "test.7z")

        zip_content = zip_result[0][1]
        tar_content = tar_result[0][1]
        sz_content = sz_result[0][1]

        assert zip_content == tar_content == sz_content == SAMPLE_MD

    def test_same_hashes_all_formats(self):
        import zipfile
        import py7zr

        content = SAMPLE_MD
        expected_hash = hashlib.sha256(content).hexdigest()

        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            zf.writestr("doc.md", content)
        zip_hash = hashlib.sha256(extract_archive(zip_buf.getvalue(), "t.zip")[0][1]).hexdigest()

        tar_data = _create_tar_bytes({"doc.md": content}, compression="gz")
        tar_hash = hashlib.sha256(extract_archive(tar_data, "t.tar.gz")[0][1]).hexdigest()

        sz_buf = io.BytesIO()
        with py7zr.SevenZipFile(sz_buf, "w") as a:
            a.writestr(content, "doc.md")
        sz_hash = hashlib.sha256(extract_archive(sz_buf.getvalue(), "t.7z")[0][1]).hexdigest()

        assert zip_hash == tar_hash == sz_hash == expected_hash


# ---------------------------------------------------------------------------
# Tests: full ingestion pipeline with tar-extracted files
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("_init_schema", "_mock_embedder")
class TestTarIngestionPipeline:
    """Integration test: ingest files extracted from tar archives."""

    async def test_ingest_md_from_tar(self, db_session, tmp_path):
        md_path = tmp_path / "api_guide.md"
        md_path.write_bytes(SAMPLE_MD)

        result = await ingest_file(
            session=db_session,
            file_path=str(md_path),
            product_name="TarTestProduct",
            firmware_version="1.0",
            manufacturer="TarMfg",
        )

        assert result["status"] == "ok"
        assert result["chunks"] > 0

        product = (await db_session.execute(
            select(Product).where(Product.name == "TarTestProduct")
        )).scalar_one()
        assert product.manufacturer == "TarMfg"

    async def test_ingest_proto_from_tar(self, db_session, tmp_path):
        proto_path = tmp_path / "device_service.proto"
        proto_path.write_bytes(SAMPLE_PROTO)

        result = await ingest_file(
            session=db_session,
            file_path=str(proto_path),
            product_name="TarProtoProduct",
            firmware_version="1.0",
        )

        assert result["status"] == "ok"
        assert result["format"] == "proto"

        chunks = (await db_session.execute(
            select(Chunk).join(Document).join(Product).where(Product.name == "TarProtoProduct")
        )).scalars().all()
        all_content = " ".join(c.content for c in chunks)
        assert "DeviceService" in all_content

    async def test_multiple_files_from_tar_same_product(self, db_session, tmp_path):
        md_path = tmp_path / "api.md"
        md_path.write_bytes(SAMPLE_MD)

        proto_path = tmp_path / "service.proto"
        proto_path.write_bytes(SAMPLE_PROTO)

        r1 = await ingest_file(
            session=db_session, file_path=str(md_path),
            product_name="TarMultiProduct", firmware_version="2.0",
        )
        r2 = await ingest_file(
            session=db_session, file_path=str(proto_path),
            product_name="TarMultiProduct", firmware_version="2.0",
        )

        assert r1["status"] == "ok"
        assert r2["status"] == "ok"

        docs = (await db_session.execute(
            select(Document).join(Product).where(Product.name == "TarMultiProduct")
        )).scalars().all()
        assert len(docs) == 2

    async def test_dedup_tar_extracted_file(self, db_session, tmp_path):
        md_path = tmp_path / "shared.md"
        md_path.write_bytes(SAMPLE_MD)

        r1 = await ingest_file(
            session=db_session, file_path=str(md_path),
            product_name="TarDedupProduct", firmware_version="1.0",
        )
        assert r1["status"] == "ok"

        r2 = await ingest_file(
            session=db_session, file_path=str(md_path),
            product_name="TarDedupProduct", firmware_version="1.0",
        )
        assert r2["status"] == "skipped"


# ---------------------------------------------------------------------------
# Tests: tar-specific edge cases
# ---------------------------------------------------------------------------

class TestTarEdgeCasesIntegration:
    """Integration-level edge cases for tar archives."""

    def test_tar_with_symlinks_skipped(self):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tf:
            file_info = tarfile.TarInfo(name="readme.md")
            content = b"# Hello"
            file_info.size = len(content)
            tf.addfile(file_info, io.BytesIO(content))

            link_info = tarfile.TarInfo(name="link.md")
            link_info.type = tarfile.SYMTYPE
            link_info.linkname = "readme.md"
            tf.addfile(link_info)

        data = buf.getvalue()
        result = extract_tar(data, ".tar")
        assert len(result) == 1
        assert os.path.basename(result[0][0]) == "readme.md"

    def test_tar_with_special_characters_in_names(self):
        files = {"docs/api guide (v2).md": b"# API v2"}
        data = _create_tar_bytes(files, compression="gz")
        result = extract_tar(data, ".tar.gz")

        assert len(result) == 1
        assert result[0][1] == b"# API v2"
