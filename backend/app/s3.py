"""S3/MinIO client for storing original document files."""
from __future__ import annotations

import logging
from io import BytesIO
from typing import Callable

import boto3
from botocore.exceptions import ClientError

from app.config import settings

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name="us-east-1",
        )
    return _client


def ensure_bucket():
    """Create the S3 bucket if it does not exist."""
    client = _get_client()
    try:
        client.head_bucket(Bucket=settings.s3_bucket)
        logger.info("S3 bucket exists", extra={"bucket": settings.s3_bucket})
    except ClientError:
        client.create_bucket(Bucket=settings.s3_bucket)
        logger.info("S3 bucket created", extra={"bucket": settings.s3_bucket})


def upload_file(key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    """Upload bytes to S3. Returns the key."""
    client = _get_client()
    client.put_object(
        Bucket=settings.s3_bucket,
        Key=key,
        Body=data,
        ContentType=content_type,
    )
    logger.debug("S3 upload", extra={"key": key, "size": len(data)})
    return key


def download_file(key: str) -> bytes:
    """Download file from S3 as bytes."""
    client = _get_client()
    response = client.get_object(Bucket=settings.s3_bucket, Key=key)
    data = response["Body"].read()
    logger.debug("S3 download", extra={"key": key, "size": len(data)})
    return data


def download_file_to_path(
    key: str,
    dest_path: str,
    progress_callback: Callable[[float], None] | None = None,
) -> int:
    """Stream-download file from S3 directly to disk with progress callback.

    Returns the total number of bytes written.
    progress_callback receives a fraction in [0..1].
    """
    client = _get_client()
    head = client.head_object(Bucket=settings.s3_bucket, Key=key)
    total_size = head["ContentLength"]

    response = client.get_object(Bucket=settings.s3_bucket, Key=key)
    body = response["Body"]

    downloaded = 0
    chunk_size = 4 * 1024 * 1024  # 4 MB
    with open(dest_path, "wb") as f:
        while True:
            chunk = body.read(chunk_size)
            if not chunk:
                break
            f.write(chunk)
            downloaded += len(chunk)
            if progress_callback is not None and total_size > 0:
                progress_callback(min(downloaded / total_size, 1.0))

    logger.debug("S3 stream download", extra={"key": key, "size": downloaded})
    return downloaded


def generate_presigned_url(key: str, expires_in: int = 900) -> str:
    """Generate a presigned download URL (default 15 min)."""
    client = _get_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": key},
        ExpiresIn=expires_in,
    )


def delete_file(key: str):
    """Delete a file from S3."""
    client = _get_client()
    client.delete_object(Bucket=settings.s3_bucket, Key=key)
    logger.debug("S3 delete", extra={"key": key})


def s3_key_for_document(document_id: int, filename: str) -> str:
    """Build the S3 key for a document's source file."""
    import os
    ext = os.path.splitext(filename)[1].lower() or ".bin"
    return f"documents/{document_id}/source{ext}"


def create_multipart_upload(key: str, content_type: str = "application/octet-stream") -> str:
    """Initiate an S3 multipart upload. Returns the UploadId."""
    client = _get_client()
    resp = client.create_multipart_upload(
        Bucket=settings.s3_bucket,
        Key=key,
        ContentType=content_type,
    )
    upload_id = resp["UploadId"]
    logger.debug("S3 multipart upload created", extra={"key": key, "upload_id": upload_id})
    return upload_id


def upload_part(key: str, upload_id: str, part_number: int, data: bytes) -> str:
    """Upload a single part of a multipart upload. Returns the ETag."""
    client = _get_client()
    resp = client.upload_part(
        Bucket=settings.s3_bucket,
        Key=key,
        UploadId=upload_id,
        PartNumber=part_number,
        Body=data,
    )
    etag = resp["ETag"]
    logger.debug(
        "S3 part uploaded",
        extra={"key": key, "part": part_number, "size": len(data), "etag": etag},
    )
    return etag


def complete_multipart_upload(key: str, upload_id: str, parts: list[dict]) -> None:
    """Complete a multipart upload. `parts` is a list of {"PartNumber": int, "ETag": str}."""
    client = _get_client()
    client.complete_multipart_upload(
        Bucket=settings.s3_bucket,
        Key=key,
        UploadId=upload_id,
        MultipartUpload={"Parts": parts},
    )
    logger.info(
        "S3 multipart upload completed",
        extra={"key": key, "upload_id": upload_id, "parts_count": len(parts)},
    )


def abort_multipart_upload(key: str, upload_id: str) -> None:
    """Abort a multipart upload, cleaning up uploaded parts."""
    client = _get_client()
    try:
        client.abort_multipart_upload(
            Bucket=settings.s3_bucket,
            Key=key,
            UploadId=upload_id,
        )
        logger.info("S3 multipart upload aborted", extra={"key": key, "upload_id": upload_id})
    except ClientError as e:
        logger.warning(
            "S3 abort_multipart_upload failed (may already be completed/aborted)",
            extra={"key": key, "upload_id": upload_id, "error": str(e)},
        )


def s3_key_for_upload(upload_id: str, filename: str) -> str:
    """Build the S3 key for a TUS upload session."""
    import os
    ext = os.path.splitext(filename)[1].lower() or ".bin"
    return f"uploads/{upload_id}/source{ext}"


def check_health() -> bool:
    """Check if S3 is reachable."""
    try:
        _get_client().head_bucket(Bucket=settings.s3_bucket)
        return True
    except Exception:
        return False
