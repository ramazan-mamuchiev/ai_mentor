"""Unit tests for the reindex API router."""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.reindex.schemas import ReindexJobResponse


def _sample_job_dict(**overrides) -> dict:
    base = {
        "id": 1,
        "mode": "reingest",
        "status": "pending",
        "product_filter": None,
        "format_filter": None,
        "total_documents": 10,
        "processed_documents": 0,
        "failed_documents": 0,
        "skipped_documents": 0,
        "total_chunks": 0,
        "progress_percent": 0.0,
        "celery_task_id": "abc-123",
        "error_message": None,
        "created_at": datetime.now(timezone.utc),
        "started_at": None,
        "finished_at": None,
        "heartbeat_at": None,
        "duration_sec": None,
        "is_stale": False,
    }
    base.update(overrides)
    return base


@pytest.fixture
def app():
    from fastapi import FastAPI
    from app.reindex.router import router
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")
    return test_app


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


class TestCreateJob:
    @pytest.mark.asyncio
    async def test_success(self, client):
        job = _sample_job_dict(status="pending")
        with patch("app.reindex.router.start_reindex_job", new_callable=AsyncMock, return_value=job) as mock_start:
            resp = await client.post("/api/v1/reindex/jobs", json={"mode": "reingest"})
        assert resp.status_code == 202
        data = resp.json()
        assert data["id"] == 1
        assert data["status"] == "pending"

    @pytest.mark.asyncio
    async def test_conflict_returns_409(self, client):
        with patch(
            "app.reindex.router.start_reindex_job",
            new_callable=AsyncMock,
            side_effect=ValueError("already covers this scope"),
        ):
            resp = await client.post("/api/v1/reindex/jobs", json={"mode": "reingest"})
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_invalid_mode_returns_400(self, client):
        with patch(
            "app.reindex.router.start_reindex_job",
            new_callable=AsyncMock,
            side_effect=ValueError("Invalid mode"),
        ):
            resp = await client.post("/api/v1/reindex/jobs", json={"mode": "bad"})
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_no_documents_returns_400(self, client):
        with patch(
            "app.reindex.router.start_reindex_job",
            new_callable=AsyncMock,
            side_effect=ValueError("No documents match"),
        ):
            resp = await client.post("/api/v1/reindex/jobs", json={"mode": "reingest", "product_name": "Unknown"})
        assert resp.status_code == 400


class TestGetJob:
    @pytest.mark.asyncio
    async def test_found(self, client):
        job = _sample_job_dict(id=5, status="running", processed_documents=3, progress_percent=30.0)
        with patch("app.reindex.router.get_job_status", new_callable=AsyncMock, return_value=job):
            resp = await client.get("/api/v1/reindex/jobs/5")
        assert resp.status_code == 200
        assert resp.json()["progress_percent"] == 30.0

    @pytest.mark.asyncio
    async def test_not_found(self, client):
        with patch("app.reindex.router.get_job_status", new_callable=AsyncMock, return_value=None):
            resp = await client.get("/api/v1/reindex/jobs/999")
        assert resp.status_code == 404


class TestListJobs:
    @pytest.mark.asyncio
    async def test_returns_list(self, client):
        jobs = [_sample_job_dict(id=1), _sample_job_dict(id=2)]
        with patch("app.reindex.router.list_jobs", new_callable=AsyncMock, return_value=(jobs, 2)):
            resp = await client.get("/api/v1/reindex/jobs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["jobs"]) == 2


class TestCancelJob:
    @pytest.mark.asyncio
    async def test_cancel_success(self, client):
        job = _sample_job_dict(status="cancelled")
        with patch("app.reindex.router.cancel_job", new_callable=AsyncMock, return_value=job):
            resp = await client.post("/api/v1/reindex/jobs/1/cancel")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_not_found(self, client):
        with patch("app.reindex.router.cancel_job", new_callable=AsyncMock, return_value=None):
            resp = await client.post("/api/v1/reindex/jobs/999/cancel")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_cancel_terminal_returns_400(self, client):
        with patch(
            "app.reindex.router.cancel_job",
            new_callable=AsyncMock,
            side_effect=ValueError("already in terminal state"),
        ):
            resp = await client.post("/api/v1/reindex/jobs/1/cancel")
        assert resp.status_code == 400


class TestGetErrors:
    @pytest.mark.asyncio
    async def test_returns_errors(self, client):
        errors = [
            {"document_id": 10, "document_title": "test.proto", "error": "boom", "timestamp": "2026-01-01T00:00:00"},
        ]
        with patch("app.reindex.router.get_job_errors", new_callable=AsyncMock, return_value=errors):
            resp = await client.get("/api/v1/reindex/jobs/1/errors")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["document_id"] == 10

    @pytest.mark.asyncio
    async def test_empty_errors(self, client):
        with patch("app.reindex.router.get_job_errors", new_callable=AsyncMock, return_value=[]):
            resp = await client.get("/api/v1/reindex/jobs/1/errors")
        assert resp.status_code == 200
        assert resp.json() == []
