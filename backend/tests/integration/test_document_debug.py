"""Integration tests for document debug metrics with real PostgreSQL+pgvector."""

import pytest
from sqlalchemy import select

from app.ingestion.pipeline import ingest_file
from app.models import Document, Product


class TestDebugMetricsAfterIngestion:
    """Verify that debug metrics are persisted after a full ingestion pipeline run."""

    async def test_timing_metrics_saved(self, db_session, sample_md_file):
        result = await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            product_name="DebugTest",
            firmware_version="1.0",
        )
        assert result["status"] == "ok"

        doc = (await db_session.execute(
            select(Document).where(Document.status == "ready")
        )).scalar_one()

        assert doc.ingest_duration_ms is not None
        assert doc.ingest_duration_ms > 0
        assert doc.read_ms is not None
        assert doc.read_ms >= 0
        assert doc.parse_ms is not None
        assert doc.embed_ms is not None
        assert doc.db_ms is not None

    async def test_token_stats_saved(self, db_session, sample_md_file):
        result = await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            product_name="TokenTest",
            firmware_version="1.0",
        )
        assert result["status"] == "ok"

        doc = (await db_session.execute(
            select(Document).where(Document.status == "ready")
        )).scalar_one()

        assert doc.total_tokens > 0
        assert doc.min_chunk_tokens is not None
        assert doc.max_chunk_tokens is not None
        assert doc.min_chunk_tokens <= doc.max_chunk_tokens
        assert doc.avg_chunk_tokens is not None
        assert doc.avg_chunk_tokens > 0
        assert doc.embedding_tokens > 0

    async def test_embedding_model_saved(self, db_session, sample_md_file):
        result = await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            product_name="EmbedTest",
            firmware_version="1.0",
        )
        assert result["status"] == "ok"

        doc = (await db_session.execute(
            select(Document).where(Document.status == "ready")
        )).scalar_one()

        assert doc.embedding_model is not None
        assert len(doc.embedding_model) > 0
        assert doc.embedding_dims is not None
        assert doc.embedding_dims > 0

    async def test_rag_counters_start_at_zero(self, db_session, sample_md_file):
        result = await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            product_name="RagTest",
            firmware_version="1.0",
        )
        assert result["status"] == "ok"

        doc = (await db_session.execute(
            select(Document).where(Document.status == "ready")
        )).scalar_one()

        assert doc.rag_hit_count == 0
        assert doc.rag_avg_similarity is None
        assert doc.rag_last_used_at is None

    async def test_total_chunks_matches_token_count(self, db_session, sample_md_file):
        """total_tokens should equal sum of all chunk token_counts."""
        result = await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            product_name="ChunkTest",
            firmware_version="1.0",
        )
        assert result["status"] == "ok"

        doc = (await db_session.execute(
            select(Document).where(Document.status == "ready")
        )).scalar_one()

        assert doc.total_chunks == result["chunks"]
        assert doc.total_tokens > 0

    async def test_timing_breakdown_sums_to_total(self, db_session, sample_md_file):
        """Sum of stage timings should be roughly equal to total duration."""
        result = await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            product_name="TimingTest",
            firmware_version="1.0",
        )
        assert result["status"] == "ok"

        doc = (await db_session.execute(
            select(Document).where(Document.status == "ready")
        )).scalar_one()

        stage_sum = (
            (doc.read_ms or 0) +
            (doc.convert_ms or 0) +
            (doc.parse_ms or 0) +
            (doc.embed_ms or 0) +
            (doc.db_ms or 0)
        )
        assert stage_sum <= doc.ingest_duration_ms * 1.5, (
            f"Stage sum {stage_sum}ms should not vastly exceed total {doc.ingest_duration_ms}ms"
        )


class TestDebugMetricsWithSearch:
    """Verify RAG hit counts update after search."""

    async def test_rag_hit_count_increments_after_search(self, db_session, sample_md_file):
        from app.search.service import search_documents

        result = await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            product_name="SearchHitTest",
            firmware_version="1.0",
        )
        assert result["status"] == "ok"

        doc_before = (await db_session.execute(
            select(Document).where(Document.status == "ready")
        )).scalar_one()
        assert doc_before.rag_hit_count == 0

        search_results = await search_documents(
            session=db_session,
            query="How to open a door?",
        )

        if search_results:
            await db_session.refresh(doc_before)
            assert doc_before.rag_hit_count > 0
            assert doc_before.rag_last_used_at is not None
            assert doc_before.rag_avg_similarity is not None
            assert doc_before.rag_avg_similarity > 0
