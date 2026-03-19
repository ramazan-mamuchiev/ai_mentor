"""Storage quota enforcement.

Current checks (no auth required):
- Per-file size limit
- Per-product storage limit
- Global storage limit

Future extension points (when user auth / tariff plans are added):
- Per-user storage limit (from tariff plan)
- Per-user concurrent uploads limit
- Rate limiting per user
"""

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Document, UploadSession

logger = logging.getLogger(__name__)

_GB = 1024 * 1024 * 1024


class QuotaError(Exception):
    """Raised when an upload would exceed a storage quota."""

    def __init__(self, message: str, quota_type: str, limit_bytes: int, used_bytes: int):
        super().__init__(message)
        self.quota_type = quota_type
        self.limit_bytes = limit_bytes
        self.used_bytes = used_bytes


async def check_quota(
    session: AsyncSession,
    file_size: int,
    product_name: str | None = None,
    user_id: int | None = None,
    tariff_plan: str | None = None,
) -> None:
    """Check all applicable quotas before starting an upload.

    Raises QuotaError if any quota would be exceeded.
    """
    _check_file_size(file_size)
    await _check_global_quota(session, file_size)
    if product_name:
        await _check_product_quota(session, file_size, product_name)


def _check_file_size(file_size: int) -> None:
    limit_gb = settings.tus_max_file_size_gb
    if limit_gb <= 0:
        return
    limit_bytes = limit_gb * _GB
    if file_size > limit_bytes:
        raise QuotaError(
            f"File size {_fmt(file_size)} exceeds maximum {limit_gb} GB",
            quota_type="file_size",
            limit_bytes=limit_bytes,
            used_bytes=file_size,
        )


async def _check_global_quota(session: AsyncSession, file_size: int) -> None:
    limit_gb = settings.storage_quota_gb
    if limit_gb <= 0:
        return
    limit_bytes = limit_gb * _GB

    docs_bytes = await session.scalar(
        select(func.coalesce(func.sum(Document.file_size_bytes), 0))
    ) or 0
    pending_bytes = await session.scalar(
        select(func.coalesce(func.sum(UploadSession.file_size), 0))
        .where(UploadSession.status == "uploading")
    ) or 0
    used = docs_bytes + pending_bytes

    if used + file_size > limit_bytes:
        raise QuotaError(
            f"Global storage quota exceeded: {_fmt(used)} used + {_fmt(file_size)} new "
            f"> {limit_gb} GB limit ({_fmt(limit_bytes - used)} remaining)",
            quota_type="global_storage",
            limit_bytes=limit_bytes,
            used_bytes=used,
        )


async def _check_product_quota(
    session: AsyncSession, file_size: int, product_name: str
) -> None:
    limit_gb = settings.product_quota_gb
    if limit_gb <= 0:
        return
    limit_bytes = limit_gb * _GB

    from app.models import Product

    docs_bytes = await session.scalar(
        select(func.coalesce(func.sum(Document.file_size_bytes), 0))
        .join(Product, Document.product_id == Product.id)
        .where(Product.name == product_name)
    ) or 0
    pending_bytes = await session.scalar(
        select(func.coalesce(func.sum(UploadSession.file_size), 0))
        .where(
            UploadSession.status == "uploading",
            UploadSession.product_name == product_name,
        )
    ) or 0
    used = docs_bytes + pending_bytes

    if used + file_size > limit_bytes:
        raise QuotaError(
            f"Product '{product_name}' storage quota exceeded: {_fmt(used)} used + "
            f"{_fmt(file_size)} new > {limit_gb} GB limit ({_fmt(limit_bytes - used)} remaining)",
            quota_type="product_storage",
            limit_bytes=limit_bytes,
            used_bytes=used,
        )


def _fmt(size_bytes: int) -> str:
    """Human-readable file size."""
    if size_bytes >= _GB:
        return f"{size_bytes / _GB:.1f} GB"
    mb = 1024 * 1024
    if size_bytes >= mb:
        return f"{size_bytes / mb:.1f} MB"
    return f"{size_bytes / 1024:.1f} KB"
