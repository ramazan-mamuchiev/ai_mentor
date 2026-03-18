"""Unit tests for document REST API endpoints (business logic)."""

import hashlib
import io
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.documents.schemas import (
    DeleteResponse,
    DocumentDownload,
    DocumentListItem,
    DocumentStatus,
    IngestResponse,
)


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestIngestResponseSchema:
    def test_basic(self):
        r = IngestResponse(document_id=1, status="pending", message="queued", task_id="abc-123")
        assert r.document_id == 1
        assert r.task_id == "abc-123"

    def test_no_task_id(self):
        r = IngestResponse(document_id=1, status="pending", message="queued")
        assert r.task_id is None

    def test_skipped_with_existing_info(self):
        r = IngestResponse(
            document_id=10,
            status="skipped",
            message="Duplicate",
            existing_document_id=10,
            existing_document_title="Old Doc",
        )
        assert r.status == "skipped"
        assert r.existing_document_id == 10
        assert r.existing_document_title == "Old Doc"
        assert r.task_id is None

    def test_existing_fields_default_none(self):
        r = IngestResponse(document_id=1, status="pending", message="ok")
        assert r.existing_document_id is None
        assert r.existing_document_title is None


class TestDocumentStatusSchema:
    def test_full(self):
        now = datetime.now(timezone.utc)
        s = DocumentStatus(
            document_id=1, status="ready", title="Manual", format="pdf",
            original_filename="manual.pdf", file_size_bytes=1024,
            total_chunks=10, ingested_at=now,
        )
        assert s.total_chunks == 10
        assert s.error_message is None

    def test_with_error(self):
        now = datetime.now(timezone.utc)
        s = DocumentStatus(
            document_id=1, status="error", title="Bad", format="pdf",
            original_filename="bad.pdf", file_size_bytes=0, total_chunks=0,
            error_message="Parse failed", ingested_at=now,
        )
        assert s.error_message == "Parse failed"


class TestDocumentListItemSchema:
    def test_basic(self):
        now = datetime.now(timezone.utc)
        item = DocumentListItem(
            id=1, title="Test", format="markdown", status="ready",
            original_filename="test.md", file_size_bytes=512, total_chunks=5,
            product_name="Camera", firmware_version="1.0", ingested_at=now,
        )
        assert item.product_name == "Camera"


class TestDocumentDownloadSchema:
    def test_default_expires(self):
        d = DocumentDownload(
            document_id=1, original_filename="doc.pdf",
            download_url="https://minio/presigned",
        )
        assert d.expires_in_seconds == 900


class TestDeleteResponseSchema:
    def test_basic(self):
        r = DeleteResponse(document_id=1, deleted=True, message="ok")
        assert r.deleted is True


# ---------------------------------------------------------------------------
# Router endpoint tests (mock DB + S3 + Celery)
# ---------------------------------------------------------------------------

def _make_upload_file(filename: str, content: bytes, content_type: str = "text/markdown"):
    """Helper: create a mock UploadFile-like object for testing."""
    from fastapi import UploadFile
    return UploadFile(
        filename=filename,
        file=io.BytesIO(content),
        headers={"content-type": content_type},
    )


def _make_mock_document(doc_id=1, **overrides):
    """Helper: create a mock Document ORM object."""
    doc = MagicMock()
    doc.id = doc_id
    doc.status = overrides.get("status", "pending")
    doc.title = overrides.get("title", "test-doc")
    doc.format = overrides.get("format", "markdown")
    doc.original_filename = overrides.get("original_filename", "test.md")
    doc.file_size_bytes = overrides.get("file_size_bytes", 100)
    doc.total_chunks = overrides.get("total_chunks", 0)
    doc.error_message = overrides.get("error_message", None)
    doc.s3_key = overrides.get("s3_key", "documents/1/source.md")
    doc.ingested_at = overrides.get("ingested_at", datetime.now(timezone.utc))
    doc.source_hash = overrides.get("source_hash", "abc123")
    doc.product_id = overrides.get("product_id", 1)
    doc.firmware_version_id = overrides.get("firmware_version_id", 1)
    return doc


class TestIngestEndpointValidation:
    """Test POST /documents/ingest validation logic."""

    @pytest.mark.asyncio
    async def test_rejects_unsupported_extension(self):
        from app.documents.router import ingest_document
        upload = _make_upload_file("virus.exe", b"MZ...")
        with pytest.raises(Exception) as exc_info:
            await ingest_document(
                request=_mock_request(),
                file=upload, product_name="Dev", firmware_version="1.0",
            )
        assert "Unsupported file extension" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_rejects_empty_file(self):
        from app.documents.router import ingest_document
        upload = _make_upload_file("empty.md", b"")
        with pytest.raises(Exception) as exc_info:
            await ingest_document(
                request=_mock_request(),
                file=upload, product_name="Dev", firmware_version="1.0",
            )
        assert "Empty file" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_rejects_oversized_file(self):
        from app.documents.router import ingest_document, MAX_UPLOAD_BYTES
        big_data = b"x" * (MAX_UPLOAD_BYTES + 1)
        upload = _make_upload_file("big.md", big_data)
        with pytest.raises(Exception) as exc_info:
            await ingest_document(
                request=_mock_request(),
                file=upload, product_name="Dev", firmware_version="1.0",
            )
        assert "File too large" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_accepts_valid_extensions(self):
        """All allowed extensions should pass validation (before DB)."""
        from app.documents.router import ALLOWED_EXTENSIONS
        for ext in ALLOWED_EXTENSIONS:
            upload = _make_upload_file(f"doc{ext}", b"content")
            try:
                from app.documents.router import ingest_document
                await ingest_document(
                    request=_mock_request(),
                    file=upload, product_name="Dev", firmware_version="1.0",
                )
            except Exception as e:
                assert "Unsupported file extension" not in str(e)


class TestIngestEndpointSuccess:
    """Test POST /documents/ingest happy path with mocked dependencies."""

    @pytest.mark.asyncio
    @patch("app.documents.router.async_session")
    @patch("app.documents.router.upload_file")
    @patch("app.documents.router.s3_key_for_document", return_value="documents/1/source.md")
    async def test_upload_creates_document_and_queues_task(
        self, mock_s3_key, mock_upload, mock_session_factory
    ):
        mock_product = MagicMock(id=1)
        mock_fw = MagicMock(id=1)
        mock_doc = MagicMock(id=42)

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.add = MagicMock()

        mock_ctx = _mock_session_ctx(mock_session)
        mock_session_factory.return_value = mock_ctx

        mock_task = MagicMock(id="task-uuid-123")

        with (
            patch("app.documents.router._find_by_hash", new_callable=AsyncMock, return_value=None),
            patch("app.documents.router._get_or_create_product", new_callable=AsyncMock, return_value=mock_product),
            patch("app.documents.router._get_or_create_firmware", new_callable=AsyncMock, return_value=mock_fw),
            patch("app.celery_app.ingest_document_task") as mock_celery_task,
            patch("app.documents.router.Document") as MockDocument,
        ):
            mock_celery_task.delay = MagicMock(return_value=mock_task)
            MockDocument.return_value = mock_doc

            from app.documents.router import ingest_document
            upload = _make_upload_file("readme.md", b"# Hello World\n\nSome content here.")

            result = await ingest_document(
                request=_mock_request(),
                file=upload, product_name="TestDev", firmware_version="2.0",
            )

            assert result.status == "pending"
            assert result.task_id == "task-uuid-123"
            mock_upload.assert_called_once()
            mock_celery_task.delay.assert_called_once()


class TestGetDocumentEndpoint:
    """Test GET /documents/{id} endpoint."""

    @pytest.mark.asyncio
    @patch("app.documents.router.async_session")
    async def test_returns_document(self, mock_session_factory):
        doc = _make_mock_document(doc_id=5, status="ready", total_chunks=10)

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=doc)
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory.return_value = mock_ctx

        from app.documents.router import get_document
        result = await get_document(5)

        assert result.document_id == 5
        assert result.status == "ready"
        assert result.total_chunks == 10

    @pytest.mark.asyncio
    @patch("app.documents.router.async_session")
    async def test_returns_404_when_not_found(self, mock_session_factory):
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=None)
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory.return_value = mock_ctx

        from app.documents.router import get_document
        with pytest.raises(Exception) as exc_info:
            await get_document(999)
        assert exc_info.value.status_code == 404


class TestDownloadEndpoint:
    """Test GET /documents/{id}/download endpoint."""

    @pytest.mark.asyncio
    @patch("app.documents.router.generate_presigned_url", return_value="https://minio/signed-url")
    @patch("app.documents.router.async_session")
    async def test_returns_presigned_url(self, mock_session_factory, mock_presigned):
        doc = _make_mock_document(doc_id=3, s3_key="documents/3/source.pdf", original_filename="manual.pdf")

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=doc)
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory.return_value = mock_ctx

        from app.documents.router import download_document
        result = await download_document(3)

        assert result.download_url == "https://minio/signed-url"
        assert result.original_filename == "manual.pdf"
        mock_presigned.assert_called_once_with("documents/3/source.pdf", expires_in=900)

    @pytest.mark.asyncio
    @patch("app.documents.router.async_session")
    async def test_returns_404_when_no_s3_key(self, mock_session_factory):
        doc = _make_mock_document(doc_id=3, s3_key="")

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=doc)
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory.return_value = mock_ctx

        from app.documents.router import download_document
        with pytest.raises(Exception) as exc_info:
            await download_document(3)
        assert exc_info.value.status_code == 404
        assert "No file stored" in str(exc_info.value.detail)


class TestDeleteEndpoint:
    """Test DELETE /documents/{id} endpoint."""

    @pytest.mark.asyncio
    @patch("app.documents.router.delete_file")
    @patch("app.documents.router.async_session")
    async def test_deletes_document_and_s3(self, mock_session_factory, mock_s3_delete):
        doc = _make_mock_document(doc_id=7, s3_key="documents/7/source.md")

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=doc)
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.delete = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory.return_value = mock_ctx

        from app.documents.router import delete_document
        result = await delete_document(7)

        assert result.deleted is True
        assert result.document_id == 7
        mock_s3_delete.assert_called_once_with("documents/7/source.md")
        mock_session.delete.assert_called_once_with(doc)

    @pytest.mark.asyncio
    @patch("app.documents.router.async_session")
    async def test_delete_returns_404_when_not_found(self, mock_session_factory):
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=None)
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory.return_value = mock_ctx

        from app.documents.router import delete_document
        with pytest.raises(Exception) as exc_info:
            await delete_document(999)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("app.documents.router.delete_file", side_effect=Exception("S3 error"))
    @patch("app.documents.router.async_session")
    async def test_delete_succeeds_even_if_s3_fails(self, mock_session_factory, mock_s3_delete):
        """S3 deletion failure should not prevent document deletion from DB."""
        doc = _make_mock_document(doc_id=8, s3_key="documents/8/source.md")

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=doc)
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.delete = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory.return_value = mock_ctx

        from app.documents.router import delete_document
        result = await delete_document(8)

        assert result.deleted is True
        mock_session.delete.assert_called_once_with(doc)


# ---------------------------------------------------------------------------
# Deduplication tests
# ---------------------------------------------------------------------------

def _mock_session_ctx(mock_session):
    """Helper: wrap a mock session into an async context manager."""
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_ctx


def _mock_request():
    """Helper: create a mock Request object."""
    req = MagicMock()
    req.headers = {}
    req.client = MagicMock()
    req.client.host = "127.0.0.1"
    return req


class TestFindByHash:
    """Unit tests for _find_by_hash helper."""

    @pytest.mark.asyncio
    async def test_returns_document_when_hash_matches(self):
        from app.documents.router import _find_by_hash

        existing_doc = _make_mock_document(doc_id=10, source_hash="abc123")
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=existing_doc)
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await _find_by_hash(mock_session, "abc123")
        assert result is existing_doc
        assert result.id == 10

    @pytest.mark.asyncio
    async def test_returns_none_when_no_match(self):
        from app.documents.router import _find_by_hash

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await _find_by_hash(mock_session, "nonexistent_hash")
        assert result is None


class TestDeduplication:
    """Test POST /documents/ingest deduplication logic."""

    @pytest.mark.asyncio
    async def test_duplicate_returns_skipped(self):
        """When content hash matches an existing doc, return status=skipped."""
        existing_doc = _make_mock_document(
            doc_id=42,
            title="Original Manual",
            original_filename="manual_v1.md",
            source_hash=hashlib.sha256(b"# Hello World").hexdigest(),
        )

        mock_session = AsyncMock()
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_ctx = _mock_session_ctx(mock_session)

        mock_find = AsyncMock(return_value=existing_doc)

        with (
            patch("app.documents.router.async_session", return_value=mock_ctx),
            patch("app.documents.router._find_by_hash", mock_find),
        ):
            from app.documents.router import ingest_document

            upload = _make_upload_file("manual_v2.md", b"# Hello World")
            result = await ingest_document(
                request=_mock_request(),
                file=upload,
                product_name="TestDev",
                firmware_version="1.0",
                manufacturer="",
                format="auto",
                force=False,
            )

            assert result.status == "skipped"
            assert result.document_id == 42
            assert result.existing_document_id == 42
            assert result.existing_document_title == "Original Manual"
            assert result.task_id is None
            assert "уже загружен" in result.message
            mock_find.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.documents.router.async_session")
    @patch("app.documents.router.upload_file")
    @patch("app.documents.router.s3_key_for_document", return_value="documents/99/source.md")
    async def test_force_bypasses_deduplication(
        self, mock_s3_key, mock_upload, mock_session_factory
    ):
        """When force=True, upload even if hash matches."""
        mock_product = MagicMock(id=1)
        mock_fw = MagicMock(id=1)
        mock_doc = MagicMock(id=99)

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.add = MagicMock()
        mock_ctx = _mock_session_ctx(mock_session)
        mock_session_factory.return_value = mock_ctx

        mock_task = MagicMock(id="task-force-123")

        with (
            patch(
                "app.documents.router._get_or_create_product",
                new_callable=AsyncMock,
                return_value=mock_product,
            ),
            patch(
                "app.documents.router._get_or_create_firmware",
                new_callable=AsyncMock,
                return_value=mock_fw,
            ),
            patch("app.celery_app.ingest_document_task") as mock_celery_task,
            patch("app.documents.router.Document") as MockDocument,
            patch("app.documents.router._find_by_hash", new_callable=AsyncMock) as mock_find,
        ):
            mock_celery_task.delay = MagicMock(return_value=mock_task)
            MockDocument.return_value = mock_doc

            from app.documents.router import ingest_document

            upload = _make_upload_file("readme.md", b"# Hello World")
            result = await ingest_document(
                request=_mock_request(),
                file=upload,
                product_name="TestDev",
                firmware_version="1.0",
                force=True,
            )

            assert result.status == "pending"
            assert result.task_id == "task-force-123"
            mock_find.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.documents.router.async_session")
    @patch("app.documents.router.upload_file")
    @patch("app.documents.router.s3_key_for_document", return_value="documents/50/source.md")
    async def test_no_duplicate_proceeds_normally(
        self, mock_s3_key, mock_upload, mock_session_factory
    ):
        """When no hash match exists, proceed with normal ingestion."""
        mock_product = MagicMock(id=1)
        mock_fw = MagicMock(id=1)
        mock_doc = MagicMock(id=50)

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.add = MagicMock()
        mock_ctx = _mock_session_ctx(mock_session)
        mock_session_factory.return_value = mock_ctx

        mock_task = MagicMock(id="task-new-456")

        with (
            patch(
                "app.documents.router._find_by_hash",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "app.documents.router._get_or_create_product",
                new_callable=AsyncMock,
                return_value=mock_product,
            ),
            patch(
                "app.documents.router._get_or_create_firmware",
                new_callable=AsyncMock,
                return_value=mock_fw,
            ),
            patch("app.celery_app.ingest_document_task") as mock_celery_task,
            patch("app.documents.router.Document") as MockDocument,
        ):
            mock_celery_task.delay = MagicMock(return_value=mock_task)
            MockDocument.return_value = mock_doc

            from app.documents.router import ingest_document

            upload = _make_upload_file("new_doc.md", b"# Brand new content")
            result = await ingest_document(
                request=_mock_request(),
                file=upload,
                product_name="TestDev",
                firmware_version="1.0",
            )

            assert result.status == "pending"
            assert result.task_id == "task-new-456"
            assert result.existing_document_id is None

    @pytest.mark.asyncio
    async def test_duplicate_preserves_existing_document_info(self):
        """Skipped response must include correct existing doc metadata."""
        content = b"Exact same content bytes"
        content_hash = hashlib.sha256(content).hexdigest()

        existing_doc = _make_mock_document(
            doc_id=77,
            title="Protocol Guide v3",
            original_filename="protocol_guide_v3.md",
            source_hash=content_hash,
        )

        mock_session = AsyncMock()
        mock_ctx = _mock_session_ctx(mock_session)

        mock_find = AsyncMock(return_value=existing_doc)

        with (
            patch("app.documents.router.async_session", return_value=mock_ctx),
            patch("app.documents.router._find_by_hash", mock_find),
        ):
            from app.documents.router import ingest_document

            upload = _make_upload_file("renamed_protocol.md", content)
            result = await ingest_document(
                request=_mock_request(),
                file=upload,
                product_name="AnyProduct",
                firmware_version="1.0",
                manufacturer="",
                format="auto",
                force=False,
            )

            assert result.status == "skipped"
            assert result.existing_document_id == 77
            assert result.existing_document_title == "Protocol Guide v3"
            assert "protocol_guide_v3.md" in result.message
            mock_find.assert_called_once()
