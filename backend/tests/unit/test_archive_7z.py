"""Unit tests for 7z archive support in document ingestion."""

import hashlib
import io
import os
import zipfile
from unittest.mock import AsyncMock, MagicMock, patch

import py7zr
import pytest

from app.documents.archive import extract_7z, extract_archive, extract_zip
from app.documents.schemas import ArchiveFileResult, ArchiveIngestResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_zip_bytes(files: dict[str, bytes]) -> bytes:
    """Create a ZIP archive in memory. files = {path: content}."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _create_7z_bytes(files: dict[str, bytes]) -> bytes:
    """Create a 7z archive in memory. files = {path: content}."""
    buf = io.BytesIO()
    with py7zr.SevenZipFile(buf, "w") as archive:
        for name, data in files.items():
            archive.writestr(data, name)
    return buf.getvalue()


def _mock_request():
    req = MagicMock()
    req.headers = {}
    req.client = MagicMock()
    req.client.host = "127.0.0.1"
    return req


def _mock_session_ctx(mock_session):
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_ctx


# ---------------------------------------------------------------------------
# Tests: extract_7z
# ---------------------------------------------------------------------------

class TestExtract7z:
    """Test the extract_7z helper function."""

    def test_extracts_supported_files(self):
        files = {
            "docs/api.md": b"# API Guide",
            "docs/spec.yaml": b"openapi: 3.0.0",
            "docs/schema.proto": b'syntax = "proto3";',
        }
        data = _create_7z_bytes(files)
        result = extract_7z(data)

        extracted_names = {os.path.basename(p) for p, _ in result}
        assert extracted_names == {"api.md", "spec.yaml", "schema.proto"}

    def test_skips_unsupported_extensions(self):
        files = {
            "readme.md": b"# Readme",
            "image.png": b"\x89PNG...",
            "binary.exe": b"MZ...",
        }
        data = _create_7z_bytes(files)
        result = extract_7z(data)

        assert len(result) == 1
        assert os.path.basename(result[0][0]) == "readme.md"

    def test_skips_hidden_files(self):
        files = {
            ".hidden.md": b"# Hidden",
            "visible.md": b"# Visible",
        }
        data = _create_7z_bytes(files)
        result = extract_7z(data)

        assert len(result) == 1
        assert os.path.basename(result[0][0]) == "visible.md"

    def test_preserves_content(self):
        content = b"# Important Documentation\n\nWith detailed content."
        files = {"doc.md": content}
        data = _create_7z_bytes(files)
        result = extract_7z(data)

        assert len(result) == 1
        assert result[0][1] == content

    def test_invalid_7z_raises_http_exception(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            extract_7z(b"this is not a 7z file")
        assert exc_info.value.status_code == 400
        assert "Invalid 7z file" in exc_info.value.detail

    def test_empty_archive(self):
        buf = io.BytesIO()
        with py7zr.SevenZipFile(buf, "w") as archive:
            pass
        data = buf.getvalue()
        result = extract_7z(data)
        assert result == []

    def test_nested_directory_structure(self):
        files = {
            "project/docs/api.md": b"# API",
            "project/docs/proto/service.proto": b'syntax = "proto3";',
            "project/config.yaml": b"key: value",
        }
        data = _create_7z_bytes(files)
        result = extract_7z(data)

        paths = [p for p, _ in result]
        assert len(paths) == 3
        assert "project/docs/api.md" in paths
        assert "project/docs/proto/service.proto" in paths


# ---------------------------------------------------------------------------
# Tests: extract_zip (regression: ensure ZIP still works)
# ---------------------------------------------------------------------------

class TestExtractZip:
    """Regression tests to ensure ZIP extraction still works after refactoring."""

    def test_extracts_supported_files(self):
        files = {
            "api.md": b"# API",
            "spec.json": b'{"openapi": "3.0.0"}',
        }
        data = _create_zip_bytes(files)
        result = extract_zip(data)

        assert len(result) == 2

    def test_invalid_zip_raises_http_exception(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            extract_zip(b"not a zip")
        assert exc_info.value.status_code == 400
        assert "Invalid ZIP file" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Tests: extract_archive dispatch
# ---------------------------------------------------------------------------

class TestExtractArchive:
    """Test the extract_archive dispatcher."""

    def test_dispatches_zip(self):
        files = {"doc.md": b"# Hello"}
        data = _create_zip_bytes(files)
        result = extract_archive(data, "archive.zip")
        assert len(result) == 1

    def test_dispatches_7z(self):
        files = {"doc.md": b"# Hello"}
        data = _create_7z_bytes(files)
        result = extract_archive(data, "archive.7z")
        assert len(result) == 1

    def test_rejects_unsupported_format(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            extract_archive(b"data", "archive.cab")
        assert exc_info.value.status_code == 400
        assert "Unsupported archive format" in exc_info.value.detail

    def test_case_insensitive_extension(self):
        files = {"doc.md": b"# Hello"}
        data_7z = _create_7z_bytes(files)
        result = extract_archive(data_7z, "ARCHIVE.7Z")
        assert len(result) == 1

        data_zip = _create_zip_bytes(files)
        result = extract_archive(data_zip, "Archive.ZIP")
        assert len(result) == 1


    # Endpoint tests for ingest_archive are in test_documents_router.py
    # (requires boto3 / Docker environment due to app.s3 import)


# ---------------------------------------------------------------------------
# Tests: content parity between ZIP and 7z
# ---------------------------------------------------------------------------

class TestArchiveContentParity:
    """Verify that the same files produce identical results from ZIP and 7z."""

    def test_same_content_from_both_formats(self):
        files = {
            "readme.md": b"# Readme\n\nSome documentation.",
            "api.yaml": b"openapi: 3.0.0\ninfo:\n  title: API",
        }

        zip_data = _create_zip_bytes(files)
        sz_data = _create_7z_bytes(files)

        zip_result = extract_archive(zip_data, "test.zip")
        sz_result = extract_archive(sz_data, "test.7z")

        zip_contents = {os.path.basename(p): d for p, d in zip_result}
        sz_contents = {os.path.basename(p): d for p, d in sz_result}

        assert zip_contents.keys() == sz_contents.keys()
        for name in zip_contents:
            assert zip_contents[name] == sz_contents[name], f"Content mismatch for {name}"

    def test_same_hashes_from_both_formats(self):
        content = b"# Identical content for hash test"
        files = {"doc.md": content}

        zip_data = _create_zip_bytes(files)
        sz_data = _create_7z_bytes(files)

        zip_result = extract_archive(zip_data, "test.zip")
        sz_result = extract_archive(sz_data, "test.7z")

        zip_hash = hashlib.sha256(zip_result[0][1]).hexdigest()
        sz_hash = hashlib.sha256(sz_result[0][1]).hexdigest()

        assert zip_hash == sz_hash
