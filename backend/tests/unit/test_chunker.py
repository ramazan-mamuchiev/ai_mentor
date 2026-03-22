"""Unit tests for app.ingestion.chunker."""

from app.ingestion.chunker import (
    ChunkData,
    Section,
    _estimate_tokens,
    _merge_small_chunks,
    _parent_heading,
    _split_into_blocks,
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
        text = " ".join(["word"] * 100)
        result = _estimate_tokens(text)
        assert result == 130

    def test_single_word(self):
        assert _estimate_tokens("hello") == 1


class TestSplitIntoBlocks:
    def test_plain_paragraphs(self):
        text = "Para one.\n\nPara two.\n\nPara three."
        blocks = _split_into_blocks(text)
        assert len(blocks) == 3
        assert blocks[0] == "Para one."
        assert blocks[1] == "Para two."
        assert blocks[2] == "Para three."

    def test_code_block_preserved(self):
        text = "Before.\n\n```python\ndef foo():\n    pass\n```\n\nAfter."
        blocks = _split_into_blocks(text)
        assert any("```python" in b and "def foo" in b for b in blocks)
        assert "Before." in blocks
        assert "After." in blocks

    def test_table_preserved(self):
        text = "Before.\n\n| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n\nAfter."
        blocks = _split_into_blocks(text)
        table_blocks = [b for b in blocks if "|" in b and "---" in b]
        assert len(table_blocks) == 1
        assert "| 1 | 2 |" in table_blocks[0]
        assert "| 3 | 4 |" in table_blocks[0]

    def test_code_block_inside_table_region(self):
        text = "```\n| A | B |\n|---|---|\n| 1 | 2 |\n```"
        blocks = _split_into_blocks(text)
        assert len(blocks) == 1
        assert "```" in blocks[0]

    def test_empty_text(self):
        assert _split_into_blocks("") == []
        assert _split_into_blocks("   ") == []

    def test_multiple_code_blocks(self):
        text = "```js\nvar x = 1;\n```\n\nText.\n\n```py\ny = 2\n```"
        blocks = _split_into_blocks(text)
        code_blocks = [b for b in blocks if "```" in b]
        assert len(code_blocks) == 2


class TestSplitText:
    def test_short_text_no_split(self):
        text = "Short paragraph."
        pieces = _split_text(text, max_tokens=500)
        assert len(pieces) == 1
        assert pieces[0] == text

    def test_split_at_paragraph_boundary(self):
        para1 = " ".join(["word"] * 200)
        para2 = " ".join(["other"] * 200)
        text = f"{para1}\n\n{para2}"
        pieces = _split_text(text, max_tokens=150)
        assert len(pieces) == 2
        assert "word" in pieces[0]
        assert "other" in pieces[1]

    def test_single_huge_paragraph(self):
        text = " ".join(["word"] * 1000)
        pieces = _split_text(text, max_tokens=100)
        assert len(pieces) == 1

    def test_overlap_between_pieces(self):
        paras = [f"Paragraph {i}. " + " ".join(["x"] * 50) for i in range(6)]
        text = "\n\n".join(paras)
        pieces = _split_text(text, max_tokens=100)
        if len(pieces) > 1:
            last_blocks_of_first = pieces[0].split("\n\n")[-2:]
            for block in last_blocks_of_first:
                if block.strip():
                    assert block.strip() in pieces[1]

    def test_code_block_not_split(self):
        code = "```python\n" + "\n".join(f"line_{i} = {i}" for i in range(20)) + "\n```"
        text = f"Intro.\n\n{code}\n\nOutro."
        pieces = _split_text(text, max_tokens=50)
        for piece in pieces:
            if "```python" in piece:
                assert "```" in piece[piece.index("```python") + 10:]
                break

    def test_table_not_split(self):
        rows = "\n".join(f"| item{i} | val{i} |" for i in range(10))
        table = f"| Name | Value |\n|------|-------|\n{rows}"
        text = f"Before.\n\n{table}\n\nAfter."
        pieces = _split_text(text, max_tokens=30)
        for piece in pieces:
            if "|---" in piece:
                assert "| item0" in piece
                assert "| item9" in piece
                break


class TestChunkSections:
    def test_empty_sections(self):
        assert chunk_sections([]) == []

    def test_single_small_section(self):
        sections = [Section(heading_path="Intro", heading_level=1, content="Hello world.")]
        chunks = chunk_sections(sections, max_tokens=1500, min_tokens=5)
        assert len(chunks) == 1
        assert chunks[0].heading_path == "Intro"
        assert chunks[0].content == "Hello world."
        assert chunks[0].parent_content is None

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
        big_content = "\n\n".join(f"Paragraph {i}. " + " ".join(["x"] * 50) for i in range(10))
        sections = [Section(heading_path="Big", heading_level=1, content=big_content)]
        chunks = chunk_sections(sections, max_tokens=100, min_tokens=5)
        assert len(chunks) > 1
        assert all("Big" in c.heading_path for c in chunks)
        assert "(part 1)" in chunks[0].heading_path

    def test_heading_path_preserved_on_split(self):
        content = "\n\n".join(f"Para {i}. " + " ".join(["y"] * 50) for i in range(5))
        sections = [Section(heading_path="API > Doors > Open", heading_level=3, content=content)]
        chunks = chunk_sections(sections, max_tokens=100, min_tokens=5)
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

    def test_parent_content_set_on_split(self):
        big_content = "\n\n".join(f"Paragraph {i}. " + " ".join(["z"] * 50) for i in range(10))
        sections = [Section(heading_path="Big", heading_level=1, content=big_content)]
        chunks = chunk_sections(sections, max_tokens=100, min_tokens=5)
        assert len(chunks) > 1
        for c in chunks:
            assert c.parent_content is not None
            assert c.parent_content == big_content

    def test_parent_content_none_for_small_section(self):
        sections = [Section(heading_path="Small", heading_level=1, content="Short text.")]
        chunks = chunk_sections(sections, max_tokens=1500, min_tokens=5)
        assert len(chunks) == 1
        assert chunks[0].parent_content is None


class TestMergeSmallChunks:
    def test_empty(self):
        assert _merge_small_chunks([], min_tokens=100, max_tokens=1500) == []

    def test_single_chunk(self):
        c = ChunkData(heading_path="A", heading_level=1, content="x", token_count=10)
        result = _merge_small_chunks([c], min_tokens=100, max_tokens=1500)
        assert len(result) == 1

    def test_parent_content_preserved_on_merge(self):
        c1 = ChunkData(
            heading_path="Parent > A", heading_level=2,
            content="tiny", token_count=5,
            parent_content="Full parent section.",
        )
        c2 = ChunkData(
            heading_path="Parent > B", heading_level=2,
            content="also tiny", token_count=5,
        )
        result = _merge_small_chunks([c1, c2], min_tokens=100, max_tokens=1500)
        assert len(result) == 1
        assert result[0].parent_content == "Full parent section."

    def test_parent_content_from_second_chunk(self):
        c1 = ChunkData(
            heading_path="Parent > A", heading_level=2,
            content="tiny", token_count=5,
        )
        c2 = ChunkData(
            heading_path="Parent > B", heading_level=2,
            content="also tiny", token_count=5,
            parent_content="From second chunk.",
        )
        result = _merge_small_chunks([c1, c2], min_tokens=100, max_tokens=1500)
        assert len(result) == 1
        assert result[0].parent_content == "From second chunk."

    def test_merged_heading_path_combines_both(self):
        """When merging two chunks with different heading_paths, both should be preserved."""
        c1 = ChunkData(
            heading_path="Parent > A", heading_level=2,
            content="tiny", token_count=5,
        )
        c2 = ChunkData(
            heading_path="Parent > B", heading_level=2,
            content="also tiny", token_count=5,
        )
        result = _merge_small_chunks([c1, c2], min_tokens=100, max_tokens=1500)
        assert len(result) == 1
        assert "Parent > A" in result[0].heading_path
        assert "Parent > B" in result[0].heading_path

    def test_merged_same_heading_path_not_duplicated(self):
        """When merging chunks with identical heading_path, no duplication."""
        c1 = ChunkData(
            heading_path="Parent > A", heading_level=2,
            content="tiny", token_count=5,
        )
        c2 = ChunkData(
            heading_path="Parent > A", heading_level=2,
            content="also tiny", token_count=5,
        )
        result = _merge_small_chunks([c1, c2], min_tokens=100, max_tokens=1500)
        assert len(result) == 1
        assert result[0].heading_path == "Parent > A"

    def test_merged_token_count_recalculated(self):
        """Token count after merge should be recalculated, not just summed."""
        c1 = ChunkData(
            heading_path="Parent > A", heading_level=2,
            content="hello world", token_count=5,
        )
        c2 = ChunkData(
            heading_path="Parent > B", heading_level=2,
            content="foo bar", token_count=5,
        )
        result = _merge_small_chunks([c1, c2], min_tokens=100, max_tokens=1500)
        assert len(result) == 1
        expected = _estimate_tokens("hello world\n\nfoo bar")
        assert result[0].token_count == expected


class TestParentHeading:
    def test_no_parent(self):
        assert _parent_heading("Root") == "Root"

    def test_one_level(self):
        assert _parent_heading("Root > Child") == "Root"

    def test_two_levels(self):
        assert _parent_heading("A > B > C") == "A > B"

    def test_merged_heading_path_with_plus(self):
        """_parent_heading should handle merged paths like 'Parent > A + Parent > B'."""
        assert _parent_heading("Parent > A + Parent > B") == "Parent"

    def test_merged_heading_path_single_level(self):
        """Merged path with no parent should return the base."""
        assert _parent_heading("A + B") == "A"

    def test_merged_heading_path_deep(self):
        assert _parent_heading("A > B > C + A > B > D") == "A > B"
