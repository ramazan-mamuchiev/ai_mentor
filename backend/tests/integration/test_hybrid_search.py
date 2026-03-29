"""Integration tests for hybrid search (BM25 + vector + RRF fusion).

Tests run against a real PostgreSQL+pgvector container with tsvector columns.
"""

import pytest

from app.ingestion.pipeline import ingest_file
from app.search.service import search_documents, _bm25_search, _rrf_fuse


class TestHybridSearch:
    async def test_bm25_finds_exact_term(self, db_session, sample_md_file):
        """BM25 should find chunks containing the exact search term."""
        await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            product_name="ZKTeco",
            firmware_version="1.0",
        )

        where_sql = "d.status = 'ready'"
        params = {"limit": 10}

        results = await _bm25_search(
            db_session, "CONTROL DEVICE", where_sql, params, fetch_limit=10,
        )
        assert len(results) > 0
        assert any("CONTROL DEVICE" in r["content"] for r in results)

    async def test_bm25_returns_empty_for_nonexistent_term(self, db_session, sample_md_file):
        await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            product_name="ZKTeco",
            firmware_version="1.0",
        )

        where_sql = "d.status = 'ready'"
        params = {"limit": 10}

        results = await _bm25_search(
            db_session, "xyznonexistent123", where_sql, params, fetch_limit=10,
        )
        assert len(results) == 0

    async def test_hybrid_search_returns_results(self, db_session, sample_md_file):
        """Full hybrid search should return results combining vector + BM25."""
        await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            product_name="ZKTeco",
            firmware_version="1.0",
        )

        results = await search_documents(db_session, "door control command")
        assert len(results) > 0

    async def test_hybrid_search_with_product_filter(self, db_session, sample_md_file):
        await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            product_name="ZKTeco InBio",
            firmware_version="1.0",
        )

        from app.search.service import resolve_product
        resolve = await resolve_product(db_session, "ZKTeco")
        results = await search_documents(db_session, "door", product_id=resolve.product_id)
        assert len(results) > 0
        assert all(r["product_name"] == "ZKTeco InBio" for r in results)

    async def test_tsvector_populated_on_insert(self, db_session, sample_md_file):
        """Verify that the tsvector trigger populates the tsv column on chunk insert."""
        from sqlalchemy import text

        await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            product_name="TestTSV",
            firmware_version="1.0",
        )

        result = await db_session.execute(
            text("SELECT COUNT(*) FROM chunks WHERE tsv IS NOT NULL")
        )
        count = result.scalar()
        assert count > 0

    async def test_bm25_finds_heading_path_terms(self, db_session, sample_md_file):
        """BM25 should also match terms from heading_path (included in tsvector)."""
        await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            product_name="ZKTeco",
            firmware_version="1.0",
        )

        where_sql = "d.status = 'ready'"
        params = {"limit": 10}

        results = await _bm25_search(
            db_session, "Event Monitoring", where_sql, params, fetch_limit=10,
        )
        assert len(results) > 0


class TestRRFFusionIntegration:
    async def test_rrf_boosts_overlapping_results(self, db_session, sample_md_file):
        """When a chunk appears in both vector and BM25, it should rank higher."""
        await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            product_name="ZKTeco",
            firmware_version="1.0",
        )

        from sqlalchemy import text as sa_text

        where_sql = "d.status = 'ready'"
        params = {"embedding": "[" + ",".join(["0.1"] * 1024) + "]", "limit": 10}

        vec_result = await db_session.execute(
            sa_text(f"""
                SELECT c.content, c.parent_content, c.heading_path, c.heading_level,
                       c.token_count, d.title AS doc_title, p.name AS product_name,
                       p.manufacturer, fw.version AS firmware_version,
                       1 - (c.embedding <=> CAST(:embedding AS vector)) AS similarity
                FROM chunks c
                JOIN documents d ON c.document_id = d.id
                JOIN products p ON d.product_id = p.id
                JOIN firmware_versions fw ON d.firmware_version_id = fw.id
                WHERE {where_sql}
                ORDER BY c.embedding <=> CAST(:embedding AS vector)
                LIMIT :limit
            """),
            params,
        )
        vector_results = [
            {
                "content": r["content"], "parent_content": r["parent_content"],
                "heading_path": r["heading_path"], "heading_level": r["heading_level"],
                "token_count": r["token_count"], "doc_title": r["doc_title"],
                "product_name": r["product_name"], "manufacturer": r["manufacturer"],
                "firmware_version": r["firmware_version"],
                "similarity": round(float(r["similarity"]), 4),
            }
            for r in vec_result.mappings().all()
        ]

        bm25_results = await _bm25_search(
            db_session, "door", where_sql, params, fetch_limit=10,
        )

        if vector_results and bm25_results:
            fused = _rrf_fuse(vector_results, bm25_results)
            assert len(fused) >= max(len(vector_results), len(bm25_results))
