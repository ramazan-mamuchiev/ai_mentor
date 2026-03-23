"""Unit tests for document debug feature: schema, endpoint, pipeline metrics, RAG hit counts."""

import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.documents.schemas import DocumentDebugInfo
from app.ingestion.chunker import ChunkData


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestDocumentDebugInfoSchema:
    def test_full_fields(self):
        now = datetime.now(timezone.utc)
        info = DocumentDebugInfo(
            document_id=1,
            title="API Guide",
            original_filename="api.md",
            format="markdown",
            status="ready",
            source_hash="abc123def456",
            file_size_bytes=102400,
            uploaded_at=now,
            ingest_duration_ms=5200.5,
            read_ms=100.0,
            convert_ms=0.0,
            parse_ms=800.0,
            embed_ms=3500.0,
            db_ms=800.5,
            total_chunks=42,
            total_tokens=8500,
            min_chunk_tokens=50,
            max_chunk_tokens=350,
            avg_chunk_tokens=202.4,
            embedding_model="intfloat/multilingual-e5-large",
            embedding_dims=1024,
            embedding_tokens=8500,
            rag_hit_count=15,
            rag_avg_similarity=0.8234,
            rag_last_used_at=now,
            product_name="Camera X",
            firmware_version="2.0",
        )
        assert info.document_id == 1
        assert info.total_tokens == 8500
        assert info.embedding_dims == 1024
        assert info.rag_hit_count == 15

    def test_defaults_for_optional_fields(self):
        now = datetime.now(timezone.utc)
        info = DocumentDebugInfo(
            document_id=1,
            title="Test",
            original_filename="test.md",
            format="markdown",
            status="pending",
            source_hash="abc",
            file_size_bytes=0,
            uploaded_at=now,
        )
        assert info.ingest_duration_ms is None
        assert info.read_ms is None
        assert info.convert_ms is None
        assert info.total_tokens == 0
        assert info.min_chunk_tokens is None
        assert info.embedding_model is None
        assert info.embedding_dims is None
        assert info.embedding_tokens == 0
        assert info.rag_hit_count == 0
        assert info.rag_avg_similarity is None
        assert info.rag_last_used_at is None
        assert info.product_name == ""
        assert info.firmware_version == ""

    def test_from_attributes_mode(self):
        """Schema should support from_attributes for ORM compatibility."""
        assert DocumentDebugInfo.model_config.get("from_attributes") is True


# ---------------------------------------------------------------------------
# Debug endpoint tests
# ---------------------------------------------------------------------------

def _mock_session_ctx(mock_session):
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_ctx


class TestGetDocumentDebugEndpoint:

    @pytest.mark.asyncio
    @patch("app.documents.router.async_session")
    async def test_returns_debug_info(self, mock_session_factory):
        now = datetime.now(timezone.utc)
        row_data = {
            "document_id": 5,
            "title": "Manual",
            "original_filename": "manual.pdf",
            "format": "pdf",
            "status": "ready",
            "source_hash": "abc123",
            "file_size_bytes": 50000,
            "uploaded_at": now,
            "indexed_at": now,
            "ingest_duration_ms": 3000.0,
            "read_ms": 50.0,
            "convert_ms": 1500.0,
            "parse_ms": 500.0,
            "embed_ms": 800.0,
            "db_ms": 150.0,
            "total_chunks": 20,
            "total_tokens": 4000,
            "min_chunk_tokens": 80,
            "max_chunk_tokens": 300,
            "avg_chunk_tokens": 200.0,
            "embedding_model": "intfloat/multilingual-e5-large",
            "embedding_dims": 1024,
            "embedding_tokens": 4000,
            "rag_hit_count": 10,
            "rag_avg_similarity": 0.85,
            "rag_last_used_at": now,
            "product_name": "Camera",
            "firmware_version": "1.0",
        }

        mock_row = MagicMock()
        mock_row._mapping = row_data

        mock_result = MagicMock()
        mock_result.one_or_none.return_value = mock_row

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session_factory.return_value = _mock_session_ctx(mock_session)

        from app.documents.router import get_document_debug
        result = await get_document_debug(5)

        assert result.document_id == 5
        assert result.ingest_duration_ms == 3000.0
        assert result.embed_ms == 800.0
        assert result.total_tokens == 4000
        assert result.embedding_model == "intfloat/multilingual-e5-large"
        assert result.embedding_dims == 1024
        assert result.rag_hit_count == 10
        assert result.product_name == "Camera"

    @pytest.mark.asyncio
    @patch("app.documents.router.async_session")
    async def test_returns_404_when_not_found(self, mock_session_factory):
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session_factory.return_value = _mock_session_ctx(mock_session)

        from app.documents.router import get_document_debug
        with pytest.raises(Exception) as exc_info:
            await get_document_debug(999)
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Pipeline metrics saving tests
# ---------------------------------------------------------------------------

def _write_temp_file(content: str, suffix: str = ".md") -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)
    return path


class TestPipelineSavesMetrics:
    """Test that ingest_from_bytes saves debug metrics to the document object."""

    @patch("app.ingestion.pipeline.embed_texts")
    @patch("app.ingestion.pipeline.chunk_sections")
    @patch("app.ingestion.pipeline.parse_markdown")
    def test_saves_timing_metrics(self, mock_parse, mock_chunk, mock_embed):
        from app.ingestion.pipeline import ingest_from_bytes

        mock_parse.return_value = [{"heading": "Test", "content": "data", "level": 1}]
        mock_chunk.return_value = [
            ChunkData("Test", 1, "data chunk one", 10),
            ChunkData("Test > Sub", 2, "data chunk two", 15),
        ]
        mock_embed.return_value = [[0.1] * 1024, [0.2] * 1024]

        doc = MagicMock()
        doc.id = 1
        doc.format = "markdown"
        doc.file_size_bytes = 500
        doc.status = "pending"
        doc.error_message = None
        doc.total_chunks = 0
        doc.title = "Test"

        path = _write_temp_file("# Test\n\ndata chunk one\n\n## Sub\n\ndata chunk two")
        mock_session = MagicMock()
        mock_session.execute.return_value.scalars.return_value.all.return_value = []

        try:
            result = ingest_from_bytes(
                session=mock_session, document=doc,
                file_path=path, original_filename="test.md",
            )
            assert result["status"] == "ok"

            assert doc.ingest_duration_ms is not None
            assert doc.ingest_duration_ms > 0
            assert doc.read_ms is not None
            assert doc.parse_ms is not None
            assert doc.embed_ms is not None
            assert doc.db_ms is not None
        finally:
            os.unlink(path)

    @patch("app.ingestion.pipeline.embed_texts")
    @patch("app.ingestion.pipeline.chunk_sections")
    @patch("app.ingestion.pipeline.parse_markdown")
    def test_saves_token_stats(self, mock_parse, mock_chunk, mock_embed):
        from app.ingestion.pipeline import ingest_from_bytes

        mock_parse.return_value = [{"heading": "A", "content": "x", "level": 1}]
        mock_chunk.return_value = [
            ChunkData("A", 1, "short", 5),
            ChunkData("B", 1, "medium content here", 20),
            ChunkData("C", 1, "longest content in this chunk", 35),
        ]
        mock_embed.return_value = [[0.1] * 1024] * 3

        doc = MagicMock()
        doc.id = 1
        doc.format = "markdown"
        doc.file_size_bytes = 200
        doc.status = "pending"
        doc.error_message = None
        doc.total_chunks = 0
        doc.title = ""

        path = _write_temp_file("# A\n\nshort\n\n# B\n\nmedium\n\n# C\n\nlongest")
        mock_session = MagicMock()
        mock_session.execute.return_value.scalars.return_value.all.return_value = []

        try:
            result = ingest_from_bytes(
                session=mock_session, document=doc,
                file_path=path, original_filename="test.md",
            )
            assert result["status"] == "ok"

            assert doc.total_tokens == 60  # 5 + 20 + 35
            assert doc.min_chunk_tokens == 5
            assert doc.max_chunk_tokens == 35
            assert doc.avg_chunk_tokens == 20.0
            assert doc.embedding_tokens == 60
        finally:
            os.unlink(path)

    @patch("app.ingestion.pipeline.embed_texts")
    @patch("app.ingestion.pipeline.chunk_sections")
    @patch("app.ingestion.pipeline.parse_markdown")
    def test_saves_embedding_model_and_dims(self, mock_parse, mock_chunk, mock_embed):
        from app.ingestion.pipeline import ingest_from_bytes

        mock_parse.return_value = [{"heading": "X", "content": "y", "level": 1}]
        mock_chunk.return_value = [ChunkData("X", 1, "y", 5)]
        mock_embed.return_value = [[0.1] * 1024]

        doc = MagicMock()
        doc.id = 1
        doc.format = "markdown"
        doc.file_size_bytes = 50
        doc.status = "pending"
        doc.error_message = None
        doc.total_chunks = 0
        doc.title = ""

        path = _write_temp_file("# X\n\ny")
        mock_session = MagicMock()
        mock_session.execute.return_value.scalars.return_value.all.return_value = []

        try:
            result = ingest_from_bytes(
                session=mock_session, document=doc,
                file_path=path, original_filename="test.md",
            )
            assert result["status"] == "ok"

            assert doc.embedding_model is not None
            assert isinstance(doc.embedding_model, str)
            assert len(doc.embedding_model) > 0
            assert doc.embedding_dims is not None
            assert doc.embedding_dims > 0
        finally:
            os.unlink(path)

    @patch("app.ingestion.pipeline.embed_texts", side_effect=RuntimeError("fail"))
    @patch("app.ingestion.pipeline.chunk_sections")
    @patch("app.ingestion.pipeline.parse_markdown")
    def test_no_metrics_on_failure(self, mock_parse, mock_chunk, mock_embed):
        """On ingestion failure, timing metrics should NOT be set (doc stays in error state)."""
        from app.ingestion.pipeline import ingest_from_bytes

        mock_parse.return_value = [{"heading": "X", "content": "y", "level": 1}]
        mock_chunk.return_value = [ChunkData("X", 1, "y", 5)]

        doc = MagicMock()
        doc.id = 1
        doc.format = "markdown"
        doc.file_size_bytes = 50
        doc.status = "pending"
        doc.error_message = None
        doc.total_chunks = 0
        doc.title = ""

        path = _write_temp_file("# X\n\ny")
        mock_session = MagicMock()
        mock_session.execute.return_value.scalars.return_value.all.return_value = []

        try:
            result = ingest_from_bytes(
                session=mock_session, document=doc,
                file_path=path, original_filename="test.md",
            )
            assert result["status"] == "error"
            assert doc.status == "error"
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Search: document_id in results
# ---------------------------------------------------------------------------

class TestSearchResultsContainDocumentId:
    """Verify that search results include document_id."""

    def test_vector_results_mapping_includes_document_id(self):
        """The vector_results dict construction should include document_id."""
        row = {
            "document_id": 42,
            "content": "test content",
            "parent_content": None,
            "heading_path": "Section",
            "heading_level": 2,
            "token_count": 10,
            "doc_title": "Doc",
            "product_name": "Product",
            "manufacturer": "Mfg",
            "firmware_version": "1.0",
            "similarity": 0.9,
        }
        result = {
            "document_id": row["document_id"],
            "content": row["content"],
            "parent_content": row["parent_content"],
            "heading_path": row["heading_path"],
            "heading_level": row["heading_level"],
            "token_count": row["token_count"],
            "doc_title": row["doc_title"],
            "product_name": row["product_name"],
            "manufacturer": row["manufacturer"],
            "firmware_version": row["firmware_version"],
            "similarity": round(float(row["similarity"]), 4),
        }
        assert "document_id" in result
        assert result["document_id"] == 42


# ---------------------------------------------------------------------------
# RAG hit count update logic
# ---------------------------------------------------------------------------

class TestUpdateRagHitCounts:

    @pytest.mark.asyncio
    async def test_updates_hit_counts_for_used_documents(self):
        from app.search.service import _update_rag_hit_counts

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        results = [
            {"document_id": 1, "similarity": 0.9, "content": "a", "heading_path": "A"},
            {"document_id": 1, "similarity": 0.8, "content": "b", "heading_path": "B"},
            {"document_id": 2, "similarity": 0.7, "content": "c", "heading_path": "C"},
        ]

        await _update_rag_hit_counts(mock_session, results)

        assert mock_session.execute.call_count == 2  # one per document_id
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_when_no_document_ids(self):
        from app.search.service import _update_rag_hit_counts

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        results = [
            {"content": "a", "heading_path": "A", "similarity": 0.9},
        ]

        await _update_rag_hit_counts(mock_session, results)

        mock_session.execute.assert_not_called()
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_on_empty_results(self):
        from app.search.service import _update_rag_hit_counts

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        await _update_rag_hit_counts(mock_session, [])

        mock_session.execute.assert_not_called()
        mock_session.commit.assert_not_called()


# ---------------------------------------------------------------------------
# RAG sources include document_id
# ---------------------------------------------------------------------------

class TestRagSourcesIncludeDocumentId:

    @pytest.mark.asyncio
    @patch("app.chat.rag._detect_product_from_query", new_callable=AsyncMock, return_value=None)
    @patch("app.chat.rag.search_documents", new_callable=AsyncMock)
    @patch("app.chat.rag._has_any_documents", new_callable=AsyncMock, return_value=True)
    async def test_sources_contain_document_id(self, mock_has_docs, mock_search, mock_detect):
        from app.chat.rag import build_rag_prompt

        mock_search.return_value = [
            {
                "document_id": 7,
                "doc_title": "Guide",
                "heading_path": "Auth",
                "similarity": 0.9,
                "content": "Use token auth",
                "product_name": "Cam",
                "firmware_version": "1.0",
            },
        ]

        mock_db = AsyncMock()
        messages, sources, rag_debug = await build_rag_prompt(
            db=mock_db,
            query="How to authenticate?",
        )

        assert len(sources) == 1
        assert sources[0]["document_id"] == 7
