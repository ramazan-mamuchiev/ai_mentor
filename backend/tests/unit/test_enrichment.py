"""Unit tests for embedding enrichment (enrich_for_embedding)."""

from app.ingestion.chunker import ChunkData
from app.ingestion.pipeline import enrich_for_embedding, _replace_generic_headings


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

    def test_all_headings_enriched(self):
        """All heading_paths are now included in enrichment (no skip for Document/Preamble)."""
        chunks = [
            ChunkData(heading_path="MyDoc", heading_level=1, content="Text.", token_count=5),
            ChunkData(heading_path="MyDoc > Preamble", heading_level=0, content="Preamble text.", token_count=5),
        ]
        enriched = enrich_for_embedding(chunks)
        assert enriched[0].startswith("[MyDoc]")
        assert enriched[1].startswith("[MyDoc > Preamble]")

    def test_empty_heading_path_no_prefix(self):
        """Chunks with empty heading_path get no prefix."""
        chunks = [
            ChunkData(heading_path="", heading_level=1, content="Some text.", token_count=5),
        ]
        enriched = enrich_for_embedding(chunks)
        assert enriched[0] == "Some text."

    def test_empty_list(self):
        assert enrich_for_embedding([]) == []

    def test_multiple_chunks(self):
        chunks = [
            ChunkData(heading_path="A > B", heading_level=2, content="Content 1", token_count=5),
            ChunkData(heading_path="MyDoc", heading_level=1, content="Content 2", token_count=5),
            ChunkData(heading_path="C > D > E", heading_level=3, content="Content 3", token_count=5),
        ]
        enriched = enrich_for_embedding(chunks)
        assert enriched[0] == "[A > B]\nContent 1"
        assert enriched[1] == "[MyDoc]\nContent 2"
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

    def test_long_text_truncated_preserving_heading(self, caplog):
        """Truncation must preserve the [heading_path] prefix intact."""
        import logging
        long_content = " ".join(["word"] * 600)
        heading = "Very > Long > Path > To > Section"
        chunks = [
            ChunkData(
                heading_path=heading,
                heading_level=5,
                content=long_content,
                token_count=780,
            ),
        ]
        with caplog.at_level(logging.WARNING):
            enriched = enrich_for_embedding(chunks)
        assert len(enriched) == 1
        assert enriched[0].startswith(f"[{heading}]\n")
        from app.ingestion.chunker import _estimate_tokens
        from app.ingestion.pipeline import MAX_EMBEDDING_TOKENS
        assert _estimate_tokens(enriched[0]) <= MAX_EMBEDDING_TOKENS + 50

    def test_list_markers_cleaned_in_embedding(self):
        """List markers should be stripped from chunk content before embedding."""
        chunks = [
            ChunkData(
                heading_path="Setup",
                heading_level=1,
                content="- Install Python\n- Run tests\n1. First step",
                token_count=10,
            ),
        ]
        enriched = enrich_for_embedding(chunks)
        assert "- " not in enriched[0].replace("[Setup]", "")
        assert "1." not in enriched[0]
        assert "Install Python" in enriched[0]


class TestReplaceGenericHeadings:
    def test_document_replaced_with_title(self):
        from app.ingestion.chunker import Section
        sections = [Section(heading_path="Document", heading_level=1, content="Some text.")]
        _replace_generic_headings(sections, "my-api-guide")
        assert sections[0].heading_path == "my-api-guide"

    def test_preamble_replaced_with_title_prefix(self):
        from app.ingestion.chunker import Section
        sections = [Section(heading_path="Preamble", heading_level=0, content="Intro.")]
        _replace_generic_headings(sections, "my-api-guide")
        assert sections[0].heading_path == "my-api-guide > Preamble"

    def test_normal_headings_unchanged(self):
        from app.ingestion.chunker import Section
        sections = [
            Section(heading_path="API > Auth", heading_level=2, content="Auth content."),
            Section(heading_path="Setup", heading_level=1, content="Setup content."),
        ]
        _replace_generic_headings(sections, "my-doc")
        assert sections[0].heading_path == "API > Auth"
        assert sections[1].heading_path == "Setup"

    def test_both_document_and_preamble(self):
        from app.ingestion.chunker import Section
        sections = [
            Section(heading_path="Preamble", heading_level=0, content="Intro."),
            Section(heading_path="API > Doors", heading_level=2, content="Doors."),
            Section(heading_path="Document", heading_level=1, content="Fallback."),
        ]
        _replace_generic_headings(sections, "zkbio")
        assert sections[0].heading_path == "zkbio > Preamble"
        assert sections[1].heading_path == "API > Doors"
        assert sections[2].heading_path == "zkbio"
