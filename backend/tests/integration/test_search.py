"""Integration tests for search service with real PostgreSQL+pgvector."""

import pytest

from app.ingestion.pipeline import ingest_file
from app.search.service import search_documents, search_endpoint
from tests.conftest import fake_embed_query


class TestSearchDocuments:
    async def test_empty_db_returns_empty(self, db_session):
        results = await search_documents(db_session, "anything")
        assert results == []

    async def test_finds_ingested_content(self, db_session, sample_md_file):
        await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            product_name="ZKTeco InBio",
            firmware_version="1.0",
            manufacturer="ZKTeco",
        )

        results = await search_documents(db_session, "open door command")
        assert len(results) > 0
        assert all("similarity" in r for r in results)
        assert all(r["product_name"] == "ZKTeco InBio" for r in results)

    async def test_filter_by_device(self, db_session, sample_md_file):
        await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            product_name="DeviceA",
            firmware_version="1.0",
        )

        from app.search.service import resolve_product
        resolve_match = await resolve_product(db_session, "DeviceA")
        results_match = await search_documents(db_session, "door", product_id=resolve_match.product_id)
        resolve_no = await resolve_product(db_session, "NonExistent")
        results_no_match = await search_documents(db_session, "door", product_id=resolve_no.product_id)

        assert len(results_match) > 0
        assert len(results_no_match) == 0

    async def test_filter_by_version(self, db_session, sample_md_file):
        await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            product_name="TestDevice",
            firmware_version="1.0",
        )

        results_match = await search_documents(db_session, "door", version="1.0")
        results_no_match = await search_documents(db_session, "door", version="99.0")

        assert len(results_match) > 0
        assert len(results_no_match) == 0

    async def test_result_fields(self, db_session, sample_md_file):
        await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            product_name="TestDevice",
            firmware_version="1.0",
            manufacturer="TestMfg",
        )

        results = await search_documents(db_session, "test query", limit=1)
        assert len(results) == 1
        r = results[0]
        assert "content" in r
        assert "heading_path" in r
        assert "heading_level" in r
        assert "token_count" in r
        assert "doc_title" in r
        assert "product_name" in r
        assert "manufacturer" in r
        assert "firmware_version" in r
        assert "similarity" in r
        assert isinstance(r["similarity"], float)

    async def test_limit_respected(self, db_session, sample_md_file):
        await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            product_name="TestDevice",
            firmware_version="1.0",
        )

        results = await search_documents(db_session, "test", limit=2)
        assert len(results) <= 2


class TestSearchEndpoint:
    async def test_exact_match_by_heading(self, db_session, sample_md_file):
        await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            product_name="TestDevice",
            firmware_version="1.0",
        )

        results = await search_endpoint(db_session, "Open Door")
        assert len(results) > 0
        assert results[0]["match_type"] == "exact"

    async def test_fallback_to_vector_search(self, db_session, sample_md_file):
        await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            product_name="TestDevice",
            firmware_version="1.0",
        )

        results = await search_endpoint(db_session, "/nonexistent/endpoint/xyz")
        assert len(results) > 0
        assert all(r.get("match_type") != "exact" for r in results)

    async def test_filter_by_device(self, db_session, sample_md_file):
        await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            product_name="DeviceX",
            firmware_version="1.0",
        )

        from app.search.service import resolve_product
        resolve_x = await resolve_product(db_session, "DeviceX")
        results = await search_endpoint(db_session, "Door", product_id=resolve_x.product_id)
        assert len(results) > 0

        resolve_other = await resolve_product(db_session, "OtherDevice")
        results_no = await search_endpoint(db_session, "Door", product_id=resolve_other.product_id)
        assert len(results_no) == 0
