"""Unit tests for S3 multipart upload operations.

boto3 is mocked at module level so tests run without AWS/MinIO.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

# Mock boto3 before importing app.s3
_mock_boto3 = MagicMock()
_mock_botocore = MagicMock()
sys.modules.setdefault("boto3", _mock_boto3)
sys.modules.setdefault("botocore", _mock_botocore)
sys.modules.setdefault("botocore.exceptions", _mock_botocore.exceptions)

# Make ClientError a real exception class for tests
class _FakeClientError(Exception):
    pass

_mock_botocore.exceptions.ClientError = _FakeClientError

from app.s3 import (  # noqa: E402
    abort_multipart_upload,
    complete_multipart_upload,
    create_multipart_upload,
    s3_key_for_document,
    s3_key_for_upload,
    upload_part,
)


class TestCreateMultipartUpload:
    @patch("app.s3._get_client")
    def test_returns_upload_id(self, mock_get_client):
        client = MagicMock()
        client.create_multipart_upload.return_value = {"UploadId": "abc123"}
        mock_get_client.return_value = client

        result = create_multipart_upload("uploads/test/source.pdf", "application/pdf")
        assert result == "abc123"
        client.create_multipart_upload.assert_called_once()
        call_kw = client.create_multipart_upload.call_args.kwargs
        assert call_kw["Key"] == "uploads/test/source.pdf"
        assert call_kw["ContentType"] == "application/pdf"

    @patch("app.s3._get_client")
    def test_default_content_type(self, mock_get_client):
        client = MagicMock()
        client.create_multipart_upload.return_value = {"UploadId": "xyz"}
        mock_get_client.return_value = client

        create_multipart_upload("key")
        call_kw = client.create_multipart_upload.call_args.kwargs
        assert call_kw["ContentType"] == "application/octet-stream"


class TestUploadPart:
    @patch("app.s3._get_client")
    def test_returns_etag(self, mock_get_client):
        client = MagicMock()
        client.upload_part.return_value = {"ETag": '"etag123"'}
        mock_get_client.return_value = client

        result = upload_part("key", "upload-id", 1, b"data")
        assert result == '"etag123"'
        client.upload_part.assert_called_once()
        call_kw = client.upload_part.call_args.kwargs
        assert call_kw["PartNumber"] == 1
        assert call_kw["Body"] == b"data"

    @patch("app.s3._get_client")
    def test_correct_part_number(self, mock_get_client):
        client = MagicMock()
        client.upload_part.return_value = {"ETag": '"e"'}
        mock_get_client.return_value = client

        upload_part("k", "u", 42, b"x")
        assert client.upload_part.call_args.kwargs["PartNumber"] == 42


class TestCompleteMultipartUpload:
    @patch("app.s3._get_client")
    def test_sends_parts_list(self, mock_get_client):
        client = MagicMock()
        mock_get_client.return_value = client

        parts = [
            {"PartNumber": 1, "ETag": '"e1"'},
            {"PartNumber": 2, "ETag": '"e2"'},
            {"PartNumber": 3, "ETag": '"e3"'},
        ]
        complete_multipart_upload("key", "uid", parts)
        client.complete_multipart_upload.assert_called_once()
        sent_parts = client.complete_multipart_upload.call_args.kwargs["MultipartUpload"]["Parts"]
        assert sent_parts == parts
        assert len(sent_parts) == 3

    @patch("app.s3._get_client")
    def test_single_part(self, mock_get_client):
        client = MagicMock()
        mock_get_client.return_value = client

        parts = [{"PartNumber": 1, "ETag": '"only"'}]
        complete_multipart_upload("k", "u", parts)
        sent = client.complete_multipart_upload.call_args.kwargs["MultipartUpload"]["Parts"]
        assert len(sent) == 1


class TestAbortMultipartUpload:
    @patch("app.s3._get_client")
    def test_calls_abort(self, mock_get_client):
        client = MagicMock()
        mock_get_client.return_value = client

        abort_multipart_upload("key", "upload-id")
        client.abort_multipart_upload.assert_called_once()

    @patch("app.s3._get_client")
    def test_handles_already_aborted(self, mock_get_client):
        from app.s3 import ClientError as RealClientError

        client = MagicMock()
        client.abort_multipart_upload.side_effect = RealClientError(
            {"Error": {"Code": "NoSuchUpload", "Message": "Not found"}},
            "AbortMultipartUpload",
        )
        mock_get_client.return_value = client

        abort_multipart_upload("key", "upload-id")

    @patch("app.s3._get_client")
    def test_passes_correct_params(self, mock_get_client):
        client = MagicMock()
        mock_get_client.return_value = client

        abort_multipart_upload("my-key", "my-uid")
        call_kw = client.abort_multipart_upload.call_args.kwargs
        assert call_kw["Key"] == "my-key"
        assert call_kw["UploadId"] == "my-uid"


class TestS3KeyForUpload:
    def test_pdf(self):
        assert s3_key_for_upload("abc", "doc.pdf") == "uploads/abc/source.pdf"

    def test_zip(self):
        assert s3_key_for_upload("abc", "archive.zip") == "uploads/abc/source.zip"

    def test_no_extension(self):
        assert s3_key_for_upload("abc", "noext") == "uploads/abc/source.bin"

    def test_uppercase_extension(self):
        assert s3_key_for_upload("abc", "DOC.PDF") == "uploads/abc/source.pdf"

    def test_tar_gz(self):
        assert s3_key_for_upload("abc", "data.tar.gz") == "uploads/abc/source.gz"

    def test_7z(self):
        assert s3_key_for_upload("abc", "data.7z") == "uploads/abc/source.7z"


class TestS3KeyForDocument:
    def test_basic(self):
        assert s3_key_for_document(123, "report.pdf") == "documents/123/source.pdf"

    def test_no_extension(self):
        assert s3_key_for_document(1, "noext") == "documents/1/source.bin"
