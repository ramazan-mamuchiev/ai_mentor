"""Unit tests for S3 client module."""

import pytest
from unittest.mock import MagicMock, patch

# Heavy deps (celery, boto3, structlog) are mocked in tests/conftest.py
from app.s3 import s3_key_for_document


class TestS3KeyForDocument:
    def test_pdf_extension(self):
        key = s3_key_for_document(42, "manual.pdf")
        assert key == "documents/42/source.pdf"

    def test_md_extension(self):
        key = s3_key_for_document(1, "readme.md")
        assert key == "documents/1/source.md"

    def test_yaml_extension(self):
        key = s3_key_for_document(10, "openapi.yaml")
        assert key == "documents/10/source.yaml"

    def test_json_extension(self):
        key = s3_key_for_document(5, "swagger.json")
        assert key == "documents/5/source.json"

    def test_no_extension(self):
        key = s3_key_for_document(7, "noext")
        assert key == "documents/7/source.bin"

    def test_uppercase_extension(self):
        key = s3_key_for_document(3, "Manual.PDF")
        assert key == "documents/3/source.pdf"


class TestUploadFile:
    @patch("app.s3._get_client")
    def test_upload_returns_key(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        from app.s3 import upload_file
        result = upload_file("test/key.pdf", b"data", "application/pdf")

        assert result == "test/key.pdf"
        mock_client.put_object.assert_called_once()


class TestDownloadFile:
    @patch("app.s3._get_client")
    def test_download_returns_bytes(self, mock_get_client):
        mock_client = MagicMock()
        mock_body = MagicMock()
        mock_body.read.return_value = b"file content"
        mock_client.get_object.return_value = {"Body": mock_body}
        mock_get_client.return_value = mock_client

        from app.s3 import download_file
        result = download_file("test/key.pdf")

        assert result == b"file content"


class TestEnsureBucket:
    @patch("app.s3._get_client")
    def test_bucket_exists(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        from app.s3 import ensure_bucket
        ensure_bucket()

        mock_client.head_bucket.assert_called_once()
        mock_client.create_bucket.assert_not_called()

    @patch("app.s3._get_client")
    def test_bucket_created_when_missing(self, mock_get_client):
        from botocore.exceptions import ClientError
        mock_client = MagicMock()
        mock_client.head_bucket.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "Not Found"}}, "HeadBucket"
        )
        mock_get_client.return_value = mock_client

        from app.s3 import ensure_bucket
        ensure_bucket()

        mock_client.create_bucket.assert_called_once()


class TestCheckHealth:
    @patch("app.s3._get_client")
    def test_healthy(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        from app.s3 import check_health
        assert check_health() is True

    @patch("app.s3._get_client")
    def test_unhealthy(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.head_bucket.side_effect = Exception("connection refused")
        mock_get_client.return_value = mock_client

        from app.s3 import check_health
        assert check_health() is False
