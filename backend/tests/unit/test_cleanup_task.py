"""Unit tests for the Celery cleanup_expired_uploads task."""

from unittest.mock import MagicMock, patch

import pytest

# Heavy deps (celery, boto3, structlog) are mocked in tests/conftest.py
import app.celery_app as celery_module


class _FakeUploadSession:
    """Lightweight stand-in for UploadSession ORM model."""

    def __init__(self, id, status="uploading", s3_upload_id="mpu-1", s3_key="k"):
        self.id = id
        self.status = status
        self.s3_upload_id = s3_upload_id
        self.s3_key = s3_key


class TestCleanupExpiredUploads:
    def _run_cleanup(self, rows, mock_abort):
        """Execute cleanup_expired_uploads_task with given rows."""
        mock_db_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = rows
        mock_db_session.execute.return_value = mock_result

        mock_session_cls = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_db_session)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

        with (
            patch.object(celery_module, "_get_sync_engine"),
            patch.object(celery_module, "Session", mock_session_cls),
            patch("app.s3.abort_multipart_upload", mock_abort),
        ):
            mock_self = MagicMock()
            return celery_module.cleanup_expired_uploads_task(mock_self)

    def test_cleans_expired_sessions(self):
        expired1 = _FakeUploadSession("exp-1")
        expired2 = _FakeUploadSession("exp-2")
        mock_abort = MagicMock()

        self._run_cleanup([expired1, expired2], mock_abort)

        assert expired1.status == "expired"
        assert expired2.status == "expired"
        assert mock_abort.call_count == 2

    def test_no_expired_sessions(self):
        mock_abort = MagicMock()
        self._run_cleanup([], mock_abort)
        mock_abort.assert_not_called()

    def test_continues_on_s3_error(self):
        expired = _FakeUploadSession("exp-err")
        mock_abort = MagicMock(side_effect=Exception("S3 down"))

        self._run_cleanup([expired], mock_abort)

        assert expired.status == "expired"

    def test_skips_abort_when_no_s3_upload_id(self):
        expired = _FakeUploadSession("exp-no-s3", s3_upload_id="")
        mock_abort = MagicMock()

        self._run_cleanup([expired], mock_abort)

        mock_abort.assert_not_called()
        assert expired.status == "expired"

    def test_mixed_sessions(self):
        with_s3 = _FakeUploadSession("mix-1", s3_upload_id="mpu-a", s3_key="k1")
        without_s3 = _FakeUploadSession("mix-2", s3_upload_id="")
        mock_abort = MagicMock()

        self._run_cleanup([with_s3, without_s3], mock_abort)

        assert with_s3.status == "expired"
        assert without_s3.status == "expired"
        mock_abort.assert_called_once_with("k1", "mpu-a")

    def test_returns_cleaned_count(self):
        rows = [_FakeUploadSession(f"cnt-{i}") for i in range(3)]
        mock_abort = MagicMock()

        result = self._run_cleanup(rows, mock_abort)

        assert result == {"cleaned": 3}

    def test_returns_zero_when_nothing_to_clean(self):
        mock_abort = MagicMock()
        result = self._run_cleanup([], mock_abort)
        assert result == {"cleaned": 0}
