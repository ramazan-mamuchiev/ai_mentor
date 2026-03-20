"""Unit tests for the reindex service layer."""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import ReindexJob
from app.reindex.service import (
    ACTIVE_STATUSES,
    TERMINAL_STATUSES,
    _is_stale,
    _job_to_dict,
)


def _make_job(**kw):
    """Create a ReindexJob-like SimpleNamespace with sensible defaults."""
    defaults = dict(
        id=1,
        mode="reingest",
        status="pending",
        product_filter=None,
        format_filter=None,
        total_documents=10,
        processed_documents=0,
        failed_documents=0,
        skipped_documents=0,
        total_chunks=0,
        celery_task_id=None,
        error_message=None,
        errors_json="[]",
        created_at=datetime.now(timezone.utc),
        started_at=None,
        finished_at=None,
        heartbeat_at=None,
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


class TestIsStale:
    def test_pending_job_not_stale(self):
        job = _make_job(status="pending")
        assert _is_stale(job) is False

    def test_running_without_heartbeat_not_stale(self):
        job = _make_job(status="running", heartbeat_at=None)
        assert _is_stale(job) is False

    def test_running_with_recent_heartbeat_not_stale(self):
        job = _make_job(
            status="running",
            heartbeat_at=datetime.now(timezone.utc) - timedelta(seconds=5),
        )
        assert _is_stale(job) is False

    def test_running_with_old_heartbeat_is_stale(self):
        job = _make_job(
            status="running",
            heartbeat_at=datetime.now(timezone.utc) - timedelta(seconds=600),
        )
        assert _is_stale(job) is True

    def test_completed_job_not_stale(self):
        job = _make_job(
            status="completed",
            heartbeat_at=datetime.now(timezone.utc) - timedelta(seconds=600),
        )
        assert _is_stale(job) is False


class TestJobToDict:
    def test_basic_fields(self):
        job = _make_job(id=42, mode="reembed", status="running")
        d = _job_to_dict(job)
        assert d["id"] == 42
        assert d["mode"] == "reembed"
        assert d["status"] == "running"

    def test_progress_zero_when_nothing_processed(self):
        job = _make_job(total_documents=10, processed_documents=0)
        d = _job_to_dict(job)
        assert d["progress_percent"] == 0.0

    def test_progress_50_percent(self):
        job = _make_job(total_documents=10, processed_documents=5)
        d = _job_to_dict(job)
        assert d["progress_percent"] == 50.0

    def test_progress_includes_failed_and_skipped(self):
        job = _make_job(
            total_documents=10,
            processed_documents=3,
            failed_documents=2,
            skipped_documents=1,
        )
        d = _job_to_dict(job)
        assert d["progress_percent"] == 60.0

    def test_progress_100_when_all_done(self):
        job = _make_job(total_documents=5, processed_documents=5)
        d = _job_to_dict(job)
        assert d["progress_percent"] == 100.0

    def test_duration_none_when_not_started(self):
        job = _make_job(started_at=None)
        d = _job_to_dict(job)
        assert d["duration_sec"] is None

    def test_duration_calculated_when_finished(self):
        now = datetime.now(timezone.utc)
        job = _make_job(started_at=now - timedelta(seconds=30), finished_at=now)
        d = _job_to_dict(job)
        assert 29.5 <= d["duration_sec"] <= 30.5

    def test_is_stale_flag(self):
        job = _make_job(
            status="running",
            heartbeat_at=datetime.now(timezone.utc) - timedelta(seconds=600),
        )
        d = _job_to_dict(job)
        assert d["is_stale"] is True


class TestConstants:
    def test_active_statuses(self):
        assert "pending" in ACTIVE_STATUSES
        assert "running" in ACTIVE_STATUSES

    def test_terminal_statuses(self):
        assert "completed" in TERMINAL_STATUSES
        assert "failed" in TERMINAL_STATUSES
        assert "cancelled" in TERMINAL_STATUSES
        assert "stale" in TERMINAL_STATUSES


class TestRunReindexSync:
    """Tests for the synchronous Celery worker function."""

    @patch("app.reindex.service._reingest_document", return_value=5)
    @patch("app.celery_app._get_sync_engine")
    def test_processes_all_documents(self, mock_engine, mock_reingest):
        from app.reindex.service import run_reindex_sync

        job = _make_job(id=1, mode="reingest", status="pending", total_documents=3)

        mock_session = MagicMock()
        mock_session.get.return_value = job
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        with patch("app.reindex.service.SyncSession", return_value=mock_session):
            run_reindex_sync(1, [10, 20, 30])

        assert mock_reingest.call_count == 3
        assert job.processed_documents == 3
        assert job.total_chunks == 15
        assert job.status == "completed"
        assert job.finished_at is not None

    @patch("app.reindex.service._reembed_document", return_value=8)
    @patch("app.celery_app._get_sync_engine")
    def test_reembed_mode(self, mock_engine, mock_reembed):
        from app.reindex.service import run_reindex_sync

        job = _make_job(id=2, mode="reembed", status="pending", total_documents=2)

        mock_session = MagicMock()
        mock_session.get.return_value = job
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        with patch("app.reindex.service.SyncSession", return_value=mock_session):
            run_reindex_sync(2, [10, 20])

        assert mock_reembed.call_count == 2
        assert job.processed_documents == 2

    @patch("app.reindex.service._reingest_document", side_effect=RuntimeError("boom"))
    @patch("app.celery_app._get_sync_engine")
    def test_handles_document_errors(self, mock_engine, mock_reingest):
        from app.reindex.service import run_reindex_sync
        from app.models import Document

        job = _make_job(id=3, mode="reingest", status="pending", total_documents=2)

        mock_doc = MagicMock()
        mock_doc.title = "test.proto"

        mock_session = MagicMock()
        mock_session.get.side_effect = lambda cls, id: job if cls is ReindexJob else mock_doc
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        with patch("app.reindex.service.SyncSession", return_value=mock_session):
            run_reindex_sync(3, [10, 20])

        assert job.failed_documents == 2
        assert job.processed_documents == 0
        assert job.status == "failed"
        errors = json.loads(job.errors_json)
        assert len(errors) == 2
        assert "boom" in errors[0]["error"]

    @patch("app.reindex.service._reingest_document", return_value=5)
    @patch("app.celery_app._get_sync_engine")
    def test_respects_cancellation(self, mock_engine, mock_reingest):
        from app.reindex.service import run_reindex_sync

        call_count = [0]

        def _get_job(cls, id):
            if call_count[0] == 0:
                call_count[0] += 1
                return _make_job(id=4, mode="reingest", status="pending", total_documents=3)
            else:
                return _make_job(id=4, mode="reingest", status="cancelled", total_documents=3)

        mock_session = MagicMock()
        mock_session.get.side_effect = _get_job
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        with patch("app.reindex.service.SyncSession", return_value=mock_session):
            run_reindex_sync(4, [10, 20, 30])

        assert mock_reingest.call_count <= 1
