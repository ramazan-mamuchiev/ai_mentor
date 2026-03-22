"""Unit tests for search deduplication logic."""

from app.search.service import _deduplicate_chunks


def _make_chunk(heading: str, content: str, similarity: float = 0.9, doc_title: str = "Doc"):
    return {
        "content": content,
        "heading_path": heading,
        "heading_level": 2,
        "token_count": len(content.split()),
        "doc_title": doc_title,
        "product_name": "Product",
        "manufacturer": "Mfg",
        "firmware_version": "1.0",
        "similarity": similarity,
    }


class TestDeduplicateChunks:
    def test_no_duplicates_returns_all(self):
        chunks = [
            _make_chunk("Auth", "Use HMAC for auth", 0.95),
            _make_chunk("Setup", "Install the SDK", 0.90),
            _make_chunk("API", "Call POST /api/login", 0.85),
        ]
        result = _deduplicate_chunks(chunks, limit=5)
        assert len(result) == 3

    def test_removes_exact_duplicates(self):
        chunks = [
            _make_chunk("Auth", "Use HMAC for auth", 0.95, "Doc v1"),
            _make_chunk("Auth", "Use HMAC for auth", 0.94, "Doc v2"),
            _make_chunk("Setup", "Install the SDK", 0.90),
        ]
        result = _deduplicate_chunks(chunks, limit=5)
        assert len(result) == 2
        assert result[0]["similarity"] == 0.95
        assert result[1]["heading_path"] == "Setup"

    def test_respects_limit(self):
        chunks = [_make_chunk(f"H{i}", f"Content {i}", 0.9 - i * 0.01) for i in range(10)]
        result = _deduplicate_chunks(chunks, limit=3)
        assert len(result) == 3

    def test_keeps_first_occurrence_highest_similarity(self):
        chunks = [
            _make_chunk("Signature", "Calculate HMAC-SHA256", 0.92, "Upload 1"),
            _make_chunk("Signature", "Calculate HMAC-SHA256", 0.91, "Upload 2"),
            _make_chunk("Signature", "Calculate HMAC-SHA256", 0.90, "Upload 3"),
        ]
        result = _deduplicate_chunks(chunks, limit=5)
        assert len(result) == 1
        assert result[0]["similarity"] == 0.92

    def test_empty_input(self):
        result = _deduplicate_chunks([], limit=5)
        assert result == []

    def test_different_content_same_heading_kept(self):
        chunks = [
            _make_chunk("Note", "First note about auth", 0.90),
            _make_chunk("Note", "Second note about setup", 0.85),
        ]
        result = _deduplicate_chunks(chunks, limit=5)
        assert len(result) == 2

    def test_dedup_uses_full_content_hash(self):
        """After switching to SHA-256 of full content, chunks with same prefix but
        different suffixes are NOT treated as duplicates."""
        base = "A" * 200
        chunks = [
            _make_chunk("H1", base + " extra1", 0.95),
            _make_chunk("H1", base + " extra2", 0.90),
        ]
        result = _deduplicate_chunks(chunks, limit=5)
        assert len(result) == 2

    def test_truly_identical_content_deduped(self):
        same_content = "A" * 200 + " same_suffix"
        chunks = [
            _make_chunk("H1", same_content, 0.95, "Doc v1"),
            _make_chunk("H1", same_content, 0.90, "Doc v2"),
        ]
        result = _deduplicate_chunks(chunks, limit=5)
        assert len(result) == 1
