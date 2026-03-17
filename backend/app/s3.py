"""S3/MinIO client for storing original document files."""

import logging
from io import BytesIO

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


def check_health() -> bool:
    """Check if S3 is reachable."""
    try:
        _get_client().head_bucket(Bucket=settings.s3_bucket)
        return True
    except Exception:
        return False
