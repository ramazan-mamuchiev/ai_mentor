"""Unit tests for tar archive family support (.tar, .tar.gz, .tgz, .tar.bz2, .tar.xz)."""

import bz2
import gzip
import hashlib
import io
import lzma
import os
import tarfile

import pytest

from app.documents.archive import (
    _archive_ext,
    extract_archive,
    extract_tar,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_tar_bytes(files: dict[str, bytes], compression: str = "") -> bytes:
    """Create a tar archive in memory.

    compression: "" (none), "gz", "bz2", "xz"
    """
    buf = io.BytesIO()
    mode = f"w:{compression}" if compression else "w"
    with tarfile.open(fileobj=buf, mode=mode) as tf:
        for name, data in files.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Tests: _archive_ext helper
# ---------------------------------------------------------------------------

class TestArchiveExt:
    """Test compound extension detection."""

    def test_tar_gz(self):
        assert _archive_ext("docs.tar.gz") == ".tar.gz"

    def test_tar_bz2(self):
        assert _archive_ext("docs.tar.bz2") == ".tar.bz2"

    def test_tar_xz(self):
        assert _archive_ext("docs.tar.xz") == ".tar.xz"

    def test_tgz(self):
        assert _archive_ext("docs.tgz") == ".tgz"

    def test_plain_tar(self):
        assert _archive_ext("docs.tar") == ".tar"

    def test_zip(self):
        assert _archive_ext("docs.zip") == ".zip"

    def test_7z(self):
        assert _archive_ext("docs.7z") == ".7z"

    def test_rar(self):
        assert _archive_ext("docs.rar") == ".rar"

    def test_case_insensitive(self):
        assert _archive_ext("DOCS.TAR.GZ") == ".tar.gz"
        assert _archive_ext("Archive.TAR.BZ2") == ".tar.bz2"


# ---------------------------------------------------------------------------
# Tests: extract_tar — plain .tar
# ---------------------------------------------------------------------------

class TestExtractTarPlain:
    """Test extraction from uncompressed .tar archives."""

    def test_extracts_supported_files(self):
        files = {
            "docs/api.md": b"# API Guide",
            "docs/spec.yaml": b"openapi: 3.0.0",
            "docs/schema.proto": b'syntax = "proto3";',
        }
        data = _create_tar_bytes(files)
        result = extract_tar(data, ".tar")

        names = {os.path.basename(p) for p, _ in result}
        assert names == {"api.md", "spec.yaml", "schema.proto"}

    def test_skips_unsupported_extensions(self):
        files = {
            "readme.md": b"# Readme",
            "image.png": b"\x89PNG...",
            "binary.exe": b"MZ...",
        }
        data = _create_tar_bytes(files)
        result = extract_tar(data, ".tar")

        assert len(result) == 1
        assert os.path.basename(result[0][0]) == "readme.md"

    def test_skips_hidden_files(self):
        files = {
            ".hidden.md": b"# Hidden",
            "visible.md": b"# Visible",
        }
        data = _create_tar_bytes(files)
        result = extract_tar(data, ".tar")

        assert len(result) == 1
        assert os.path.basename(result[0][0]) == "visible.md"

    def test_preserves_content(self):
        content = b"# Important Documentation\n\nWith detailed content."
        files = {"doc.md": content}
        data = _create_tar_bytes(files)
        result = extract_tar(data, ".tar")

        assert len(result) == 1
        assert result[0][1] == content

    def test_invalid_tar_raises_http_exception(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            extract_tar(b"this is not a tar file", ".tar")
        assert exc_info.value.status_code == 400
        assert "Invalid tar archive" in exc_info.value.detail

    def test_empty_archive(self):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tf:
            pass
        data = buf.getvalue()
        result = extract_tar(data, ".tar")
        assert result == []

    def test_nested_directory_structure(self):
        files = {
            "project/docs/api.md": b"# API",
            "project/docs/proto/service.proto": b'syntax = "proto3";',
            "project/config.yaml": b"key: value",
        }
        data = _create_tar_bytes(files)
        result = extract_tar(data, ".tar")

        paths = [p for p, _ in result]
        assert len(paths) == 3


# ---------------------------------------------------------------------------
# Tests: extract_tar — .tar.gz / .tgz
# ---------------------------------------------------------------------------

class TestExtractTarGz:
    """Test extraction from gzip-compressed tar archives."""

    def test_extracts_tar_gz(self):
        files = {"readme.md": b"# Hello", "spec.yaml": b"openapi: 3.0.0"}
        data = _create_tar_bytes(files, compression="gz")
        result = extract_tar(data, ".tar.gz")

        assert len(result) == 2

    def test_extracts_tgz(self):
        files = {"readme.md": b"# Hello"}
        data = _create_tar_bytes(files, compression="gz")
        result = extract_tar(data, ".tgz")

        assert len(result) == 1
        assert result[0][1] == b"# Hello"

    def test_preserves_content_gz(self):
        content = b"Complex content with special chars: \xc3\xa9\xc3\xa0\xc3\xbc"
        files = {"doc.md": content}
        data = _create_tar_bytes(files, compression="gz")
        result = extract_tar(data, ".tar.gz")

        assert result[0][1] == content


# ---------------------------------------------------------------------------
# Tests: extract_tar — .tar.bz2
# ---------------------------------------------------------------------------

class TestExtractTarBz2:
    """Test extraction from bzip2-compressed tar archives."""

    def test_extracts_tar_bz2(self):
        files = {"api.md": b"# API", "schema.proto": b'syntax = "proto3";'}
        data = _create_tar_bytes(files, compression="bz2")
        result = extract_tar(data, ".tar.bz2")

        assert len(result) == 2

    def test_preserves_content_bz2(self):
        content = b"# BZ2 compressed documentation\n\n" + b"x" * 1000
        files = {"large.md": content}
        data = _create_tar_bytes(files, compression="bz2")
        result = extract_tar(data, ".tar.bz2")

        assert result[0][1] == content


# ---------------------------------------------------------------------------
# Tests: extract_tar — .tar.xz
# ---------------------------------------------------------------------------

class TestExtractTarXz:
    """Test extraction from xz-compressed tar archives."""

    def test_extracts_tar_xz(self):
        files = {"readme.md": b"# XZ compressed", "spec.json": b'{"openapi": "3.0.0"}'}
        data = _create_tar_bytes(files, compression="xz")
        result = extract_tar(data, ".tar.xz")

        assert len(result) == 2

    def test_preserves_content_xz(self):
        content = b"# XZ content preservation test"
        files = {"doc.md": content}
        data = _create_tar_bytes(files, compression="xz")
        result = extract_tar(data, ".tar.xz")

        assert result[0][1] == content


# ---------------------------------------------------------------------------
# Tests: extract_archive dispatch for tar family
# ---------------------------------------------------------------------------

class TestExtractArchiveTarDispatch:
    """Test that extract_archive correctly dispatches tar variants."""

    def test_dispatches_tar(self):
        files = {"doc.md": b"# Hello"}
        data = _create_tar_bytes(files)
        result = extract_archive(data, "archive.tar")
        assert len(result) == 1

    def test_dispatches_tar_gz(self):
        files = {"doc.md": b"# Hello"}
        data = _create_tar_bytes(files, compression="gz")
        result = extract_archive(data, "archive.tar.gz")
        assert len(result) == 1

    def test_dispatches_tgz(self):
        files = {"doc.md": b"# Hello"}
        data = _create_tar_bytes(files, compression="gz")
        result = extract_archive(data, "archive.tgz")
        assert len(result) == 1

    def test_dispatches_tar_bz2(self):
        files = {"doc.md": b"# Hello"}
        data = _create_tar_bytes(files, compression="bz2")
        result = extract_archive(data, "archive.tar.bz2")
        assert len(result) == 1

    def test_dispatches_tar_xz(self):
        files = {"doc.md": b"# Hello"}
        data = _create_tar_bytes(files, compression="xz")
        result = extract_archive(data, "archive.tar.xz")
        assert len(result) == 1

    def test_case_insensitive(self):
        files = {"doc.md": b"# Hello"}
        data = _create_tar_bytes(files, compression="gz")
        result = extract_archive(data, "ARCHIVE.TAR.GZ")
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Tests: content parity across all tar compression types
# ---------------------------------------------------------------------------

class TestTarContentParity:
    """Verify identical content from all tar compression variants."""

    def test_same_content_all_compressions(self):
        content = b"# Identical content for parity test\n\nWith paragraphs."
        files = {"doc.md": content}

        for compression, ext in [("", ".tar"), ("gz", ".tar.gz"), ("bz2", ".tar.bz2"), ("xz", ".tar.xz")]:
            data = _create_tar_bytes(files, compression=compression)
            result = extract_tar(data, ext)
            assert len(result) == 1, f"Failed for {ext}"
            assert result[0][1] == content, f"Content mismatch for {ext}"

    def test_same_hashes_all_compressions(self):
        content = b"# Hash parity test"
        files = {"doc.md": content}
        expected_hash = hashlib.sha256(content).hexdigest()

        for compression, ext in [("", ".tar"), ("gz", ".tar.gz"), ("bz2", ".tar.bz2"), ("xz", ".tar.xz")]:
            data = _create_tar_bytes(files, compression=compression)
            result = extract_tar(data, ext)
            actual_hash = hashlib.sha256(result[0][1]).hexdigest()
            assert actual_hash == expected_hash, f"Hash mismatch for {ext}"


# ---------------------------------------------------------------------------
# Tests: tar edge cases
# ---------------------------------------------------------------------------

class TestTarEdgeCases:
    """Test edge cases specific to tar format."""

    def test_tar_with_only_unsupported_files(self):
        files = {"image.png": b"\x89PNG...", "binary.exe": b"MZ..."}
        data = _create_tar_bytes(files)
        result = extract_tar(data, ".tar")
        assert result == []

    def test_tar_with_directories_skipped(self):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tf:
            dir_info = tarfile.TarInfo(name="docs/")
            dir_info.type = tarfile.DIRTYPE
            tf.addfile(dir_info)

            file_info = tarfile.TarInfo(name="docs/readme.md")
            content = b"# Hello"
            file_info.size = len(content)
            tf.addfile(file_info, io.BytesIO(content))

        data = buf.getvalue()
        result = extract_tar(data, ".tar")
        assert len(result) == 1
        assert os.path.basename(result[0][0]) == "readme.md"

    def test_tar_preserves_binary_content(self):
        pdf_header = b"%PDF-1.4\n" + os.urandom(512)
        files = {"document.pdf": pdf_header}
        data = _create_tar_bytes(files)
        result = extract_tar(data, ".tar")

        assert len(result) == 1
        assert result[0][1] == pdf_header

    def test_tar_multiple_files(self):
        files = {
            "api.md": b"# API",
            "spec.yaml": b"openapi: 3.0.0",
            "schema.proto": b'syntax = "proto3";',
            "notes.txt": b"Some notes",
            "config.json": b'{"key": "value"}',
        }
        data = _create_tar_bytes(files, compression="gz")
        result = extract_tar(data, ".tar.gz")

        assert len(result) == 5
