"""Unit tests for app.ingestion.chunker."""

from app.ingestion.chunker import (
    ChunkData,
    Section,
    _estimate_tokens,
    _merge_small_chunks,
    _parent_heading,
    _split_text,
    chunk_sections,
)


class TestEstimateTokens:
    def test_empty_string(self):
        assert _estimate_tokens("") == 1

    def test_short_text(self):
        result = _estimate_tokens("hello world")
        assert result >= 1

    def test_longer_text(self):
        text = "a" * 300
        result = _estimate_tokens(text)
        assert result == 100


class TestSplitText:
    def test_short_text_no_split(self):
        text = "Short paragraph."
        pieces = _split_text(text, max_tokens=500)
        assert len(pieces) == 1
        assert pieces[0] == text

    def test_split_at_paragraph_boundary(self):
        para1 = "A" * 300
        para2 = "B" * 300
        text = f"{para1}\n\n{para2}"
        pieces = _split_text(text, max_tokens=150)
        assert len(pieces) == 2
        assert para1 in pieces[0]
        assert para2 in pieces[1]

    def test_single_huge_paragraph(self):
        text = "word " * 1000
        pieces = _split_text(text, max_tokens=100)
        assert len(pieces) == 1


class TestChunkSections:
    def test_empty_sections(self):
        assert chunk_sections([]) == []

    def test_single_small_section(self):
        sections = [Section(heading_path="Intro", heading_level=1, content="Hello world.")]
        chunks = chunk_sections(sections, max_tokens=1500, min_tokens=5)
        assert len(chunks) == 1
        assert chunks[0].heading_path == "Intro"
        assert chunks[0].content == "Hello world."

    def test_empty_content_skipped(self):
        sections = [
            Section(heading_path="A", heading_level=1, content="Real content."),
            Section(heading_path="B", heading_level=1, content="   "),
            Section(heading_path="C", heading_level=1, content="More content."),
        ]
        chunks = chunk_sections(sections, max_tokens=1500, min_tokens=5)
        paths = [c.heading_path for c in chunks]
        assert "B" not in paths
        assert "A" in paths
        assert "C" in paths

    def test_large_section_splits(self):
        big_content = "\n\n".join(f"Paragraph {i}. " + "x" * 200 for i in range(10))
        sections = [Section(heading_path="Big", heading_level=1, content=big_content)]
        chunks = chunk_sections(sections, max_tokens=300, min_tokens=50)
        assert len(chunks) > 1
        assert all("Big" in c.heading_path for c in chunks)
        assert "(part 1)" in chunks[0].heading_path

    def test_heading_path_preserved_on_split(self):
        content = "\n\n".join(f"Para {i}. " + "y" * 200 for i in range(5))
        sections = [Section(heading_path="API > Doors > Open", heading_level=3, content=content)]
        chunks = chunk_sections(sections, max_tokens=300, min_tokens=50)
        assert len(chunks) > 1
        for c in chunks:
            assert c.heading_path.startswith("API > Doors > Open")
            assert c.heading_level == 3

    def test_small_sections_merged(self):
        sections = [
            Section(heading_path="Parent > A", heading_level=2, content="tiny"),
            Section(heading_path="Parent > B", heading_level=2, content="also tiny"),
        ]
        chunks = chunk_sections(sections, max_tokens=1500, min_tokens=100)
        assert len(chunks) == 1
        assert "tiny" in chunks[0].content
        assert "also tiny" in chunks[0].content

    def test_different_parents_not_merged(self):
        sections = [
            Section(heading_path="Chapter1 > A", heading_level=2, content="tiny"),
            Section(heading_path="Chapter2 > B", heading_level=2, content="also tiny"),
        ]
        chunks = chunk_sections(sections, max_tokens=1500, min_tokens=100)
        assert len(chunks) == 2


class TestMergeSmallChunks:
    def test_empty(self):
        assert _merge_small_chunks([], min_tokens=100, max_tokens=1500) == []

    def test_single_chunk(self):
        c = ChunkData(heading_path="A", heading_level=1, content="x", token_count=10)
        result = _merge_small_chunks([c], min_tokens=100, max_tokens=1500)
        assert len(result) == 1


class TestParentHeading:
    def test_no_parent(self):
        assert _parent_heading("Root") == "Root"

    def test_one_level(self):
        assert _parent_heading("Root > Child") == "Root"

    def test_two_levels(self):
        assert _parent_heading("A > B > C") == "A > B"
