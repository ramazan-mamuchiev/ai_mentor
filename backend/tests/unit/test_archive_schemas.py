"""Unit tests for archive ingest schemas."""

import pytest

from app.documents.schemas import ArchiveFileResult, ArchiveIngestResponse


class TestArchiveFileResult:
    def test_pending_result(self):
        r = ArchiveFileResult(
            filename="api.proto",
            status="pending",
            document_id=42,
            task_id="abc-123",
            message="Queued for processing",
        )
        assert r.filename == "api.proto"
        assert r.status == "pending"
        assert r.document_id == 42

    def test_skipped_result(self):
        r = ArchiveFileResult(
            filename="dup.md",
            status="skipped",
            document_id=10,
            message="Duplicate of «API Guide» (id=10)",
        )
        assert r.status == "skipped"
        assert r.task_id is None

    def test_error_result(self):
        r = ArchiveFileResult(
            filename="bad.bin",
            status="error",
            message="Unsupported format",
        )
        assert r.status == "error"
        assert r.document_id is None


class TestArchiveIngestResponse:
    def test_full_response(self):
        resp = ArchiveIngestResponse(
            product_name="AxxonOne",
            total_files=3,
            accepted=2,
            skipped=1,
            errors=0,
            files=[
                ArchiveFileResult(filename="a.md", status="pending", document_id=1, task_id="t1"),
                ArchiveFileResult(filename="b.proto", status="pending", document_id=2, task_id="t2"),
                ArchiveFileResult(filename="c.pdf", status="skipped", document_id=5, message="dup"),
            ],
        )
        assert resp.product_name == "AxxonOne"
        assert resp.total_files == 3
        assert resp.accepted == 2
        assert resp.skipped == 1
        assert len(resp.files) == 3

    def test_empty_archive(self):
        resp = ArchiveIngestResponse(
            product_name="Empty",
            total_files=0,
            accepted=0,
            skipped=0,
            errors=0,
            files=[],
        )
        assert resp.total_files == 0
        assert resp.files == []
