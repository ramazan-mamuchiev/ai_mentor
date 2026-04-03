"""TUS resumable upload protocol implementation.

Implements the core TUS v1.0.0 protocol:
- POST   /uploads       — create upload session
- HEAD   /uploads/{id}  — get current offset (for resume)
- PATCH  /uploads/{id}  — upload next chunk
- DELETE /uploads/{id}  — cancel upload
- OPTIONS /uploads      — TUS capabilities discovery

Files are streamed directly to S3 via multipart upload, never buffered
entirely in RAM. SHA-256 hash is computed incrementally across chunks
for deduplication.
"""

import base64
import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

import redis as redis_lib
from resumablesha256 import sha256 as resumable_sha256
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select

from app.auth.dependencies import get_current_tenant
from app.config import settings
from app.database import async_session
from app.documents.archive import SUPPORTED_ARCHIVE_EXTENSIONS, _archive_ext
from app.models import Document, Tenant, UploadSession
from app.s3 import (
    abort_multipart_upload,
    complete_multipart_upload,
    create_multipart_upload,
    s3_key_for_document,
    s3_key_for_upload,
    upload_part,
)
from app.uploads.quota import QuotaError, check_quota

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/uploads", tags=["uploads"])

TUS_VERSION = "1.0.0"
TUS_EXTENSIONS = "creation,termination"
S3_MIN_PART_SIZE = 5 * 1024 * 1024  # 5 MB — S3 minimum part size

_redis: redis_lib.Redis | None = None


def _get_redis() -> redis_lib.Redis:
    global _redis
    if _redis is None:
        _redis = redis_lib.from_url(settings.redis_url, decode_responses=True)
    return _redis


def _redis_offset_key(upload_id: str) -> str:
    return f"upload:{upload_id}:offset"


def _redis_hash_key(upload_id: str) -> str:
    return f"upload:{upload_id}:sha256"


def _tus_headers() -> dict[str, str]:
    return {
        "Tus-Resumable": TUS_VERSION,
        "Tus-Version": TUS_VERSION,
        "Tus-Extension": TUS_EXTENSIONS,
    }


def _parse_metadata(header: str) -> dict[str, str]:
    """Parse TUS Upload-Metadata header: 'key base64val, key2 base64val2'."""
    result = {}
    if not header:
        return result
    for pair in header.split(","):
        pair = pair.strip()
        if not pair:
            continue
        parts = pair.split(" ", 1)
        key = parts[0]
        value = base64.b64decode(parts[1]).decode("utf-8") if len(parts) > 1 else ""
        result[key] = value
    return result


@router.api_route("/", methods=["OPTIONS"], include_in_schema=False)
async def tus_options():
    """TUS capabilities discovery."""
    max_size = settings.tus_max_file_size_gb * 1024 * 1024 * 1024 if settings.tus_max_file_size_gb > 0 else 0
    headers = {
        **_tus_headers(),
        "Tus-Max-Size": str(max_size) if max_size else "",
    }
    return Response(status_code=204, headers=headers)


@router.post("/")
async def tus_create(request: Request, tenant: Tenant = Depends(get_current_tenant)):
    """Create a new upload session (TUS Creation extension)."""
    upload_length = request.headers.get("Upload-Length")
    if upload_length is None:
        raise HTTPException(status_code=400, detail="Missing Upload-Length header")

    try:
        file_size = int(upload_length)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Upload-Length")

    if file_size <= 0:
        raise HTTPException(status_code=400, detail="Upload-Length must be positive")

    metadata = _parse_metadata(request.headers.get("Upload-Metadata", ""))
    filename = metadata.get("filename", "unknown")
    product_name = metadata.get("product_name")
    if not product_name:
        raise HTTPException(status_code=400, detail="product_name is required in Upload-Metadata")

    firmware_version = metadata.get("firmware_version", "1.0")
    manufacturer = metadata.get("manufacturer", "")
    force = metadata.get("force", "false").lower() in ("true", "1", "yes")
    content_type = metadata.get("content_type", "application/octet-stream")

    ext = _archive_ext(filename) if _archive_ext(filename) in SUPPORTED_ARCHIVE_EXTENSIONS else os.path.splitext(filename)[1].lower()
    is_archive = ext in SUPPORTED_ARCHIVE_EXTENSIONS

    async with async_session() as session:
        try:
            await check_quota(session, file_size, product_name)
        except QuotaError as e:
            raise HTTPException(
                status_code=413,
                detail={
                    "error": str(e),
                    "quota_type": e.quota_type,
                    "limit_bytes": e.limit_bytes,
                    "used_bytes": e.used_bytes,
                },
            )

        upload_id = uuid.uuid4().hex
        s3_key = s3_key_for_upload(upload_id, filename)
        s3_upload_id = create_multipart_upload(s3_key, content_type)

        expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.tus_upload_ttl_hours)

        upload_session = UploadSession(
            id=upload_id,
            tenant_id=tenant.id,
            filename=filename,
            file_size=file_size,
            offset=0,
            content_type=content_type,
            product_name=product_name,
            firmware_version=firmware_version,
            manufacturer=manufacturer,
            is_archive=is_archive,
            force=force,
            s3_upload_id=s3_upload_id,
            s3_key=s3_key,
            parts_json="[]",
            sha256_state="",
            status="uploading",
            expires_at=expires_at,
        )
        session.add(upload_session)
        await session.commit()

    r = _get_redis()
    ttl_seconds = settings.tus_upload_ttl_hours * 3600
    r.set(_redis_offset_key(upload_id), 0, ex=ttl_seconds)

    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("host", request.url.netloc)
    location = f"{proto}://{host}/api/v1/uploads/{upload_id}"
    headers = {
        **_tus_headers(),
        "Location": location,
        "Upload-Expires": expires_at.strftime("%a, %d %b %Y %H:%M:%S GMT"),
    }

    logger.info(
        "TUS upload session created",
        extra={
            "upload_id": upload_id,
            "original_filename": filename,
            "file_size": file_size,
            "product_name": product_name,
            "is_archive": is_archive,
            "s3_key": s3_key,
        },
    )

    return Response(status_code=201, headers=headers)


@router.head("/{upload_id}")
async def tus_head(upload_id: str):
    """Get current upload offset (for resume after disconnect)."""
    async with async_session() as session:
        us = await session.get(UploadSession, upload_id)
        if us is None:
            raise HTTPException(status_code=404, detail="Upload session not found")
        if us.status != "uploading":
            raise HTTPException(status_code=410, detail=f"Upload session is {us.status}")

        r = _get_redis()
        cached_offset = r.get(_redis_offset_key(upload_id))
        offset = cached_offset if cached_offset is not None else str(us.offset)

        headers = {
            **_tus_headers(),
            "Upload-Offset": offset,
            "Upload-Length": str(us.file_size),
            "Cache-Control": "no-store",
        }
        return Response(status_code=200, headers=headers)


@router.patch("/{upload_id}")
async def tus_patch(upload_id: str, request: Request):
    """Upload next chunk of data (streaming to S3)."""
    ct = request.headers.get("Content-Type", "")
    if ct != "application/offset+octet-stream":
        raise HTTPException(
            status_code=415,
            detail="Content-Type must be application/offset+octet-stream",
        )

    client_offset_str = request.headers.get("Upload-Offset")
    if client_offset_str is None:
        raise HTTPException(status_code=400, detail="Missing Upload-Offset header")
    try:
        client_offset = int(client_offset_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Upload-Offset")

    async with async_session() as session:
        us = await session.get(UploadSession, upload_id)
        if us is None:
            raise HTTPException(status_code=404, detail="Upload session not found")
        if us.status != "uploading":
            raise HTTPException(status_code=410, detail=f"Upload session is {us.status}")
        if client_offset != us.offset:
            raise HTTPException(
                status_code=409,
                detail=f"Offset mismatch: client={client_offset}, server={us.offset}",
            )

        parts = json.loads(us.parts_json)
        part_number = len(parts) + 1

        hasher = _load_sha256(us.sha256_state)

        buffer = bytearray()
        bytes_received = 0

        async for chunk in request.stream():
            buffer.extend(chunk)
            bytes_received += len(chunk)

            while len(buffer) >= S3_MIN_PART_SIZE:
                part_data = bytes(buffer[:S3_MIN_PART_SIZE])
                buffer = buffer[S3_MIN_PART_SIZE:]
                hasher.update(part_data)
                etag = upload_part(us.s3_key, us.s3_upload_id, part_number, part_data)
                parts.append({"PartNumber": part_number, "ETag": etag})
                part_number += 1

        new_offset = us.offset + bytes_received
        is_final = new_offset >= us.file_size

        if buffer:
            part_data = bytes(buffer)
            hasher.update(part_data)
            etag = upload_part(us.s3_key, us.s3_upload_id, part_number, part_data)
            parts.append({"PartNumber": part_number, "ETag": etag})

        us.offset = new_offset
        us.parts_json = json.dumps(parts)
        us.sha256_state = _save_sha256(hasher)

        r = _get_redis()
        ttl_seconds = settings.tus_upload_ttl_hours * 3600
        r.set(_redis_offset_key(upload_id), new_offset, ex=ttl_seconds)

        if is_final:
            complete_multipart_upload(us.s3_key, us.s3_upload_id, parts)
            source_hash = hasher.hexdigest()

            document_id = await _finalize_upload(session, us, source_hash)
            us.status = "completed"
            await session.commit()

            r.delete(_redis_offset_key(upload_id))
            r.delete(_redis_hash_key(upload_id))

            logger.info(
                "TUS upload completed",
                extra={
                    "upload_id": upload_id,
                    "document_id": document_id,
                    "file_size": us.file_size,
                    "source_hash": source_hash,
                    "parts_count": len(parts),
                },
            )

            headers = {
                **_tus_headers(),
                "Upload-Offset": str(new_offset),
                "Upload-Complete": "true",
                "X-Document-Id": str(document_id) if document_id else "",
                "X-Source-Hash": source_hash,
            }
            return Response(status_code=204, headers=headers)

        await session.commit()

        logger.debug(
            "TUS chunk received",
            extra={
                "upload_id": upload_id,
                "bytes_received": bytes_received,
                "new_offset": new_offset,
                "file_size": us.file_size,
                "progress_pct": round(new_offset / us.file_size * 100, 1),
            },
        )

        headers = {
            **_tus_headers(),
            "Upload-Offset": str(new_offset),
        }
        return Response(status_code=204, headers=headers)


@router.delete("/{upload_id}")
async def tus_delete(upload_id: str):
    """Cancel and clean up an upload session (TUS Termination extension)."""
    async with async_session() as session:
        us = await session.get(UploadSession, upload_id)
        if us is None:
            raise HTTPException(status_code=404, detail="Upload session not found")

        if us.status == "uploading" and us.s3_upload_id:
            try:
                abort_multipart_upload(us.s3_key, us.s3_upload_id)
            except Exception:
                logger.warning("Failed to abort S3 multipart", exc_info=True)

        us.status = "cancelled"
        await session.commit()

    r = _get_redis()
    r.delete(_redis_offset_key(upload_id))
    r.delete(_redis_hash_key(upload_id))

    logger.info("TUS upload cancelled", extra={"upload_id": upload_id})
    return Response(status_code=204, headers=_tus_headers())


async def _finalize_upload(session, us: UploadSession, source_hash: str) -> int | None:
    """Create Document record and trigger ingestion after upload completes.

    For archives: no Document is created for the archive itself. Instead, the
    Celery task extracts inner files and creates Documents for each one.
    """
    from app.documents.router import _find_by_hash, _get_or_create_firmware, _get_or_create_product

    upload_tenant_id = us.tenant_id

    if us.is_archive:
        product = await _get_or_create_product(session, us.product_name, us.manufacturer, tenant_id=upload_tenant_id)
        fw = await _get_or_create_firmware(session, product.id, us.firmware_version)
        await session.commit()

        from app.celery_app import ingest_archive_from_s3_task
        ingest_archive_from_s3_task.delay(
            us.s3_key, us.filename, product.id, fw.id, us.force,
            str(upload_tenant_id) if upload_tenant_id else None,
        )
        return None

    product = await _get_or_create_product(session, us.product_name, us.manufacturer, tenant_id=upload_tenant_id)
    fw = await _get_or_create_firmware(session, product.id, us.firmware_version)

    if not us.force:
        existing = await _find_by_hash(session, source_hash, product.id, fw.id)
        if existing is not None:
            logger.info(
                "TUS upload completed but duplicate found",
                extra={
                    "upload_id": us.id,
                    "existing_document_id": existing.id,
                    "source_hash": source_hash,
                },
            )
            return existing.id

    doc = Document(
        product_id=product.id,
        firmware_version_id=fw.id,
        format="auto",
        original_filename=us.filename,
        file_size_bytes=us.file_size,
        title=os.path.splitext(us.filename)[0],
        status="pending",
        source_hash=source_hash,
        s3_key=us.s3_key,
        tenant_id=upload_tenant_id,
    )
    session.add(doc)
    await session.flush()

    new_s3_key = s3_key_for_document(doc.id, us.filename)
    if new_s3_key != us.s3_key:
        from app.s3 import _get_client
        client = _get_client()
        client.copy_object(
            Bucket=settings.s3_bucket,
            CopySource={"Bucket": settings.s3_bucket, "Key": us.s3_key},
            Key=new_s3_key,
        )
        doc.s3_key = new_s3_key

    await session.commit()

    from app.celery_app import ingest_document_task
    ingest_document_task.delay(doc.id)

    return doc.id


def _save_sha256(hasher) -> str:
    """Serialize a resumable SHA-256 hasher via pickle so it can be resumed across requests."""
    import pickle
    return base64.b64encode(pickle.dumps(hasher)).decode("ascii")


def _load_sha256(state: str):
    """Deserialize a SHA-256 hasher from a previously saved state."""
    import pickle
    if not state:
        return resumable_sha256()
    return pickle.loads(base64.b64decode(state))
