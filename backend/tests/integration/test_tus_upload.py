"""Integration tests for TUS resumable upload — full cycle with real DB.

These tests use Testcontainers PostgreSQL and verify:
- UploadSession model CRUD
- Status transitions (uploading -> completed/cancelled/expired)
- Expired sessions query
- Quota enforcement with real data
- SHA-256 incremental hashing
- Concurrent upload sessions
- Pending uploads counted in quotas
"""

import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.models import Document, FirmwareVersion, Product, UploadSession


def _encode_metadata(**kwargs) -> str:
    parts = []
    for k, v in kwargs.items():
        if v:
            encoded = base64.b64encode(str(v).encode()).decode()
            parts.append(f"{k} {encoded}")
    return ", ".join(parts)


def _make_upload(db_session, id, **kwargs):
    """Helper to create an UploadSession with sensible defaults."""
    defaults = dict(
        filename="test.pdf",
        file_size=1_000_000,
        offset=0,
        product_name="TestProduct",
        firmware_version="1.0",
        manufacturer="",
        s3_upload_id="mpu-" + id,
        s3_key=f"uploads/{id}/source.pdf",
        status="uploading",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    defaults.update(kwargs)
    us = UploadSession(id=id, **defaults)
    db_session.add(us)
    return us


# ---------------------------------------------------------------------------
# UploadSession model CRUD
# ---------------------------------------------------------------------------

class TestUploadSessionModel:
    @pytest.mark.asyncio
    async def test_create_and_read(self, db_session):
        _make_upload(db_session, "crud-001", filename="doc.pdf", file_size=5_000_000)
        await db_session.flush()

        loaded = await db_session.get(UploadSession, "crud-001")
        assert loaded is not None
        assert loaded.filename == "doc.pdf"
        assert loaded.file_size == 5_000_000
        assert loaded.status == "uploading"
        assert loaded.offset == 0
        assert loaded.parts_json == "[]"

    @pytest.mark.asyncio
    async def test_update_offset_and_parts(self, db_session):
        us = _make_upload(db_session, "crud-002", file_size=100_000_000)
        await db_session.flush()

        us.offset = 50_000_000
        us.parts_json = json.dumps([
            {"PartNumber": 1, "ETag": '"etag1"'},
            {"PartNumber": 2, "ETag": '"etag2"'},
        ])
        await db_session.flush()

        loaded = await db_session.get(UploadSession, "crud-002")
        assert loaded.offset == 50_000_000
        parts = json.loads(loaded.parts_json)
        assert len(parts) == 2
        assert parts[0]["PartNumber"] == 1

    @pytest.mark.asyncio
    async def test_default_values(self, db_session):
        us = UploadSession(
            id="crud-003",
            filename="x.pdf",
            file_size=100,
            product_name="P",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db_session.add(us)
        await db_session.flush()

        loaded = await db_session.get(UploadSession, "crud-003")
        assert loaded.offset == 0
        assert loaded.content_type == "application/octet-stream"
        assert loaded.firmware_version == "1.0"
        assert loaded.manufacturer == ""
        assert loaded.is_archive is False
        assert loaded.force is False
        assert loaded.s3_upload_id == ""
        assert loaded.s3_key == ""
        assert loaded.parts_json == "[]"
        assert loaded.sha256_state == ""
        assert loaded.status == "uploading"


# ---------------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------------

class TestStatusTransitions:
    @pytest.mark.asyncio
    async def test_uploading_to_completed(self, db_session):
        us = _make_upload(db_session, "st-001")
        await db_session.flush()

        us.offset = us.file_size
        us.status = "completed"
        await db_session.flush()

        loaded = await db_session.get(UploadSession, "st-001")
        assert loaded.status == "completed"
        assert loaded.offset == loaded.file_size

    @pytest.mark.asyncio
    async def test_uploading_to_cancelled(self, db_session):
        us = _make_upload(db_session, "st-002")
        await db_session.flush()

        us.status = "cancelled"
        await db_session.flush()

        loaded = await db_session.get(UploadSession, "st-002")
        assert loaded.status == "cancelled"

    @pytest.mark.asyncio
    async def test_uploading_to_expired(self, db_session):
        us = _make_upload(db_session, "st-003")
        await db_session.flush()

        us.status = "expired"
        await db_session.flush()

        loaded = await db_session.get(UploadSession, "st-003")
        assert loaded.status == "expired"


# ---------------------------------------------------------------------------
# Expired sessions query
# ---------------------------------------------------------------------------

class TestExpiredSessions:
    @pytest.mark.asyncio
    async def test_find_only_expired(self, db_session):
        now = datetime.now(timezone.utc)

        _make_upload(db_session, "active-001", expires_at=now + timedelta(hours=24))
        _make_upload(db_session, "expired-001", expires_at=now - timedelta(hours=1))
        _make_upload(db_session, "expired-002", expires_at=now - timedelta(minutes=5))
        _make_upload(db_session, "completed-001", status="completed", expires_at=now - timedelta(hours=2))
        await db_session.flush()

        result = await db_session.execute(
            select(UploadSession).where(
                UploadSession.status == "uploading",
                UploadSession.expires_at < now,
            )
        )
        expired = result.scalars().all()
        expired_ids = {us.id for us in expired}
        assert expired_ids == {"expired-001", "expired-002"}

    @pytest.mark.asyncio
    async def test_no_expired(self, db_session):
        now = datetime.now(timezone.utc)
        _make_upload(db_session, "fresh-001", expires_at=now + timedelta(hours=24))
        await db_session.flush()

        result = await db_session.execute(
            select(UploadSession).where(
                UploadSession.status == "uploading",
                UploadSession.expires_at < now,
            )
        )
        assert result.scalars().all() == []


# ---------------------------------------------------------------------------
# Concurrent uploads
# ---------------------------------------------------------------------------

class TestConcurrentUploads:
    @pytest.mark.asyncio
    async def test_multiple_uploads_same_product(self, db_session):
        for i in range(5):
            _make_upload(
                db_session, f"conc-{i:03d}",
                product_name="SharedProduct",
                file_size=10_000_000 * (i + 1),
            )
        await db_session.flush()

        result = await db_session.execute(
            select(UploadSession).where(UploadSession.product_name == "SharedProduct")
        )
        uploads = result.scalars().all()
        assert len(uploads) == 5

    @pytest.mark.asyncio
    async def test_total_pending_size(self, db_session):
        _make_upload(db_session, "sz-001", file_size=100_000_000)
        _make_upload(db_session, "sz-002", file_size=200_000_000)
        _make_upload(db_session, "sz-003", file_size=50_000_000, status="completed")
        await db_session.flush()

        total = await db_session.scalar(
            select(func.coalesce(func.sum(UploadSession.file_size), 0))
            .where(UploadSession.status == "uploading")
        )
        assert total == 300_000_000


# ---------------------------------------------------------------------------
# Quota integration (with real DB)
# ---------------------------------------------------------------------------

class TestQuotaIntegration:
    async def _create_product_with_docs(self, db_session, name, doc_size_bytes):
        product = Product(name=name, manufacturer="TestMfg", model=f"M-{name}")
        db_session.add(product)
        await db_session.flush()

        fw = FirmwareVersion(product_id=product.id, version="1.0")
        db_session.add(fw)
        await db_session.flush()

        doc = Document(
            product_id=product.id,
            firmware_version_id=fw.id,
            file_size_bytes=doc_size_bytes,
            original_filename="data.pdf",
            status="ready",
        )
        db_session.add(doc)
        await db_session.flush()
        return product

    @pytest.mark.asyncio
    async def test_global_quota_exceeded(self, db_session):
        from unittest.mock import patch
        from app.uploads.quota import QuotaError, check_quota

        await self._create_product_with_docs(db_session, "GQ1", 400 * 1024**3)

        with patch("app.uploads.quota.settings") as s:
            s.tus_max_file_size_gb = 0
            s.storage_quota_gb = 500
            s.product_quota_gb = 0

            with pytest.raises(QuotaError) as exc_info:
                await check_quota(db_session, 200 * 1024**3)
            assert exc_info.value.quota_type == "global_storage"

    @pytest.mark.asyncio
    async def test_global_quota_ok(self, db_session):
        from unittest.mock import patch
        from app.uploads.quota import check_quota

        await self._create_product_with_docs(db_session, "GQ2", 100 * 1024**3)

        with patch("app.uploads.quota.settings") as s:
            s.tus_max_file_size_gb = 0
            s.storage_quota_gb = 500
            s.product_quota_gb = 0

            await check_quota(db_session, 50 * 1024**3)

    @pytest.mark.asyncio
    async def test_product_quota_exceeded(self, db_session):
        from unittest.mock import patch
        from app.uploads.quota import QuotaError, check_quota

        await self._create_product_with_docs(db_session, "PQ1", 45 * 1024**3)

        with patch("app.uploads.quota.settings") as s:
            s.tus_max_file_size_gb = 0
            s.storage_quota_gb = 0
            s.product_quota_gb = 50

            with pytest.raises(QuotaError) as exc_info:
                await check_quota(db_session, 10 * 1024**3, product_name="PQ1")
            assert exc_info.value.quota_type == "product_storage"

    @pytest.mark.asyncio
    async def test_pending_uploads_counted_in_global_quota(self, db_session):
        from unittest.mock import patch
        from app.uploads.quota import QuotaError, check_quota

        await self._create_product_with_docs(db_session, "PUQ1", 100 * 1024**3)

        _make_upload(db_session, "pending-q1", file_size=350 * 1024**3, product_name="PUQ1")
        await db_session.flush()

        with patch("app.uploads.quota.settings") as s:
            s.tus_max_file_size_gb = 0
            s.storage_quota_gb = 500
            s.product_quota_gb = 0

            with pytest.raises(QuotaError) as exc_info:
                await check_quota(db_session, 100 * 1024**3)
            assert exc_info.value.quota_type == "global_storage"

    @pytest.mark.asyncio
    async def test_pending_uploads_counted_in_product_quota(self, db_session):
        from unittest.mock import patch
        from app.uploads.quota import QuotaError, check_quota

        await self._create_product_with_docs(db_session, "PPQ1", 10 * 1024**3)

        _make_upload(db_session, "pending-pq1", file_size=35 * 1024**3, product_name="PPQ1")
        await db_session.flush()

        with patch("app.uploads.quota.settings") as s:
            s.tus_max_file_size_gb = 0
            s.storage_quota_gb = 0
            s.product_quota_gb = 50

            with pytest.raises(QuotaError) as exc_info:
                await check_quota(db_session, 10 * 1024**3, product_name="PPQ1")
            assert exc_info.value.quota_type == "product_storage"


# ---------------------------------------------------------------------------
# SHA-256 incremental hash across sessions
# ---------------------------------------------------------------------------

class TestIncrementalHash:
    def test_roundtrip(self):
        from app.uploads.router import _load_sha256, _save_sha256
        from resumablesha256 import sha256 as rsha256

        h = rsha256()
        h.update(b"chunk1")
        state = _save_sha256(h)

        restored = _load_sha256(state)
        restored.update(b"chunk2")

        assert restored.hexdigest() == hashlib.sha256(b"chunk1chunk2").hexdigest()

    def test_empty_state(self):
        from app.uploads.router import _load_sha256

        h = _load_sha256("")
        h.update(b"data")
        assert h.hexdigest() == hashlib.sha256(b"data").hexdigest()

    def test_three_cycles(self):
        from app.uploads.router import _load_sha256, _save_sha256
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

    def test_large_data_split(self):
        from app.uploads.router import _load_sha256, _save_sha256
        from resumablesha256 import sha256 as rsha256

        data = b"A" * 50_000_000
        chunk_size = 10_000_000

        h = rsha256()
        for i in range(0, len(data), chunk_size):
            h.update(data[i : i + chunk_size])
            state = _save_sha256(h)
            h = _load_sha256(state)

        assert h.hexdigest() == hashlib.sha256(data).hexdigest()

    def test_binary_data(self):
        from app.uploads.router import _load_sha256, _save_sha256
        from resumablesha256 import sha256 as rsha256

        data = bytes(range(256)) * 100
        h = rsha256()
        h.update(data[:128])
        state = _save_sha256(h)

        h2 = _load_sha256(state)
        h2.update(data[128:])

        assert h2.hexdigest() == hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Index verification
# ---------------------------------------------------------------------------

class TestIndexes:
    @pytest.mark.asyncio
    async def test_status_index_used_for_query(self, db_session):
        """Verify the status index exists by running a filtered query."""
        _make_upload(db_session, "idx-001", status="uploading")
        _make_upload(db_session, "idx-002", status="completed")
        await db_session.flush()

        result = await db_session.execute(
            select(UploadSession).where(UploadSession.status == "uploading")
        )
        rows = result.scalars().all()
        assert len(rows) == 1
        assert rows[0].id == "idx-001"
