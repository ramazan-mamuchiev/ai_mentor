"""Unit tests for Celery ingest_document_task business logic."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch, call

import pytest


def _make_doc(doc_id=1, **kw):
    """Create a simple document-like object with real attribute assignment."""
    return SimpleNamespace(
        id=doc_id,
        status=kw.get("status", "pending"),
        s3_key=kw.get("s3_key", "documents/1/source.md"),
        original_filename=kw.get("original_filename", "test.md"),
        file_size_bytes=kw.get("file_size_bytes", 100),
        format=kw.get("format", "auto"),
        error_message=kw.get("error_message", None),
    )


def _make_session(doc):
    """Create a mock Session that returns `doc` from .get() and supports context manager."""
    session = MagicMock()
    session.get.return_value = doc
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    return session


@pytest.fixture()
def celery_task():
    from app.celery_app import ingest_document_task
    ingest_document_task.request.id = "test-task-id"
    return ingest_document_task


def _run(celery_task, doc, session, extra_patches=None):
    """Run the task with all necessary patches applied."""
    patches = {
        "app.celery_app._get_sync_engine": MagicMock(),
    }
    if extra_patches:
        patches.update(extra_patches)

    stack = {}
    import contextlib
    with contextlib.ExitStack() as exit_stack:
        for target, mock_val in patches.items():
            if isinstance(mock_val, dict):
                exit_stack.enter_context(patch(target, **mock_val))
            else:
                exit_stack.enter_context(patch(target, mock_val))

        with patch("app.celery_app.Session", return_value=session):
            return celery_task.run(document_id=doc.id)


class TestDocNotFound:

    def test_returns_error_when_doc_not_found(self, celery_task):
        session = _make_session(doc=None)
        result = _run(celery_task, SimpleNamespace(id=999), session)
        assert result["status"] == "error"
        assert "not found" in result["error"].lower()


class TestAlreadyReady:

    def test_skips_ready_document(self, celery_task):
        doc = _make_doc(status="ready")
        session = _make_session(doc)
        result = _run(celery_task, doc, session)
        assert result["status"] == "skipped"


class TestS3Failure:

    def test_retries_on_s3_failure(self, celery_task):
        doc = _make_doc(status="pending")
        session = _make_session(doc)

        retry_exc = Exception("retry-sentinel")

        with patch("app.celery_app._get_sync_engine"), \
             patch("app.celery_app.Session", return_value=session), \
             patch("app.s3.download_file", side_effect=Exception("S3 connection refused")), \
             patch.object(celery_task, "retry", side_effect=retry_exc):

            with pytest.raises(Exception, match="retry-sentinel"):
                celery_task.run(document_id=doc.id)

        assert doc.status == "error"
        assert "S3 download failed" in doc.error_message


class TestSuccessfulIngestion:

    def test_processes_document(self, celery_task):
        doc = _make_doc(doc_id=5, status="pending", original_filename="test.md")
        session = _make_session(doc)

        with patch("app.celery_app._get_sync_engine"), \
             patch("app.celery_app.Session", return_value=session), \
             patch("app.s3.download_file", return_value=b"# Test\n\nContent."), \
             patch("app.ingestion.pipeline.ingest_from_bytes", return_value={"status": "ok", "chunks": 3, "document_id": 5}):

            result = celery_task.run(document_id=5)

        assert result["status"] == "ok"
        assert result["chunks"] == 3
        assert doc.status == "processing"


class TestPipelineFailure:

    def test_retries_on_pipeline_error(self, celery_task):
        doc = _make_doc(doc_id=2, status="pending", original_filename="bad.md")
        session = _make_session(doc)

        retry_exc = Exception("retry-sentinel")

        with patch("app.celery_app._get_sync_engine"), \
             patch("app.celery_app.Session", return_value=session), \
             patch("app.s3.download_file", return_value=b"bad"), \
             patch("app.ingestion.pipeline.ingest_from_bytes", side_effect=ValueError("Parse error")), \
             patch.object(celery_task, "retry", side_effect=retry_exc):

            with pytest.raises(Exception, match="retry-sentinel"):
                celery_task.run(document_id=2)

        assert doc.status == "error"
        assert "Parse error" in doc.error_message


class TestTempFileCleanup:

    def test_temp_file_cleaned_up_on_error(self, celery_task):
        doc = _make_doc(doc_id=3, status="pending", original_filename="test.md")
        session = _make_session(doc)

        retry_exc = Exception("retry-sentinel")

        with patch("app.celery_app._get_sync_engine"), \
             patch("app.celery_app.Session", return_value=session), \
             patch("app.s3.download_file", return_value=b"content"), \
             patch("app.ingestion.pipeline.ingest_from_bytes", side_effect=RuntimeError("boom")), \
             patch.object(celery_task, "retry", side_effect=retry_exc), \
             patch("os.unlink") as mock_unlink, \
             patch("os.path.exists", return_value=True):

            with pytest.raises(Exception, match="retry-sentinel"):
                celery_task.run(document_id=3)

            mock_unlink.assert_called_once()


class TestStatusTransition:

    def test_sets_processing_before_download(self, celery_task):
        doc = _make_doc(doc_id=10, status="pending", original_filename="doc.md")
        statuses_at_commit = []

        session = _make_session(doc)
        original_commit = session.commit

        def track_commit():
            statuses_at_commit.append(doc.status)

        session.commit = track_commit

        with patch("app.celery_app._get_sync_engine"), \
             patch("app.celery_app.Session", return_value=session), \
             patch("app.s3.download_file", return_value=b"content"), \
             patch("app.ingestion.pipeline.ingest_from_bytes", return_value={"status": "ok", "chunks": 1}):

            celery_task.run(document_id=10)

        assert "processing" in statuses_at_commit
