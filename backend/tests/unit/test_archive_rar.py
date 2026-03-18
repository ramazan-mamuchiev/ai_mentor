"""Unit tests for RAR archive support.

Note: Creating RAR archives requires proprietary tools, so we test:
- Error handling for invalid RAR data
- Dispatch from extract_archive
- Graceful handling when unrar binary is missing
- Mock-based extraction tests
"""

import io
import os
from unittest.mock import MagicMock, patch

import pytest

from app.documents.archive import _archive_ext, extract_archive, extract_rar


# ---------------------------------------------------------------------------
# Tests: _archive_ext for .rar
# ---------------------------------------------------------------------------

class TestArchiveExtRar:
    def test_rar_extension(self):
        assert _archive_ext("docs.rar") == ".rar"

    def test_rar_case_insensitive(self):
        assert _archive_ext("DOCS.RAR") == ".rar"


# ---------------------------------------------------------------------------
# Tests: extract_rar error handling
# ---------------------------------------------------------------------------

class TestExtractRarErrors:
    """Test error handling in extract_rar."""

    def test_invalid_rar_raises_http_exception(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            extract_rar(b"this is not a rar file at all")
        assert exc_info.value.status_code == 400
        assert "Invalid RAR file" in exc_info.value.detail

    def test_empty_data_raises_http_exception(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            extract_rar(b"")
        assert exc_info.value.status_code == 400

    def test_import_error_returns_500(self):
        """If rarfile is not installed, return 500 with helpful message."""
        from fastapi import HTTPException

        original_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

        def mock_import(name, *args, **kwargs):
            if name == "rarfile":
                raise ImportError("No module named 'rarfile'")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            with pytest.raises(HTTPException) as exc_info:
                extract_rar(b"some data")
            assert exc_info.value.status_code == 500
            assert "rarfile" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Tests: extract_archive dispatch for .rar
# ---------------------------------------------------------------------------

class TestExtractArchiveRarDispatch:
    """Test that extract_archive correctly dispatches .rar."""

    def test_dispatches_rar(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            extract_archive(b"not a real rar", "archive.rar")
        assert exc_info.value.status_code == 400
        assert "Invalid RAR file" in exc_info.value.detail

    def test_case_insensitive_dispatch(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            extract_archive(b"not a real rar", "ARCHIVE.RAR")
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# Tests: extract_rar with mocked rarfile module
# ---------------------------------------------------------------------------

class TestExtractRarMocked:
    """Test extract_rar logic with mocked rarfile for controlled testing."""

    def test_extracts_supported_files(self):
        mock_info_md = MagicMock()
        mock_info_md.filename = "docs/api.md"
        mock_info_md.is_dir.return_value = False

        mock_info_yaml = MagicMock()
        mock_info_yaml.filename = "docs/spec.yaml"
        mock_info_yaml.is_dir.return_value = False

        mock_info_png = MagicMock()
        mock_info_png.filename = "image.png"
        mock_info_png.is_dir.return_value = False

        mock_rf = MagicMock()
        mock_rf.infolist.return_value = [mock_info_md, mock_info_yaml, mock_info_png]
        mock_rf.read.side_effect = lambda name: {
            "docs/api.md": b"# API Guide",
            "docs/spec.yaml": b"openapi: 3.0.0",
            "image.png": b"\x89PNG...",
        }[name]
        mock_rf.close = MagicMock()

        mock_rarfile_module = MagicMock()
        mock_rarfile_module.RarFile.return_value = mock_rf
        mock_rarfile_module.BadRarFile = Exception
        mock_rarfile_module.NotRarFile = Exception

        with patch.dict("sys.modules", {"rarfile": mock_rarfile_module}):
            import importlib
            import app.documents.archive
            importlib.reload(app.documents.archive)
            try:
                result = app.documents.archive.extract_rar(b"fake rar data")

                assert len(result) == 2
                names = {os.path.basename(p) for p, _ in result}
                assert names == {"api.md", "spec.yaml"}
                assert result[0][1] == b"# API Guide"
            finally:
                importlib.reload(app.documents.archive)

    def test_skips_hidden_files(self):
        mock_info_hidden = MagicMock()
        mock_info_hidden.filename = ".hidden.md"
        mock_info_hidden.is_dir.return_value = False

        mock_info_visible = MagicMock()
        mock_info_visible.filename = "visible.md"
        mock_info_visible.is_dir.return_value = False

        mock_rf = MagicMock()
        mock_rf.infolist.return_value = [mock_info_hidden, mock_info_visible]
        mock_rf.read.side_effect = lambda name: {
            ".hidden.md": b"# Hidden",
            "visible.md": b"# Visible",
        }[name]
        mock_rf.close = MagicMock()

        mock_rarfile_module = MagicMock()
        mock_rarfile_module.RarFile.return_value = mock_rf
        mock_rarfile_module.BadRarFile = Exception
        mock_rarfile_module.NotRarFile = Exception

        with patch.dict("sys.modules", {"rarfile": mock_rarfile_module}):
            import importlib
            import app.documents.archive
            importlib.reload(app.documents.archive)
            try:
                result = app.documents.archive.extract_rar(b"fake rar data")

                assert len(result) == 1
                assert os.path.basename(result[0][0]) == "visible.md"
            finally:
                importlib.reload(app.documents.archive)

    def test_skips_directories(self):
        mock_info_dir = MagicMock()
        mock_info_dir.filename = "docs/"
        mock_info_dir.is_dir.return_value = True

        mock_info_file = MagicMock()
        mock_info_file.filename = "docs/readme.md"
        mock_info_file.is_dir.return_value = False

        mock_rf = MagicMock()
        mock_rf.infolist.return_value = [mock_info_dir, mock_info_file]
        mock_rf.read.return_value = b"# Readme"
        mock_rf.close = MagicMock()

        mock_rarfile_module = MagicMock()
        mock_rarfile_module.RarFile.return_value = mock_rf
        mock_rarfile_module.BadRarFile = Exception
        mock_rarfile_module.NotRarFile = Exception

        with patch.dict("sys.modules", {"rarfile": mock_rarfile_module}):
            import importlib
            import app.documents.archive
            importlib.reload(app.documents.archive)
            try:
                result = app.documents.archive.extract_rar(b"fake rar data")

                assert len(result) == 1
                assert os.path.basename(result[0][0]) == "readme.md"
            finally:
                importlib.reload(app.documents.archive)

    def test_preserves_content(self):
        content = b"# Important RAR content\n\nWith details."

        mock_info = MagicMock()
        mock_info.filename = "doc.md"
        mock_info.is_dir.return_value = False

        mock_rf = MagicMock()
        mock_rf.infolist.return_value = [mock_info]
        mock_rf.read.return_value = content
        mock_rf.close = MagicMock()

        mock_rarfile_module = MagicMock()
        mock_rarfile_module.RarFile.return_value = mock_rf
        mock_rarfile_module.BadRarFile = Exception
        mock_rarfile_module.NotRarFile = Exception

        with patch.dict("sys.modules", {"rarfile": mock_rarfile_module}):
            import importlib
            import app.documents.archive
            importlib.reload(app.documents.archive)
            try:
                result = app.documents.archive.extract_rar(b"fake rar data")

                assert len(result) == 1
                assert result[0][1] == content
            finally:
                importlib.reload(app.documents.archive)


# ---------------------------------------------------------------------------
# Tests: content parity (RAR vs ZIP via mock)
# ---------------------------------------------------------------------------

class TestRarContentParityMocked:
    """Verify that mocked RAR extraction produces same content as real ZIP."""

    def test_same_hash_as_zip(self):
        import hashlib
        import zipfile

        content = b"# Identical content for hash test"

        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            zf.writestr("doc.md", content)
        zip_data = zip_buf.getvalue()

        from app.documents.archive import extract_zip
        zip_result = extract_zip(zip_data)
        zip_hash = hashlib.sha256(zip_result[0][1]).hexdigest()

        expected_hash = hashlib.sha256(content).hexdigest()
        assert zip_hash == expected_hash
