"""Unit tests for products REST API endpoints."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.products.schemas import (
    FormatCount,
    ProductDebugInfo,
    ProductDetail,
    ProductDocumentSummary,
    ProductListItem,
    ProductUpdate,
)


class TestProductListItemSchema:
    def test_basic(self):
        now = datetime.now(timezone.utc)
        item = ProductListItem(
            id=1,
            name="Camera X",
            manufacturer="Hikvision",
            model="DS-2CD",
            category="IP Camera",
            created_at=now,
            total_documents=3,
            pending_documents=0,
            processing_documents=0,
            ready_documents=3,
            error_documents=0,
            total_file_size_bytes=102400,
            total_chunks=50,
            formats=[FormatCount(format="pdf", count=2), FormatCount(format="proto", count=1)],
            uploaded_at=now,
            indexed_at=now,
            progress_percent=100,
            progress_detail="3/3 ready",
        )
        assert item.name == "Camera X"
        assert item.total_documents == 3
        assert len(item.formats) == 2

    def test_defaults(self):
        now = datetime.now(timezone.utc)
        item = ProductListItem(id=1, name="Test", created_at=now)
        assert item.total_documents == 0
        assert item.formats == []
        assert item.progress_percent == 0
        assert item.progress_detail == ""


class TestProductDetailSchema:
    def test_basic(self):
        now = datetime.now(timezone.utc)
        detail = ProductDetail(
            id=1,
            name="Camera X",
            manufacturer="Hikvision",
            model="DS-2CD",
            category="IP Camera",
            created_at=now,
            firmware_versions=["1.0", "2.0"],
        )
        assert detail.name == "Camera X"
        assert len(detail.firmware_versions) == 2


class TestProductUpdateSchema:
    def test_partial(self):
        update = ProductUpdate(name="New Name")
        assert update.name == "New Name"
        assert update.manufacturer is None
        assert update.model is None

    def test_all_fields(self):
        update = ProductUpdate(name="A", manufacturer="B", model="C", category="D")
        assert update.category == "D"


class TestProductDebugInfoSchema:
    def test_full(self):
        now = datetime.now(timezone.utc)
        info = ProductDebugInfo(
            product_id=1,
            product_name="Camera",
            total_documents=3,
            firmware_version_count=2,
            total_file_size_bytes=100000,
            sum_ingest_duration_ms=10000.0,
            avg_ingest_duration_ms=3333.3,
            total_chunks=50,
            total_tokens=10000,
            embedding_model="e5-large",
            total_embedding_tokens=10000,
            total_rag_hit_count=25,
            avg_rag_similarity=0.85,
            last_rag_used_at=now.isoformat(),
            documents=[
                ProductDocumentSummary(id=1, title="Doc1", format="pdf", file_size_bytes=50000, total_chunks=25, status="ready"),
                ProductDocumentSummary(id=2, title="Doc2", format="proto", file_size_bytes=50000, total_chunks=25, status="ready"),
            ],
        )
        assert info.total_documents == 3
        assert len(info.documents) == 2

    def test_defaults(self):
        info = ProductDebugInfo(product_id=1, product_name="Test")
        assert info.total_documents == 0
        assert info.documents == []
        assert info.sum_ingest_duration_ms is None


def _mock_session_ctx(mock_session):
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_ctx


class TestGetProductEndpoint:
    @pytest.mark.asyncio
    @patch("app.products.router.async_session")
    async def test_returns_product(self, mock_session_factory):
        mock_product = MagicMock()
        mock_product.id = 1
        mock_product.name = "Camera"
        mock_product.manufacturer = "Hikvision"
        mock_product.model = "DS-2CD"
        mock_product.category = "IP Camera"
        mock_product.created_at = datetime.now(timezone.utc)

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_product)

        mock_fw_result = MagicMock()
        mock_fw_result.all.return_value = [("1.0",), ("2.0",)]
        mock_session.execute = AsyncMock(return_value=mock_fw_result)

        mock_session_factory.return_value = _mock_session_ctx(mock_session)

        from app.products.router import get_product
        result = await get_product(1)

        assert result.id == 1
        assert result.name == "Camera"

    @pytest.mark.asyncio
    @patch("app.products.router.async_session")
    async def test_returns_404_when_not_found(self, mock_session_factory):
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=None)
        mock_session_factory.return_value = _mock_session_ctx(mock_session)

        from app.products.router import get_product
        with pytest.raises(Exception) as exc_info:
            await get_product(999)
        assert exc_info.value.status_code == 404


class TestUpdateProductEndpoint:
    @pytest.mark.asyncio
    @patch("app.products.router.async_session")
    async def test_updates_product(self, mock_session_factory):
        mock_product = MagicMock()
        mock_product.id = 1
        mock_product.name = "Old Name"
        mock_product.manufacturer = ""
        mock_product.model = ""
        mock_product.category = ""
        mock_product.created_at = datetime.now(timezone.utc)

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_product)
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        mock_fw_result = MagicMock()
        mock_fw_result.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_fw_result)

        mock_session_factory.return_value = _mock_session_ctx(mock_session)

        from app.products.router import update_product
        body = ProductUpdate(name="New Name", manufacturer="NewMfg")
        result = await update_product(1, body)

        assert mock_product.name == "New Name"
        assert mock_product.manufacturer == "NewMfg"

    @pytest.mark.asyncio
    @patch("app.products.router.async_session")
    async def test_returns_404_when_not_found(self, mock_session_factory):
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=None)
        mock_session_factory.return_value = _mock_session_ctx(mock_session)

        from app.products.router import update_product
        body = ProductUpdate(name="New")
        with pytest.raises(Exception) as exc_info:
            await update_product(999, body)
        assert exc_info.value.status_code == 404


class TestDeleteProductEndpoint:
    @pytest.mark.asyncio
    @patch("app.products.router.async_session")
    async def test_deletes_product(self, mock_session_factory):
        mock_product = MagicMock()
        mock_product.id = 1

        mock_docs_result = MagicMock()
        mock_docs_result.scalars.return_value.all.return_value = []

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_product)
        mock_session.execute = AsyncMock(return_value=mock_docs_result)
        mock_session.delete = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_session_factory.return_value = _mock_session_ctx(mock_session)

        from app.products.router import delete_product
        result = await delete_product(1)

        assert result["deleted"] is True
        mock_session.delete.assert_called_once_with(mock_product)

    @pytest.mark.asyncio
    @patch("app.products.router.async_session")
    async def test_returns_404_when_not_found(self, mock_session_factory):
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=None)
        mock_session_factory.return_value = _mock_session_ctx(mock_session)

        from app.products.router import delete_product
        with pytest.raises(Exception) as exc_info:
            await delete_product(999)
        assert exc_info.value.status_code == 404
