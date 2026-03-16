"""Integration tests for the ingestion pipeline with real PostgreSQL+pgvector."""

import pytest
from sqlalchemy import select

from app.ingestion.pipeline import ingest_file
from app.models import Chunk, Device, Document, FirmwareVersion


class TestIngestFile:
    async def test_ingest_markdown_creates_records(self, db_session, sample_md_file):
        result = await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            device_name="ZKTeco InBio",
            firmware_version="1.0",
            manufacturer="ZKTeco",
        )

        assert result["status"] == "ok"
        assert result["chunks"] > 0
        assert result["device"] == "ZKTeco InBio"
        assert result["format"] == "markdown"

        device = (await db_session.execute(
            select(Device).where(Device.name == "ZKTeco InBio")
        )).scalar_one()
        assert device.manufacturer == "ZKTeco"

        fw = (await db_session.execute(
            select(FirmwareVersion).where(
                FirmwareVersion.device_id == device.id,
                FirmwareVersion.version == "1.0",
            )
        )).scalar_one()
        assert fw is not None

        doc = (await db_session.execute(
            select(Document).where(Document.device_id == device.id)
        )).scalar_one()
        assert doc.status == "ready"
        assert doc.total_chunks == result["chunks"]

    async def test_chunks_have_sequential_index(self, db_session, sample_md_file):
        result = await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            device_name="TestDevice",
            firmware_version="1.0",
        )

        chunks = (await db_session.execute(
            select(Chunk).order_by(Chunk.chunk_index)
        )).scalars().all()

        indices = [c.chunk_index for c in chunks]
        assert indices == list(range(len(chunks)))

    async def test_chunks_have_embeddings(self, db_session, sample_md_file):
        await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            device_name="TestDevice",
            firmware_version="1.0",
        )

        chunks = (await db_session.execute(select(Chunk))).scalars().all()
        for chunk in chunks:
            assert chunk.embedding is not None
            assert len(chunk.embedding) == 1536

    async def test_duplicate_ingest_skipped(self, db_session, sample_md_file):
        r1 = await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            device_name="TestDevice",
            firmware_version="1.0",
        )
        assert r1["status"] == "ok"

        r2 = await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            device_name="TestDevice",
            firmware_version="1.0",
        )
        assert r2["status"] == "skipped"

    async def test_new_firmware_creates_new_document(self, db_session, sample_md_file):
        r1 = await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            device_name="TestDevice",
            firmware_version="1.0",
        )
        r2 = await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            device_name="TestDevice",
            firmware_version="2.0",
        )
        assert r1["status"] == "ok"
        assert r2["status"] == "ok"

        devices = (await db_session.execute(select(Device))).scalars().all()
        assert len(devices) == 1

        docs = (await db_session.execute(select(Document))).scalars().all()
        assert len(docs) == 2

    async def test_file_not_found_error(self, db_session):
        result = await ingest_file(
            session=db_session,
            file_path="/nonexistent/path/doc.md",
            device_name="TestDevice",
        )
        assert result["status"] == "error"
        assert "not found" in result["error"].lower() or "File not found" in result["error"]
