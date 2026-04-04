"""Integration tests for the reindex API (real DB, mocked Celery + embedder)."""

import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text

from app.models import Chunk, Document, Product, ReindexJob


def _wrap_session_as_factory(db_session):
    """Wrap a real AsyncSession so it behaves like async_session() context manager."""
    @asynccontextmanager
    async def _fake_session():
        yield db_session
    return _fake_session


@pytest.fixture
async def reindex_client(db_engine, db_session):
    """AsyncClient wired to a FastAPI app with the reindex router and real DB."""
    from fastapi import FastAPI
    from app.reindex.router import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _seed_product_and_docs(db_session, product_name="TestProduct", count=3, fmt="proto"):
    """Insert a product with N ready documents into the test DB."""
    product = Product(name=product_name, manufacturer="Test", version="1.0", slug=f"test-{product_name.lower()}-1-0")
    db_session.add(product)
    await db_session.flush()

    doc_ids = []
    for i in range(count):
        doc = Document(
            product_id=product.id,
            format=fmt,
            original_filename=f"file_{i}.{fmt}",
            title=f"file_{i}",
            status="ready",
            s3_key=f"documents/{i}/source.{fmt}",
        )
        db_session.add(doc)
        await db_session.flush()
        doc_ids.append(doc.id)

    await db_session.commit()
    return product, doc_ids


@pytest.mark.usefixtures("_init_schema")
class TestReindexAPIIntegration:

    async def test_create_job_and_get_status(self, db_session, reindex_client):
        _, doc_ids = await _seed_product_and_docs(db_session, count=2)

        mock_task = MagicMock()
        mock_task.id = "celery-task-123"

        with (
            patch("app.reindex.router.async_session", _wrap_session_as_factory(db_session)),
            patch("app.celery_app.run_reindex_job_task") as mock_celery,
        ):
            mock_celery.delay.return_value = mock_task
            resp = await reindex_client.post(
                "/api/v1/reindex/jobs",
                json={"mode": "reingest", "product_name": "TestProduct"},
            )

        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "pending"
        assert data["total_documents"] == 2
        assert data["mode"] == "reingest"
        assert data["product_filter"] == "TestProduct"

    async def test_create_job_no_matching_docs_returns_400(self, db_session, reindex_client):
        with patch("app.reindex.router.async_session", _wrap_session_as_factory(db_session)):
            resp = await reindex_client.post(
                "/api/v1/reindex/jobs",
                json={"mode": "reingest", "product_name": "NonExistent"},
            )

        assert resp.status_code == 400

    async def test_list_jobs(self, db_session, reindex_client):
        with patch("app.reindex.router.async_session", _wrap_session_as_factory(db_session)):
            resp = await reindex_client.get("/api/v1/reindex/jobs")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 0
        assert isinstance(data["jobs"], list)

    async def test_get_nonexistent_job_returns_404(self, db_session, reindex_client):
        with patch("app.reindex.router.async_session", _wrap_session_as_factory(db_session)):
            resp = await reindex_client.get("/api/v1/reindex/jobs/99999")

        assert resp.status_code == 404

    async def test_cancel_nonexistent_job_returns_404(self, db_session, reindex_client):
        with patch("app.reindex.router.async_session", _wrap_session_as_factory(db_session)):
            resp = await reindex_client.post("/api/v1/reindex/jobs/99999/cancel")

        assert resp.status_code == 404


@pytest.mark.usefixtures("_init_schema")
class TestReindexServiceIntegration:
    """Test the service layer directly with a real DB session."""

    async def test_start_and_cancel_job(self, db_session):
        _, doc_ids = await _seed_product_and_docs(db_session, product_name="CancelTest", count=2)

        mock_task = MagicMock()
        mock_task.id = "task-cancel-test"

        from app.reindex.service import cancel_job, start_reindex_job

        with patch("app.celery_app.run_reindex_job_task") as mock_celery:
            mock_celery.delay.return_value = mock_task
            result = await start_reindex_job(db_session, "reingest", product_name="CancelTest")

        assert result["status"] == "pending"
        job_id = result["id"]

        cancelled = await cancel_job(db_session, job_id)
        assert cancelled["status"] == "cancelled"
        assert cancelled["finished_at"] is not None

    async def test_duplicate_job_rejected(self, db_session):
        _, doc_ids = await _seed_product_and_docs(db_session, product_name="DupTest", count=1)

        mock_task = MagicMock()
        mock_task.id = "task-dup-test"

        from app.reindex.service import start_reindex_job

        with patch("app.celery_app.run_reindex_job_task") as mock_celery:
            mock_celery.delay.return_value = mock_task
            await start_reindex_job(db_session, "reingest", product_name="DupTest")

            with pytest.raises(ValueError, match="already covers"):
                await start_reindex_job(db_session, "reingest", product_name="DupTest")

    async def test_stale_job_auto_detected(self, db_session):
        _, doc_ids = await _seed_product_and_docs(db_session, product_name="StaleTest", count=1)

        job = ReindexJob(
            mode="reingest",
            status="running",
            product_filter="StaleTest",
            total_documents=1,
            heartbeat_at=datetime.now(timezone.utc) - timedelta(seconds=600),
        )
        db_session.add(job)
        await db_session.flush()

        from app.reindex.service import get_job_status
        result = await get_job_status(db_session, job.id)
        assert result["status"] == "stale"
        assert result["finished_at"] is not None

    async def test_job_errors_stored(self, db_session):
        job = ReindexJob(
            mode="reingest",
            status="completed",
            total_documents=2,
            processed_documents=1,
            failed_documents=1,
            errors_json=json.dumps([
                {"document_id": 10, "document_title": "bad.proto", "error": "parse failed", "timestamp": "2026-01-01"},
            ]),
        )
        db_session.add(job)
        await db_session.flush()

        from app.reindex.service import get_job_errors
        errors = await get_job_errors(db_session, job.id)
        assert len(errors) == 1
        assert errors[0]["document_id"] == 10

    async def test_invalid_mode_rejected(self, db_session):
        from app.reindex.service import start_reindex_job
        with pytest.raises(ValueError, match="Invalid mode"):
            await start_reindex_job(db_session, "bad_mode")
