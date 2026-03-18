"""Integration tests for document deduplication.

Tests the full flow: hash lookup, index existence, and deduplication logic
using a real PostgreSQL database (via testcontainers).
"""

import hashlib

import pytest
from sqlalchemy import select, text

from app.models import Product, Document, FirmwareVersion


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _insert_document(db_session, *, content: bytes, title: str = "Existing Doc",
                           filename: str = "existing.md", product_name: str = "TestDev",
                           manufacturer: str | None = None):
    """Insert a product + firmware + document directly into the DB."""
    mfg = manufacturer or f"Mfg-{product_name}"
    product = Product(name=product_name, manufacturer=mfg, model=product_name)
    db_session.add(product)
    await db_session.flush()

    fw = FirmwareVersion(product_id=product.id, version="1.0")
    db_session.add(fw)
    await db_session.flush()

    source_hash = hashlib.sha256(content).hexdigest()
    doc = Document(
        product_id=product.id,
        firmware_version_id=fw.id,
        format="markdown",
        original_filename=filename,
        file_size_bytes=len(content),
        source_hash=source_hash,
        title=title,
        status="ready",
        total_chunks=5,
    )
    db_session.add(doc)
    await db_session.flush()
    return doc


async def _find_by_hash_sql(db_session, source_hash: str):
    """Replicate _find_by_hash logic using raw SQLAlchemy (avoids router import)."""
    result = await db_session.execute(
        select(Document).where(Document.source_hash == source_hash).limit(1)
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Tests: find-by-hash against real DB
# ---------------------------------------------------------------------------

class TestFindByHashIntegration:
    """Test hash-based document lookup with a real PostgreSQL database."""

    async def test_finds_existing_document_by_hash(self, db_session):
        content = b"# Protocol Documentation\n\nSome content here."
        doc = await _insert_document(db_session, content=content, title="Protocol Guide")

        found = await _find_by_hash_sql(db_session, doc.source_hash)

        assert found is not None
        assert found.id == doc.id
        assert found.title == "Protocol Guide"

    async def test_returns_none_for_unknown_hash(self, db_session):
        found = await _find_by_hash_sql(
            db_session,
            "0000000000000000000000000000000000000000000000000000000000000000",
        )
        assert found is None

    async def test_finds_correct_doc_among_multiple(self, db_session):
        content_a = b"Content A unique bytes"
        content_b = b"Content B different bytes"

        doc_a = await _insert_document(db_session, content=content_a, title="Doc A",
                                       filename="a.md", product_name="DevA")
        doc_b = await _insert_document(db_session, content=content_b, title="Doc B",
                                       filename="b.md", product_name="DevB")

        found_a = await _find_by_hash_sql(db_session, hashlib.sha256(content_a).hexdigest())
        assert found_a is not None
        assert found_a.id == doc_a.id

        found_b = await _find_by_hash_sql(db_session, hashlib.sha256(content_b).hexdigest())
        assert found_b is not None
        assert found_b.id == doc_b.id


# ---------------------------------------------------------------------------
# Tests: source_hash index exists
# ---------------------------------------------------------------------------

class TestSourceHashIndex:
    """Verify the deduplication index is created by schema.sql."""

    async def test_index_exists(self, db_session):
        result = await db_session.execute(
            text(
                "SELECT 1 FROM pg_indexes "
                "WHERE tablename = 'documents' AND indexname = 'idx_documents_source_hash'"
            )
        )
        row = result.scalar_one_or_none()
        assert row is not None, "idx_documents_source_hash index should exist"


# ---------------------------------------------------------------------------
# Tests: SHA-256 hash consistency
# ---------------------------------------------------------------------------

class TestHashConsistency:
    """Verify that identical content always produces the same hash."""

    def test_same_content_same_hash(self):
        content = b"# Identical content\n\nWith some paragraphs."
        h1 = hashlib.sha256(content).hexdigest()
        h2 = hashlib.sha256(content).hexdigest()
        assert h1 == h2

    def test_different_content_different_hash(self):
        h1 = hashlib.sha256(b"Content version 1").hexdigest()
        h2 = hashlib.sha256(b"Content version 2").hexdigest()
        assert h1 != h2

    def test_hash_is_64_hex_chars(self):
        h = hashlib.sha256(b"test").hexdigest()
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


# ---------------------------------------------------------------------------
# Tests: Deduplication flow (DB-level, no HTTP)
# ---------------------------------------------------------------------------

class TestDeduplicationFlow:
    """Test the deduplication logic at the database level."""

    async def test_duplicate_content_detected(self, db_session):
        """Two documents with same content should have same source_hash."""
        content = b"# Shared content between uploads"

        doc1 = await _insert_document(db_session, content=content, title="Upload 1",
                                      filename="file_v1.md", product_name="Dev1")
        doc2 = await _insert_document(db_session, content=content, title="Upload 2",
                                      filename="file_v2.md", product_name="Dev2")

        assert doc1.source_hash == doc2.source_hash

        found = await _find_by_hash_sql(db_session, doc1.source_hash)
        assert found is not None
        assert found.id in (doc1.id, doc2.id)

    async def test_different_content_not_duplicate(self, db_session):
        """Documents with different content should not be detected as duplicates."""
        await _insert_document(db_session, content=b"Content A",
                               title="Doc A", product_name="DevA")

        found = await _find_by_hash_sql(db_session, hashlib.sha256(b"Content B").hexdigest())
        assert found is None

    async def test_empty_hash_not_matched_by_real_content(self, db_session):
        """A document with empty source_hash should not match a real content hash."""
        product = Product(name="EmptyHashDev", manufacturer="Test")
        db_session.add(product)
        await db_session.flush()

        fw = FirmwareVersion(product_id=product.id, version="1.0")
        db_session.add(fw)
        await db_session.flush()

        doc = Document(
            product_id=product.id,
            firmware_version_id=fw.id,
            format="markdown",
            original_filename="old.md",
            file_size_bytes=10,
            source_hash="",
            title="Legacy Doc",
            status="ready",
        )
        db_session.add(doc)
        await db_session.flush()

        real_hash = hashlib.sha256(b"some real content").hexdigest()
        found = await _find_by_hash_sql(db_session, real_hash)
        assert found is None

    async def test_source_hash_stored_correctly(self, db_session):
        """Verify that source_hash is stored and retrievable."""
        content = b"Unique content for hash test"
        expected_hash = hashlib.sha256(content).hexdigest()

        doc = await _insert_document(db_session, content=content, title="Hash Test")

        assert doc.source_hash == expected_hash

        loaded = await db_session.get(Document, doc.id)
        assert loaded is not None
        assert loaded.source_hash == expected_hash
