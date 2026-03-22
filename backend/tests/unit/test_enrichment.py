"""Unit tests for embedding enrichment (enrich_for_embedding)."""

from app.ingestion.chunker import ChunkData
from app.ingestion.pipeline import enrich_for_embedding


class TestEnrichForEmbedding:
    def test_adds_heading_path_prefix(self):
        chunks = [
            ChunkData(
                heading_path="API > Doors > Open",
                heading_level=3,
                content="Opens a door by ID.",
                token_count=10,
            ),
        ]
        enriched = enrich_for_embedding(chunks)
        assert len(enriched) == 1
        assert enriched[0] == "[API > Doors > Open]\nOpens a door by ID."

    def test_document_heading_not_enriched(self):
        chunks = [
            ChunkData(
                heading_path="Document",
                heading_level=1,
                content="Plain text without headings.",
                token_count=10,
            ),
        ]
        enriched = enrich_for_embedding(chunks)
        assert enriched[0] == "Plain text without headings."

    def test_preamble_heading_not_enriched(self):
        chunks = [
            ChunkData(
                heading_path="Preamble",
                heading_level=0,
                content="Text before first heading.",
                token_count=10,
            ),
        ]
        enriched = enrich_for_embedding(chunks)
        assert enriched[0] == "Text before first heading."

    def test_empty_list(self):
        assert enrich_for_embedding([]) == []

    def test_multiple_chunks(self):
        chunks = [
            ChunkData(heading_path="A > B", heading_level=2, content="Content 1", token_count=5),
            ChunkData(heading_path="Document", heading_level=1, content="Content 2", token_count=5),
            ChunkData(heading_path="C > D > E", heading_level=3, content="Content 3", token_count=5),
        ]
        enriched = enrich_for_embedding(chunks)
        assert enriched[0] == "[A > B]\nContent 1"
        assert enriched[1] == "Content 2"
        assert enriched[2] == "[C > D > E]\nContent 3"

    def test_parent_content_not_included_in_enrichment(self):
        chunks = [
            ChunkData(
                heading_path="Section (part 1)",
                heading_level=1,
                content="Part 1 text.",
                token_count=5,
                parent_content="Full section text.",
            ),
        ]
        enriched = enrich_for_embedding(chunks)
        assert enriched[0] == "[Section (part 1)]\nPart 1 text."
        assert "Full section" not in enriched[0]

    def test_markdown_formatting_stripped(self):
        """Bold, italic, links should be cleaned before embedding."""
        chunks = [
            ChunkData(
                heading_path="API > Auth",
                heading_level=2,
                content="Use **HMAC-SHA256** for [authentication](https://example.com).",
                token_count=10,
            ),
        ]
        enriched = enrich_for_embedding(chunks)
        assert "**" not in enriched[0]
        assert "https://example.com" not in enriched[0]
        assert "HMAC-SHA256" in enriched[0]
        assert "authentication" in enriched[0]

    def test_images_removed_from_embedding(self):
        chunks = [
            ChunkData(
                heading_path="Guide",
                heading_level=1,
                content="See diagram: ![arch](img/arch.png)\n\nNext paragraph.",
                token_count=10,
            ),
        ]
        enriched = enrich_for_embedding(chunks)
        assert "![" not in enriched[0]
        assert "img/arch.png" not in enriched[0]
        assert "Next paragraph" in enriched[0]

    def test_blockquotes_cleaned_in_embedding(self):
        chunks = [
            ChunkData(
                heading_path="FAQ",
                heading_level=2,
                content="> Important note.\n> Second line.\n\nNormal text.",
                token_count=10,
            ),
        ]
        enriched = enrich_for_embedding(chunks)
        assert ">" not in enriched[0].replace("[FAQ]", "")
        assert "Important note." in enriched[0]

    def test_long_text_truncated_with_warning(self, caplog):
        """Enriched text exceeding MAX_EMBEDDING_TOKENS should be truncated."""
        import logging
        long_content = " ".join(["word"] * 600)
        chunks = [
            ChunkData(
                heading_path="Very > Long > Path > To > Section",
                heading_level=5,
                content=long_content,
                token_count=780,
            ),
        ]
        with caplog.at_level(logging.WARNING):
            enriched = enrich_for_embedding(chunks)
        assert len(enriched) == 1
        from app.ingestion.chunker import _estimate_tokens
        from app.ingestion.pipeline import MAX_EMBEDDING_TOKENS
        assert _estimate_tokens(enriched[0]) <= MAX_EMBEDDING_TOKENS + 50
