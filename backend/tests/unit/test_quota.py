"""Unit tests for the quota enforcement system."""

from unittest.mock import AsyncMock, patch

import pytest

from app.uploads.quota import QuotaError, check_quota, _check_file_size, _fmt

_GB = 1024 * 1024 * 1024
_MB = 1024 * 1024


# ---------------------------------------------------------------------------
# _check_file_size
# ---------------------------------------------------------------------------

class TestCheckFileSize:
    @patch("app.uploads.quota.settings")
    def test_within_limit(self, mock_settings):
        mock_settings.tus_max_file_size_gb = 10
        _check_file_size(5 * _GB)

    @patch("app.uploads.quota.settings")
    def test_exceeds_limit(self, mock_settings):
        mock_settings.tus_max_file_size_gb = 1
        with pytest.raises(QuotaError) as exc_info:
            _check_file_size(2 * _GB)
        assert exc_info.value.quota_type == "file_size"
        assert exc_info.value.limit_bytes == 1 * _GB

    @patch("app.uploads.quota.settings")
    def test_zero_means_no_limit(self, mock_settings):
        mock_settings.tus_max_file_size_gb = 0
        _check_file_size(100 * _GB)

    @patch("app.uploads.quota.settings")
    def test_exact_limit_is_ok(self, mock_settings):
        mock_settings.tus_max_file_size_gb = 1
        _check_file_size(1 * _GB)

    @patch("app.uploads.quota.settings")
    def test_one_byte_over_limit(self, mock_settings):
        mock_settings.tus_max_file_size_gb = 1
        with pytest.raises(QuotaError):
            _check_file_size(1 * _GB + 1)

    @patch("app.uploads.quota.settings")
    def test_small_file(self, mock_settings):
        mock_settings.tus_max_file_size_gb = 10
        _check_file_size(1)


# ---------------------------------------------------------------------------
# Global quota
# ---------------------------------------------------------------------------

class TestGlobalQuota:
    @pytest.mark.asyncio
    @patch("app.uploads.quota.settings")
    async def test_within_global_quota(self, mock_settings):
        mock_settings.tus_max_file_size_gb = 0
        mock_settings.storage_quota_gb = 500
        mock_settings.product_quota_gb = 0

        session = AsyncMock()
        session.scalar = AsyncMock(side_effect=[100 * _MB, 50 * _MB])

        await check_quota(session, 1 * _MB)

    @pytest.mark.asyncio
    @patch("app.uploads.quota.settings")
    async def test_exceeds_global_quota(self, mock_settings):
        mock_settings.tus_max_file_size_gb = 0
        mock_settings.storage_quota_gb = 1
        mock_settings.product_quota_gb = 0

        session = AsyncMock()
        session.scalar = AsyncMock(side_effect=[_GB - 100, 0])

        with pytest.raises(QuotaError) as exc_info:
            await check_quota(session, 200)
        assert exc_info.value.quota_type == "global_storage"

    @pytest.mark.asyncio
    @patch("app.uploads.quota.settings")
    async def test_global_quota_disabled(self, mock_settings):
        mock_settings.tus_max_file_size_gb = 0
        mock_settings.storage_quota_gb = 0
        mock_settings.product_quota_gb = 0

        session = AsyncMock()
        session.scalar = AsyncMock(return_value=0)

        await check_quota(session, 999 * _GB)

    @pytest.mark.asyncio
    @patch("app.uploads.quota.settings")
    async def test_pending_uploads_counted(self, mock_settings):
        mock_settings.tus_max_file_size_gb = 0
        mock_settings.storage_quota_gb = 1
        mock_settings.product_quota_gb = 0

        session = AsyncMock()
        session.scalar = AsyncMock(side_effect=[
            100 * _MB,
            _GB - 200 * _MB,
        ])

        with pytest.raises(QuotaError) as exc_info:
            await check_quota(session, 200 * _MB)
        assert exc_info.value.quota_type == "global_storage"


# ---------------------------------------------------------------------------
# Product quota
# ---------------------------------------------------------------------------

class TestProductQuota:
    @pytest.mark.asyncio
    @patch("app.uploads.quota.settings")
    async def test_within_product_quota(self, mock_settings):
        mock_settings.tus_max_file_size_gb = 0
        mock_settings.storage_quota_gb = 0
        mock_settings.product_quota_gb = 50

        session = AsyncMock()
        session.scalar = AsyncMock(side_effect=[10 * _GB, 5 * _GB])

        await check_quota(session, 1 * _MB, product_name="TestProduct")

    @pytest.mark.asyncio
    @patch("app.uploads.quota.settings")
    async def test_exceeds_product_quota(self, mock_settings):
        mock_settings.tus_max_file_size_gb = 0
        mock_settings.storage_quota_gb = 0
        mock_settings.product_quota_gb = 1

        session = AsyncMock()
        session.scalar = AsyncMock(side_effect=[_GB - 100, 0])

        with pytest.raises(QuotaError) as exc_info:
            await check_quota(session, 200, product_name="TestProduct")
        assert exc_info.value.quota_type == "product_storage"

    @pytest.mark.asyncio
    @patch("app.uploads.quota.settings")
    async def test_product_quota_skipped_when_no_product_name(self, mock_settings):
        mock_settings.tus_max_file_size_gb = 0
        mock_settings.storage_quota_gb = 0
        mock_settings.product_quota_gb = 1

        session = AsyncMock()
        session.scalar = AsyncMock(return_value=0)

        await check_quota(session, 2 * _GB)

    @pytest.mark.asyncio
    @patch("app.uploads.quota.settings")
    async def test_product_quota_disabled(self, mock_settings):
        mock_settings.tus_max_file_size_gb = 0
        mock_settings.storage_quota_gb = 0
        mock_settings.product_quota_gb = 0

        session = AsyncMock()
        session.scalar = AsyncMock(return_value=0)

        await check_quota(session, 999 * _GB, product_name="AnyProduct")


# ---------------------------------------------------------------------------
# All quotas together
# ---------------------------------------------------------------------------

class TestCombinedQuotas:
    @pytest.mark.asyncio
    @patch("app.uploads.quota.settings")
    async def test_file_size_checked_first(self, mock_settings):
        mock_settings.tus_max_file_size_gb = 1
        mock_settings.storage_quota_gb = 500
        mock_settings.product_quota_gb = 50

        session = AsyncMock()
        with pytest.raises(QuotaError) as exc_info:
            await check_quota(session, 2 * _GB, product_name="P")
        assert exc_info.value.quota_type == "file_size"
        session.scalar.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("app.uploads.quota.settings")
    async def test_global_checked_before_product(self, mock_settings):
        mock_settings.tus_max_file_size_gb = 0
        mock_settings.storage_quota_gb = 1
        mock_settings.product_quota_gb = 50

        session = AsyncMock()
        session.scalar = AsyncMock(side_effect=[_GB, 0])

        with pytest.raises(QuotaError) as exc_info:
            await check_quota(session, 1 * _MB, product_name="P")
        assert exc_info.value.quota_type == "global_storage"

    @pytest.mark.asyncio
    @patch("app.uploads.quota.settings")
    async def test_all_pass(self, mock_settings):
        mock_settings.tus_max_file_size_gb = 10
        mock_settings.storage_quota_gb = 500
        mock_settings.product_quota_gb = 50

        session = AsyncMock()
        session.scalar = AsyncMock(side_effect=[
            1 * _GB, 0,
            500 * _MB, 0,
        ])

        await check_quota(session, 100 * _MB, product_name="P")


# ---------------------------------------------------------------------------
# QuotaError attributes
# ---------------------------------------------------------------------------

class TestQuotaError:
    def test_attributes(self):
        err = QuotaError("msg", "file_size", 1000, 500)
        assert str(err) == "msg"
        assert err.quota_type == "file_size"
        assert err.limit_bytes == 1000
        assert err.used_bytes == 500

    def test_is_exception(self):
        assert issubclass(QuotaError, Exception)


# ---------------------------------------------------------------------------
# _fmt helper
# ---------------------------------------------------------------------------

class TestFmt:
    def test_gb(self):
        assert _fmt(_GB) == "1.0 GB"

    def test_mb(self):
        assert _fmt(10 * _MB) == "10.0 MB"

    def test_kb(self):
        assert _fmt(512 * 1024) == "512.0 KB"

    def test_fractional_gb(self):
        assert _fmt(int(1.5 * _GB)) == "1.5 GB"

    def test_small_mb(self):
        assert _fmt(int(0.5 * _MB)) == "512.0 KB"

    def test_zero(self):
        assert _fmt(0) == "0.0 KB"
