"""Unit tests for TUS resumable upload router.

All external dependencies (redis, boto3, database) are mocked at module level
so tests run without Docker.
"""

import base64
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Mock heavy imports BEFORE importing the module under test
# ---------------------------------------------------------------------------
_mock_redis_module = MagicMock()
_mock_boto3 = MagicMock()
sys.modules.setdefault("redis", _mock_redis_module)
sys.modules.setdefault("boto3", _mock_boto3)
sys.modules.setdefault("botocore", MagicMock())
sys.modules.setdefault("botocore.exceptions", MagicMock())

from app.uploads.router import (  # noqa: E402
    _load_sha256,
    _parse_metadata,
    _save_sha256,
    router,
)

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _b64(val: str) -> str:
    return base64.b64encode(val.encode()).decode()


def _encode_metadata(**kwargs) -> str:
    parts = []
    for k, v in kwargs.items():
        if v is not None:
            parts.append(f"{k} {_b64(str(v))}")
    return ", ".join(parts)


def _make_app():
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


# ---------------------------------------------------------------------------
# _parse_metadata
# ---------------------------------------------------------------------------

class TestParseMetadata:
    def test_empty_string(self):
        assert _parse_metadata("") == {}

    def test_single_pair(self):
        result = _parse_metadata(f"filename {_b64('test.pdf')}")
        assert result == {"filename": "test.pdf"}

    def test_multiple_pairs(self):
        header = f"filename {_b64('doc.md')}, product_name {_b64('AxxonOne')}"
        result = _parse_metadata(header)
        assert result["filename"] == "doc.md"
        assert result["product_name"] == "AxxonOne"

    def test_key_without_value(self):
        assert _parse_metadata("force") == {"force": ""}

    def test_trailing_comma(self):
        result = _parse_metadata(f"filename {_b64('a.pdf')},")
        assert result == {"filename": "a.pdf"}

    def test_unicode_value(self):
        result = _parse_metadata(f"filename {_b64('документ.pdf')}")
        assert result["filename"] == "документ.pdf"


# ---------------------------------------------------------------------------
# SHA-256 save / load
# ---------------------------------------------------------------------------

class TestSha256Serialization:
    def test_roundtrip(self):
        from resumablesha256 import sha256 as rsha256
        h = rsha256()
        h.update(b"chunk1")
        state = _save_sha256(h)
        restored = _load_sha256(state)
        restored.update(b"chunk2")
        assert restored.hexdigest() == hashlib.sha256(b"chunk1chunk2").hexdigest()

    def test_empty_state_returns_fresh_hasher(self):
        h = _load_sha256("")
        h.update(b"data")
        assert h.hexdigest() == hashlib.sha256(b"data").hexdigest()

    def test_multiple_save_restore_cycles(self):
        from resumablesha256 import sha256 as rsha256
        h = rsha256()
        h.update(b"p1")
        s1 = _save_sha256(h)

        h2 = _load_sha256(s1)
        h2.update(b"p2")
        s2 = _save_sha256(h2)

        h3 = _load_sha256(s2)
        h3.update(b"p3")

        assert h3.hexdigest() == hashlib.sha256(b"p1p2p3").hexdigest()

    def test_large_data(self):
        from resumablesha256 import sha256 as rsha256
        data = b"x" * 10_000_000
        h = rsha256()
        h.update(data[:5_000_000])
        state = _save_sha256(h)
        h2 = _load_sha256(state)
        h2.update(data[5_000_000:])
        assert h2.hexdigest() == hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# TUS OPTIONS
# ---------------------------------------------------------------------------

class TestTusOptions:
    def setup_method(self):
        self.client = TestClient(_make_app())

    def test_returns_204(self):
        resp = self.client.request("OPTIONS", "/api/v1/uploads/")
        assert resp.status_code == 204

    def test_tus_headers(self):
        resp = self.client.request("OPTIONS", "/api/v1/uploads/")
        assert resp.headers["Tus-Resumable"] == "1.0.0"
        assert "creation" in resp.headers["Tus-Extension"]
        assert "termination" in resp.headers["Tus-Extension"]

    @patch("app.uploads.router.settings")
    def test_max_size_header(self, mock_settings):
        mock_settings.tus_max_file_size_gb = 5
        resp = self.client.request("OPTIONS", "/api/v1/uploads/")
        expected = str(5 * 1024 * 1024 * 1024)
        assert resp.headers.get("Tus-Max-Size") == expected

    @patch("app.uploads.router.settings")
    def test_no_max_size_when_zero(self, mock_settings):
        mock_settings.tus_max_file_size_gb = 0
        resp = self.client.request("OPTIONS", "/api/v1/uploads/")
        assert resp.headers.get("Tus-Max-Size", "") == ""


# ---------------------------------------------------------------------------
# TUS POST — create session
# ---------------------------------------------------------------------------

class TestTusCreate:
    def setup_method(self):
        self.client = TestClient(_make_app())

    def test_missing_upload_length(self):
        resp = self.client.post("/api/v1/uploads/", headers={"Tus-Resumable": "1.0.0"})
        assert resp.status_code == 400
        assert "Upload-Length" in resp.json()["detail"]

    def test_invalid_upload_length(self):
        resp = self.client.post(
            "/api/v1/uploads/",
            headers={"Tus-Resumable": "1.0.0", "Upload-Length": "abc"},
        )
        assert resp.status_code == 400

    def test_zero_upload_length(self):
        resp = self.client.post(
            "/api/v1/uploads/",
            headers={"Tus-Resumable": "1.0.0", "Upload-Length": "0"},
        )
        assert resp.status_code == 400

    def test_negative_upload_length(self):
        resp = self.client.post(
            "/api/v1/uploads/",
            headers={"Tus-Resumable": "1.0.0", "Upload-Length": "-100"},
        )
        assert resp.status_code == 400

    def test_missing_product_name(self):
        meta = _encode_metadata(filename="test.pdf")
        resp = self.client.post(
            "/api/v1/uploads/",
            headers={"Tus-Resumable": "1.0.0", "Upload-Length": "1000", "Upload-Metadata": meta},
        )
        assert resp.status_code == 400
        assert "product_name" in resp.json()["detail"]

    @patch("app.uploads.router._get_redis")
    @patch("app.uploads.router.check_quota", new_callable=AsyncMock)
    @patch("app.uploads.router.create_multipart_upload", return_value="mpu-id-1")
    @patch("app.uploads.router.async_session")
    def test_successful_creation(self, mock_session, mock_s3, mock_quota, mock_redis):
        mock_redis.return_value = MagicMock()
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        mock_session.return_value.__aenter__ = AsyncMock(return_value=db)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

        meta = _encode_metadata(filename="doc.pdf", product_name="TestProd", firmware_version="2.0")
        resp = self.client.post(
            "/api/v1/uploads/",
            headers={"Tus-Resumable": "1.0.0", "Upload-Length": "5000000", "Upload-Metadata": meta},
        )
        assert resp.status_code == 201
        assert "Location" in resp.headers
        assert resp.headers["Tus-Resumable"] == "1.0.0"
        assert "Upload-Expires" in resp.headers
        mock_s3.assert_called_once()
        mock_quota.assert_awaited_once()

    @patch("app.uploads.router._get_redis")
    @patch("app.uploads.router.check_quota", new_callable=AsyncMock)
    @patch("app.uploads.router.create_multipart_upload", return_value="mpu-id-2")
    @patch("app.uploads.router.async_session")
    def test_archive_detection(self, mock_session, mock_s3, mock_quota, mock_redis):
        mock_redis.return_value = MagicMock()
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        mock_session.return_value.__aenter__ = AsyncMock(return_value=db)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

        meta = _encode_metadata(filename="docs.zip", product_name="TestProd")
        resp = self.client.post(
            "/api/v1/uploads/",
            headers={"Tus-Resumable": "1.0.0", "Upload-Length": "10000", "Upload-Metadata": meta},
        )
        assert resp.status_code == 201
        added_obj = db.add.call_args[0][0]
        assert added_obj.is_archive is True

    @patch("app.uploads.router.async_session")
    def test_quota_rejection(self, mock_session):
        from app.uploads.quota import QuotaError

        db = AsyncMock()
        mock_session.return_value.__aenter__ = AsyncMock(return_value=db)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "app.uploads.router.check_quota",
            new_callable=AsyncMock,
            side_effect=QuotaError("Quota exceeded", "global_storage", 500 * 1024**3, 499 * 1024**3),
        ):
            meta = _encode_metadata(filename="huge.pdf", product_name="TestProd")
            resp = self.client.post(
                "/api/v1/uploads/",
                headers={"Tus-Resumable": "1.0.0", "Upload-Length": "999999999999", "Upload-Metadata": meta},
            )
        assert resp.status_code == 413
        body = resp.json()["detail"]
        assert body["quota_type"] == "global_storage"
        assert "limit_bytes" in body


# ---------------------------------------------------------------------------
# TUS HEAD — get offset
# ---------------------------------------------------------------------------

class TestTusHead:
    def setup_method(self):
        self.client = TestClient(_make_app())

    @patch("app.uploads.router.async_session")
    @patch("app.uploads.router._get_redis")
    def test_returns_cached_offset(self, mock_redis, mock_session):
        r = MagicMock()
        r.get.return_value = "12345"
        mock_redis.return_value = r

        resp = self.client.head("/api/v1/uploads/some-id")
        assert resp.status_code == 200
        assert resp.headers["Upload-Offset"] == "12345"
        assert resp.headers["Cache-Control"] == "no-store"

    @patch("app.uploads.router.async_session")
    @patch("app.uploads.router._get_redis")
    def test_falls_back_to_db(self, mock_redis, mock_session):
        r = MagicMock()
        r.get.return_value = None
        mock_redis.return_value = r

        us = MagicMock()
        us.offset = 50000
        us.file_size = 100000
        us.status = "uploading"

        db = AsyncMock()
        db.get = AsyncMock(return_value=us)
        mock_session.return_value.__aenter__ = AsyncMock(return_value=db)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = self.client.head("/api/v1/uploads/some-id")
        assert resp.status_code == 200
        assert resp.headers["Upload-Offset"] == "50000"
        assert resp.headers["Upload-Length"] == "100000"

    @patch("app.uploads.router.async_session")
    @patch("app.uploads.router._get_redis")
    def test_not_found(self, mock_redis, mock_session):
        r = MagicMock()
        r.get.return_value = None
        mock_redis.return_value = r

        db = AsyncMock()
        db.get = AsyncMock(return_value=None)
        mock_session.return_value.__aenter__ = AsyncMock(return_value=db)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = self.client.head("/api/v1/uploads/nonexistent")
        assert resp.status_code == 404

    @patch("app.uploads.router.async_session")
    @patch("app.uploads.router._get_redis")
    def test_gone_when_completed(self, mock_redis, mock_session):
        r = MagicMock()
        r.get.return_value = None
        mock_redis.return_value = r

        us = MagicMock()
        us.status = "completed"

        db = AsyncMock()
        db.get = AsyncMock(return_value=us)
        mock_session.return_value.__aenter__ = AsyncMock(return_value=db)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = self.client.head("/api/v1/uploads/done-id")
        assert resp.status_code == 410


# ---------------------------------------------------------------------------
# TUS PATCH — validation
# ---------------------------------------------------------------------------

class TestTusPatchValidation:
    def setup_method(self):
        self.client = TestClient(_make_app())

    def test_wrong_content_type(self):
        resp = self.client.patch(
            "/api/v1/uploads/fake-id",
            headers={"Tus-Resumable": "1.0.0", "Upload-Offset": "0", "Content-Type": "application/json"},
        )
        assert resp.status_code == 415

    def test_missing_upload_offset(self):
        resp = self.client.patch(
            "/api/v1/uploads/fake-id",
            headers={"Tus-Resumable": "1.0.0", "Content-Type": "application/offset+octet-stream"},
        )
        assert resp.status_code == 400
        assert "Upload-Offset" in resp.json()["detail"]

    def test_invalid_upload_offset(self):
        resp = self.client.patch(
            "/api/v1/uploads/fake-id",
            headers={
                "Tus-Resumable": "1.0.0",
                "Content-Type": "application/offset+octet-stream",
                "Upload-Offset": "not-a-number",
            },
        )
        assert resp.status_code == 400

    @patch("app.uploads.router._get_redis")
    @patch("app.uploads.router.async_session")
    def test_not_found(self, mock_session, mock_redis):
        mock_redis.return_value = MagicMock()
        db = AsyncMock()
        db.get = AsyncMock(return_value=None)
        mock_session.return_value.__aenter__ = AsyncMock(return_value=db)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = self.client.patch(
            "/api/v1/uploads/nonexistent",
            headers={
                "Tus-Resumable": "1.0.0",
                "Content-Type": "application/offset+octet-stream",
                "Upload-Offset": "0",
            },
            content=b"data",
        )
        assert resp.status_code == 404

    @patch("app.uploads.router._get_redis")
    @patch("app.uploads.router.async_session")
    def test_offset_mismatch(self, mock_session, mock_redis):
        mock_redis.return_value = MagicMock()

        us = MagicMock()
        us.status = "uploading"
        us.offset = 100

        db = AsyncMock()
        db.get = AsyncMock(return_value=us)
        mock_session.return_value.__aenter__ = AsyncMock(return_value=db)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = self.client.patch(
            "/api/v1/uploads/some-id",
            headers={
                "Tus-Resumable": "1.0.0",
                "Content-Type": "application/offset+octet-stream",
                "Upload-Offset": "0",
            },
            content=b"data",
        )
        assert resp.status_code == 409
        assert "mismatch" in resp.json()["detail"].lower()

    @patch("app.uploads.router._get_redis")
    @patch("app.uploads.router.async_session")
    def test_gone_when_expired(self, mock_session, mock_redis):
        mock_redis.return_value = MagicMock()

        us = MagicMock()
        us.status = "expired"

        db = AsyncMock()
        db.get = AsyncMock(return_value=us)
        mock_session.return_value.__aenter__ = AsyncMock(return_value=db)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = self.client.patch(
            "/api/v1/uploads/expired-id",
            headers={
                "Tus-Resumable": "1.0.0",
                "Content-Type": "application/offset+octet-stream",
                "Upload-Offset": "0",
            },
            content=b"data",
        )
        assert resp.status_code == 410


# ---------------------------------------------------------------------------
# TUS PATCH — successful chunk upload (non-final)
# ---------------------------------------------------------------------------

class TestTusPatchSuccess:
    def setup_method(self):
        self.client = TestClient(_make_app())

    @patch("app.uploads.router._get_redis")
    @patch("app.uploads.router.upload_part", return_value='"etag-1"')
    @patch("app.uploads.router.async_session")
    def test_non_final_chunk(self, mock_session, mock_upload_part, mock_redis):
        mock_redis.return_value = MagicMock()

        us = MagicMock()
        us.status = "uploading"
        us.offset = 0
        us.file_size = 20_000_000
        us.parts_json = "[]"
        us.sha256_state = ""
        us.s3_key = "uploads/test/source.pdf"
        us.s3_upload_id = "mpu-1"

        db = AsyncMock()
        db.get = AsyncMock(return_value=us)
        db.commit = AsyncMock()
        mock_session.return_value.__aenter__ = AsyncMock(return_value=db)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

        chunk = b"x" * 1000
        resp = self.client.patch(
            "/api/v1/uploads/test-id",
            headers={
                "Tus-Resumable": "1.0.0",
                "Content-Type": "application/offset+octet-stream",
                "Upload-Offset": "0",
            },
            content=chunk,
        )
        assert resp.status_code == 204
        assert resp.headers["Upload-Offset"] == "1000"
        assert "Upload-Complete" not in resp.headers
        assert us.offset == 1000

    @patch("app.uploads.router._finalize_upload", new_callable=AsyncMock, return_value=42)
    @patch("app.uploads.router.complete_multipart_upload")
    @patch("app.uploads.router._get_redis")
    @patch("app.uploads.router.upload_part", return_value='"etag-final"')
    @patch("app.uploads.router.async_session")
    def test_final_chunk(self, mock_session, mock_upload_part, mock_redis, mock_complete, mock_finalize):
        r = MagicMock()
        mock_redis.return_value = r

        us = MagicMock()
        us.status = "uploading"
        us.offset = 0
        us.file_size = 500
        us.parts_json = "[]"
        us.sha256_state = ""
        us.s3_key = "uploads/test/source.pdf"
        us.s3_upload_id = "mpu-2"
        us.id = "test-final-id"

        db = AsyncMock()
        db.get = AsyncMock(return_value=us)
        db.commit = AsyncMock()
        mock_session.return_value.__aenter__ = AsyncMock(return_value=db)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

        chunk = b"A" * 500
        resp = self.client.patch(
            "/api/v1/uploads/test-final-id",
            headers={
                "Tus-Resumable": "1.0.0",
                "Content-Type": "application/offset+octet-stream",
                "Upload-Offset": "0",
            },
            content=chunk,
        )
        assert resp.status_code == 204
        assert resp.headers["Upload-Complete"] == "true"
        assert resp.headers["X-Document-Id"] == "42"
        assert "X-Source-Hash" in resp.headers
        assert us.status == "completed"
        mock_complete.assert_called_once()
        mock_finalize.assert_awaited_once()
        r.delete.assert_called()


# ---------------------------------------------------------------------------
# TUS DELETE
# ---------------------------------------------------------------------------

class TestTusDelete:
    def setup_method(self):
        self.client = TestClient(_make_app())

    @patch("app.uploads.router._get_redis")
    @patch("app.uploads.router.async_session")
    def test_not_found(self, mock_session, mock_redis):
        mock_redis.return_value = MagicMock()
        db = AsyncMock()
        db.get = AsyncMock(return_value=None)
        mock_session.return_value.__aenter__ = AsyncMock(return_value=db)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = self.client.delete("/api/v1/uploads/nonexistent")
        assert resp.status_code == 404

    @patch("app.uploads.router._get_redis")
    @patch("app.uploads.router.abort_multipart_upload")
    @patch("app.uploads.router.async_session")
    def test_cancels_uploading_session(self, mock_session, mock_abort, mock_redis):
        mock_redis.return_value = MagicMock()

        us = MagicMock()
        us.status = "uploading"
        us.s3_upload_id = "mpu-to-abort"
        us.s3_key = "uploads/x/source.pdf"

        db = AsyncMock()
        db.get = AsyncMock(return_value=us)
        db.commit = AsyncMock()
        mock_session.return_value.__aenter__ = AsyncMock(return_value=db)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = self.client.delete("/api/v1/uploads/cancel-me")
        assert resp.status_code == 204
        assert us.status == "cancelled"
        mock_abort.assert_called_once_with("uploads/x/source.pdf", "mpu-to-abort")

    @patch("app.uploads.router._get_redis")
    @patch("app.uploads.router.abort_multipart_upload", side_effect=Exception("S3 error"))
    @patch("app.uploads.router.async_session")
    def test_delete_succeeds_even_if_s3_abort_fails(self, mock_session, mock_abort, mock_redis):
        mock_redis.return_value = MagicMock()

        us = MagicMock()
        us.status = "uploading"
        us.s3_upload_id = "mpu-fail"
        us.s3_key = "uploads/y/source.pdf"

        db = AsyncMock()
        db.get = AsyncMock(return_value=us)
        db.commit = AsyncMock()
        mock_session.return_value.__aenter__ = AsyncMock(return_value=db)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = self.client.delete("/api/v1/uploads/fail-abort")
        assert resp.status_code == 204
        assert us.status == "cancelled"

    @patch("app.uploads.router._get_redis")
    @patch("app.uploads.router.async_session")
    def test_delete_already_completed(self, mock_session, mock_redis):
        mock_redis.return_value = MagicMock()

        us = MagicMock()
        us.status = "completed"
        us.s3_upload_id = ""

        db = AsyncMock()
        db.get = AsyncMock(return_value=us)
        db.commit = AsyncMock()
        mock_session.return_value.__aenter__ = AsyncMock(return_value=db)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = self.client.delete("/api/v1/uploads/already-done")
        assert resp.status_code == 204
        assert us.status == "cancelled"
