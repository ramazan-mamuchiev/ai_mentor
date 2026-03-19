"""Unit tests for ingest_from_bytes (synchronous pipeline for Celery worker)."""

import os
import tempfile
from unittest.mock import MagicMock, patch, call

import pytest


def _make_mock_document(doc_id=1, **overrides):
    doc = MagicMock()
    doc.id = doc_id
    doc.format = overrides.get("format", "auto")
    doc.file_size_bytes = overrides.get("file_size_bytes", 100)
    doc.status = overrides.get("status", "pending")
    doc.error_message = None
    doc.total_chunks = 0
    return doc


def _write_temp_file(content: str, suffix: str = ".md") -> str:
    """Write content to a temp file and return its path."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)
    return path


class TestIngestFromBytesAutoDetect:
    """Test format auto-detection in ingest_from_bytes."""

    @patch("app.ingestion.pipeline.embed_texts", return_value=[[0.1] * 1024])
    @patch("app.ingestion.pipeline.chunk_sections")
    @patch("app.ingestion.pipeline.parse_markdown")
    def test_auto_detects_markdown(self, mock_parse, mock_chunk, mock_embed):
        from app.ingestion.pipeline import ingest_from_bytes
        from collections import namedtuple
        ChunkData = namedtuple("ChunkData", ["heading_path", "heading_level", "content", "token_count"])

        mock_parse.return_value = [{"heading": "Test", "content": "Hello", "level": 1}]
        mock_chunk.return_value = [ChunkData("Test", 1, "Hello", 5)]

        doc = _make_mock_document(format="auto")
        path = _write_temp_file("# Test\n\nHello")

        mock_session = MagicMock()
        mock_session.execute.return_value.scalars.return_value.all.return_value = []

        try:
            result = ingest_from_bytes(
                session=mock_session, document=doc,
                file_path=path, original_filename="test.md",
            )
            assert result["status"] == "ok"
            assert result["chunks"] == 1
            assert doc.format == "markdown"
        finally:
            os.unlink(path)


class TestIngestFromBytesMarkdown:
    """Test markdown ingestion path."""

    @patch("app.ingestion.pipeline.embed_texts")
    @patch("app.ingestion.pipeline.chunk_sections")
    @patch("app.ingestion.pipeline.parse_markdown")
    def test_successful_markdown_ingestion(self, mock_parse, mock_chunk, mock_embed):
        from app.ingestion.pipeline import ingest_from_bytes
        from collections import namedtuple
        ChunkData = namedtuple("ChunkData", ["heading_path", "heading_level", "content", "token_count"])

        mock_parse.return_value = [
            {"heading": "API", "content": "Endpoint docs", "level": 1},
            {"heading": "Auth", "content": "Token auth", "level": 2},
        ]
        mock_chunk.return_value = [
            ChunkData("API", 1, "Endpoint docs", 10),
            ChunkData("API > Auth", 2, "Token auth", 8),
        ]
        mock_embed.return_value = [[0.1] * 1024, [0.2] * 1024]

        doc = _make_mock_document(format="markdown")
        path = _write_temp_file("# API\n\nEndpoint docs\n\n## Auth\n\nToken auth")

        mock_session = MagicMock()
        mock_session.execute.return_value.scalars.return_value.all.return_value = []

        try:
            result = ingest_from_bytes(
                session=mock_session, document=doc,
                file_path=path, original_filename="api.md",
            )
            assert result["status"] == "ok"
            assert result["chunks"] == 2
            assert doc.total_chunks == 2
            assert doc.status == "ready"
            mock_session.commit.assert_called()
        finally:
            os.unlink(path)


class TestIngestFromBytesPdf:
    """Test PDF ingestion path."""

    @patch("app.ingestion.pipeline.embed_texts", return_value=[[0.1] * 1024])
    @patch("app.ingestion.pipeline.chunk_sections")
    @patch("app.ingestion.pipeline._parse_content")
    @patch("app.ingestion.pipeline.convert_pdf")
    def test_pdf_conversion_called(self, mock_convert_pdf, mock_parse, mock_chunk, mock_embed):
        from app.ingestion.pipeline import ingest_from_bytes
        from collections import namedtuple
        ChunkData = namedtuple("ChunkData", ["heading_path", "heading_level", "content", "token_count"])

        mock_convert_pdf.return_value = ("# PDF Content\n\nExtracted text", {"total_ms": 100.0})
        mock_parse.return_value = [{"heading": "PDF", "content": "text", "level": 1}]
        mock_chunk.return_value = [ChunkData("PDF", 1, "Extracted text", 5)]

        doc = _make_mock_document(format="pdf")
        path = _write_temp_file("fake pdf", suffix=".pdf")

        mock_session = MagicMock()
        mock_session.execute.return_value.scalars.return_value.all.return_value = []

        try:
            result = ingest_from_bytes(
                session=mock_session, document=doc,
                file_path=path, original_filename="manual.pdf",
            )
            assert result["status"] == "ok"
            mock_convert_pdf.assert_called_once()
            assert "convert_metadata" in result
        finally:
            os.unlink(path)

    @patch("app.ingestion.pipeline.convert_pdf", side_effect=RuntimeError("PDF corrupt"))
    def test_pdf_conversion_failure(self, mock_convert_pdf):
        from app.ingestion.pipeline import ingest_from_bytes

        doc = _make_mock_document(format="pdf")
        path = _write_temp_file("bad pdf", suffix=".pdf")

        mock_session = MagicMock()

        try:
            result = ingest_from_bytes(
                session=mock_session, document=doc,
                file_path=path, original_filename="bad.pdf",
            )
            assert result["status"] == "error"
            assert "PDF corrupt" in result["error"]
            assert "PDF conversion failed" in doc.error_message
            assert doc.status == "error"
            mock_session.commit.assert_called()
        finally:
            os.unlink(path)


class TestIngestFromBytesSwagger:
    """Test Swagger/OpenAPI ingestion path."""

    @patch("app.ingestion.pipeline.embed_texts", return_value=[[0.1] * 1024])
    @patch("app.ingestion.pipeline.chunk_sections")
    @patch("app.ingestion.pipeline._parse_content")
    @patch("app.ingestion.pipeline.convert_swagger_file")
    def test_swagger_conversion_called(self, mock_convert, mock_parse, mock_chunk, mock_embed):
        from app.ingestion.pipeline import ingest_from_bytes
        from collections import namedtuple
        ChunkData = namedtuple("ChunkData", ["heading_path", "heading_level", "content", "token_count"])

        mock_convert.return_value = ("# API\n\n## GET /test", {"total_ms": 50.0, "endpoints": 1})
        mock_parse.return_value = [{"heading": "GET /test", "content": "endpoint", "level": 2}]
        mock_chunk.return_value = [ChunkData("GET /test", 2, "endpoint", 5)]

        doc = _make_mock_document(format="swagger")
        path = _write_temp_file('{"openapi": "3.0.0"}', suffix=".json")

        mock_session = MagicMock()
        mock_session.execute.return_value.scalars.return_value.all.return_value = []

        try:
            result = ingest_from_bytes(
                session=mock_session, document=doc,
                file_path=path, original_filename="api.json",
            )
            assert result["status"] == "ok"
            mock_convert.assert_called_once()
        finally:
            os.unlink(path)

    @patch("app.ingestion.pipeline.convert_swagger_file", side_effect=ValueError("Invalid spec"))
    def test_swagger_conversion_failure(self, mock_convert):
        from app.ingestion.pipeline import ingest_from_bytes

        doc = _make_mock_document(format="swagger")
        path = _write_temp_file("bad yaml", suffix=".yaml")

        mock_session = MagicMock()

        try:
            result = ingest_from_bytes(
                session=mock_session, document=doc,
                file_path=path, original_filename="bad.yaml",
            )
            assert result["status"] == "error"
            assert "Invalid spec" in result["error"]
            assert "Swagger conversion failed" in doc.error_message
            assert doc.status == "error"
        finally:
            os.unlink(path)


class TestIngestFromBytesProto:
    """Test proto ingestion passes original_filename to the converter."""

    @patch("app.ingestion.pipeline.embed_texts", return_value=[[0.1] * 1024])
    @patch("app.ingestion.pipeline.chunk_sections")
    @patch("app.ingestion.pipeline._parse_content")
    @patch("app.ingestion.pipeline.convert_proto_file")
    def test_proto_passes_original_filename(self, mock_convert_proto, mock_parse, mock_chunk, mock_embed):
        from app.ingestion.pipeline import ingest_from_bytes
        from collections import namedtuple
        ChunkData = namedtuple("ChunkData", ["heading_path", "heading_level", "content", "token_count"])

        mock_convert_proto.return_value = ("# AcfaService.proto\n\nService content", {"total_ms": 10.0})
        mock_parse.return_value = [{"heading": "AcfaService", "content": "Service content", "level": 1}]
        mock_chunk.return_value = [ChunkData("AcfaService", 1, "Service content", 5)]

        doc = _make_mock_document(format="proto")
        path = _write_temp_file('syntax = "proto3";', suffix=".proto")

        mock_session = MagicMock()
        mock_session.execute.return_value.scalars.return_value.all.return_value = []

        try:
            result = ingest_from_bytes(
                session=mock_session, document=doc,
                file_path=path, original_filename="AcfaService.proto",
            )
            assert result["status"] == "ok"
            mock_convert_proto.assert_called_once_with(path, original_filename="AcfaService.proto")
        finally:
            os.unlink(path)

    @patch("app.ingestion.pipeline.convert_proto_file", side_effect=RuntimeError("Parse error"))
    def test_proto_conversion_failure(self, mock_convert_proto):
        from app.ingestion.pipeline import ingest_from_bytes

        doc = _make_mock_document(format="proto")
        path = _write_temp_file("bad proto", suffix=".proto")

        mock_session = MagicMock()

        try:
            result = ingest_from_bytes(
                session=mock_session, document=doc,
                file_path=path, original_filename="Bad.proto",
            )
            assert result["status"] == "error"
            assert "Parse error" in result["error"]
            assert "Proto conversion failed" in doc.error_message
            assert doc.status == "error"
            mock_session.commit.assert_called()
        finally:
            os.unlink(path)

    @patch("app.ingestion.pipeline.embed_texts", return_value=[[0.1] * 1024])
    @patch("app.ingestion.pipeline.chunk_sections")
    @patch("app.ingestion.pipeline.parse_markdown")
    def test_auto_detect_uses_original_filename_for_proto(self, mock_parse, mock_chunk, mock_embed):
        """When format=auto, detect_format should use original_filename (not temp path)."""
        from app.ingestion.pipeline import ingest_from_bytes
        from collections import namedtuple
        ChunkData = namedtuple("ChunkData", ["heading_path", "heading_level", "content", "token_count"])

        mock_parse.return_value = [{"heading": "Test", "content": "data", "level": 1}]
        mock_chunk.return_value = [ChunkData("Test", 1, "data", 5)]

        doc = _make_mock_document(format="auto")
        path = _write_temp_file('syntax = "proto3";', suffix=".bin")

        mock_session = MagicMock()
        mock_session.execute.return_value.scalars.return_value.all.return_value = []

        try:
            with patch("app.ingestion.pipeline.convert_proto_file") as mock_proto:
                mock_proto.return_value = ("# Test\n\ndata", {"total_ms": 5.0})
                result = ingest_from_bytes(
                    session=mock_session, document=doc,
                    file_path=path, original_filename="TestService.proto",
                )
                assert doc.format == "proto"
                mock_proto.assert_called_once_with(path, original_filename="TestService.proto")
        finally:
            os.unlink(path)


ALLMAN_PROTO_CONTENT = """\
syntax = "proto3";
package axxonsoft.bl.acfa;

service AcfaService
{
    rpc ListUnitsEvents(ListUnitsEventsRequest) returns (stream ListUnitsEventsResponse);
}

message ListUnitsEventsRequest
{
    message Unit
    {
        string uid = 1;
    }

    repeated Unit items = 1;
    int32 portion_size = 2;
}

message ListUnitsEventsResponse
{
    message UnitEvents
    {
        string uid = 1;
        repeated string events = 2;
    }

    repeated UnitEvents items = 1;
    bool more_data = 2;
}

enum EStatesMode
{
    SM_ALL = 0;
    SM_CURRENT = 1;
}
"""


class TestIngestFromBytesAllmanProto:
    """Test that Allman-style proto files are correctly processed through ingest_from_bytes."""

    @patch("app.ingestion.pipeline.embed_texts")
    def test_allman_proto_produces_multiple_chunks(self, mock_embed):
        """Real conversion (no mock on converter) — Allman proto should produce >1 chunk."""
        from app.ingestion.pipeline import ingest_from_bytes

        mock_embed.side_effect = lambda texts, **kw: [[0.1] * 1024 for _ in texts]

        doc = _make_mock_document(format="proto")
        path = _write_temp_file(ALLMAN_PROTO_CONTENT, suffix=".proto")

        mock_session = MagicMock()
        mock_session.execute.return_value.scalars.return_value.all.return_value = []

        try:
            result = ingest_from_bytes(
                session=mock_session, document=doc,
                file_path=path, original_filename="AcfaService.proto",
            )
            assert result["status"] == "ok"
            assert result["chunks"] > 1, (
                f"Allman-style proto should produce multiple chunks, got {result['chunks']}"
            )
            assert doc.status == "ready"
        finally:
            os.unlink(path)

    @patch("app.ingestion.pipeline.embed_texts")
    def test_allman_proto_heading_uses_original_filename(self, mock_embed):
        """Chunks heading_path should reference original filename, not temp path."""
        from app.ingestion.pipeline import ingest_from_bytes

        mock_embed.side_effect = lambda texts, **kw: [[0.1] * 1024 for _ in texts]

        doc = _make_mock_document(format="proto")
        path = _write_temp_file(ALLMAN_PROTO_CONTENT, suffix=".proto")

        mock_session = MagicMock()
        mock_session.execute.return_value.scalars.return_value.all.return_value = []

        added_chunks = []
        original_add = mock_session.add

        def capture_add(obj):
            if hasattr(obj, "heading_path"):
                added_chunks.append(obj)
            return original_add(obj)

        mock_session.add = capture_add

        try:
            result = ingest_from_bytes(
                session=mock_session, document=doc,
                file_path=path, original_filename="AcfaService.proto",
            )
            assert result["status"] == "ok"
            assert len(added_chunks) > 0
            all_headings = " ".join(c.heading_path for c in added_chunks)
            assert "AcfaService.proto" in all_headings
            assert "tmp" not in all_headings.lower()
        finally:
            os.unlink(path)

    @patch("app.ingestion.pipeline.embed_texts")
    def test_allman_proto_chunks_contain_key_content(self, mock_embed):
        """Chunks should contain service/message/enum names from the Allman proto."""
        from app.ingestion.pipeline import ingest_from_bytes

        mock_embed.side_effect = lambda texts, **kw: [[0.1] * 1024 for _ in texts]

        doc = _make_mock_document(format="proto")
        path = _write_temp_file(ALLMAN_PROTO_CONTENT, suffix=".proto")

        mock_session = MagicMock()
        mock_session.execute.return_value.scalars.return_value.all.return_value = []

        added_chunks = []
        original_add = mock_session.add

        def capture_add(obj):
            if hasattr(obj, "content") and hasattr(obj, "heading_path"):
                added_chunks.append(obj)
            return original_add(obj)

        mock_session.add = capture_add

        try:
            result = ingest_from_bytes(
                session=mock_session, document=doc,
                file_path=path, original_filename="AcfaService.proto",
            )
            assert result["status"] == "ok"
            all_text = " ".join(
                f"{c.heading_path} {c.content}" for c in added_chunks
            )
            assert "AcfaService" in all_text
            assert "ListUnitsEventsResponse" in all_text
            assert "ListUnitsEventsRequest" in all_text
            assert "EStatesMode" in all_text
        finally:
            os.unlink(path)

    @patch("app.ingestion.pipeline.embed_texts")
    def test_allman_auto_detect_from_original_filename(self, mock_embed):
        """format=auto + original_filename=X.proto should detect proto and parse Allman."""
        from app.ingestion.pipeline import ingest_from_bytes

        mock_embed.side_effect = lambda texts, **kw: [[0.1] * 1024 for _ in texts]

        doc = _make_mock_document(format="auto")
        path = _write_temp_file(ALLMAN_PROTO_CONTENT, suffix=".bin")

        mock_session = MagicMock()
        mock_session.execute.return_value.scalars.return_value.all.return_value = []

        try:
            result = ingest_from_bytes(
                session=mock_session, document=doc,
                file_path=path, original_filename="AcfaService.proto",
            )
            assert doc.format == "proto"
            assert result["status"] == "ok"
            assert result["chunks"] > 1
        finally:
            os.unlink(path)


class TestIngestFromBytesNoContent:
    """Test behavior when no chunks are extracted."""

    @patch("app.ingestion.pipeline.chunk_sections", return_value=[])
    @patch("app.ingestion.pipeline.parse_markdown", return_value=[])
    def test_returns_error_on_empty_content(self, mock_parse, mock_chunk):
        from app.ingestion.pipeline import ingest_from_bytes

        doc = _make_mock_document(format="markdown")
        path = _write_temp_file("")

        mock_session = MagicMock()
        mock_session.execute.return_value.scalars.return_value.all.return_value = []

        try:
            result = ingest_from_bytes(
                session=mock_session, document=doc,
                file_path=path, original_filename="empty.md",
            )
            assert result["status"] == "error"
            assert "No content extracted" in result["error"]
            assert doc.status == "error"
        finally:
            os.unlink(path)


class TestIngestFromBytesFileReadError:
    """Test behavior when file cannot be read."""

    def test_returns_error_on_unreadable_file(self):
        from app.ingestion.pipeline import ingest_from_bytes

        doc = _make_mock_document(format="markdown")
        mock_session = MagicMock()

        result = ingest_from_bytes(
            session=mock_session, document=doc,
            file_path="/nonexistent/path/file.md",
            original_filename="missing.md",
        )
        assert result["status"] == "error"
        assert doc.status == "error"
        mock_session.commit.assert_called()


class TestIngestFromBytesEmbeddingFailure:
    """Test behavior when embedding step fails."""

    @patch("app.ingestion.pipeline.embed_texts", side_effect=RuntimeError("Model not loaded"))
    @patch("app.ingestion.pipeline.chunk_sections")
    @patch("app.ingestion.pipeline.parse_markdown")
    def test_returns_error_on_embedding_failure(self, mock_parse, mock_chunk, mock_embed):
        from app.ingestion.pipeline import ingest_from_bytes
        from collections import namedtuple
        ChunkData = namedtuple("ChunkData", ["heading_path", "heading_level", "content", "token_count"])

        mock_parse.return_value = [{"heading": "Test", "content": "data", "level": 1}]
        mock_chunk.return_value = [ChunkData("Test", 1, "data", 5)]

        doc = _make_mock_document(format="markdown")
        path = _write_temp_file("# Test\n\ndata")

        mock_session = MagicMock()
        mock_session.execute.return_value.scalars.return_value.all.return_value = []

        try:
            result = ingest_from_bytes(
                session=mock_session, document=doc,
                file_path=path, original_filename="test.md",
            )
            assert result["status"] == "error"
            assert "Model not loaded" in result["error"]
            assert doc.status == "error"
        finally:
            os.unlink(path)


class TestIngestFromBytesExistingChunks:
    """Test that existing chunks are deleted before re-ingestion."""

    @patch("app.ingestion.pipeline.embed_texts", return_value=[[0.1] * 1024])
    @patch("app.ingestion.pipeline.chunk_sections")
    @patch("app.ingestion.pipeline.parse_markdown")
    def test_deletes_old_chunks(self, mock_parse, mock_chunk, mock_embed):
        from app.ingestion.pipeline import ingest_from_bytes
        from collections import namedtuple
        ChunkData = namedtuple("ChunkData", ["heading_path", "heading_level", "content", "token_count"])

        mock_parse.return_value = [{"heading": "New", "content": "content", "level": 1}]
        mock_chunk.return_value = [ChunkData("New", 1, "content", 5)]

        old_chunk = MagicMock()
        doc = _make_mock_document(format="markdown")
        path = _write_temp_file("# New\n\ncontent")

        mock_session = MagicMock()
        mock_session.execute.return_value.scalars.return_value.all.return_value = [old_chunk]

        try:
            result = ingest_from_bytes(
                session=mock_session, document=doc,
                file_path=path, original_filename="test.md",
            )
            assert result["status"] == "ok"
            mock_session.delete.assert_any_call(old_chunk)
        finally:
            os.unlink(path)
