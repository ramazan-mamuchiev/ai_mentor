"""Unit tests for app.ingestion.parsers.markdown."""

from app.ingestion.parsers.markdown import parse_markdown


class TestParseMarkdown:
    def test_empty_text(self):
        assert parse_markdown("") == []
        assert parse_markdown("   ") == []

    def test_no_headings(self):
        text = "Just some plain text\nwith multiple lines."
        sections = parse_markdown(text)
        assert len(sections) == 1
        assert sections[0].heading_path == "Document"
        assert sections[0].heading_level == 1
        assert "plain text" in sections[0].content

    def test_single_h1(self):
        text = "# Overview\nSome content here."
        sections = parse_markdown(text)
        assert len(sections) == 1
        assert sections[0].heading_path == "Overview"
        assert sections[0].heading_level == 1
        assert "Some content" in sections[0].content

    def test_h1_h2_h3_hierarchy(self):
        text = """# Device Guide
Intro text.

## API Reference
API overview.

### GET /doors
Returns list of doors.

### POST /doors/open
Opens a door.

## Configuration
Config section.
"""
        sections = parse_markdown(text)
        paths = [s.heading_path for s in sections]

        assert "Device Guide" in paths
        assert "Device Guide > API Reference" in paths
        assert "Device Guide > API Reference > GET /doors" in paths
        assert "Device Guide > API Reference > POST /doors/open" in paths
        assert "Device Guide > Configuration" in paths

    def test_heading_level_reset(self):
        text = """# Chapter 1
## Section A
Content A.

# Chapter 2
## Section B
Content B.
"""
        sections = parse_markdown(text)
        paths = [s.heading_path for s in sections]
        assert "Chapter 1 > Section A" in paths
        assert "Chapter 2 > Section B" in paths
        assert not any("Chapter 1 > Section B" in p for p in paths)

    def test_empty_sections_skipped(self):
        text = """# Title
## Empty Section
## Section With Content
Real content here.
"""
        sections = parse_markdown(text)
        paths = [s.heading_path for s in sections]
        assert "Title > Empty Section" not in paths
        assert "Title > Section With Content" in paths

    def test_preamble_before_first_heading(self):
        text = """This is preamble text.

# First Heading
Content.
"""
        sections = parse_markdown(text)
        assert sections[0].heading_path == "Preamble"
        assert sections[0].heading_level == 0
        assert "preamble" in sections[0].content

    def test_heading_levels_preserved(self):
        text = """# H1
Content 1.
## H2
Content 2.
### H3
Content 3.
"""
        sections = parse_markdown(text)
        levels = {s.heading_path: s.heading_level for s in sections}
        assert levels["H1"] == 1
        assert levels["H1 > H2"] == 2
        assert levels["H1 > H2 > H3"] == 3

    def test_multiline_content(self):
        text = """# Section
Line 1.

Line 2.

Line 3.
"""
        sections = parse_markdown(text)
        assert len(sections) == 1
        assert "Line 1" in sections[0].content
        assert "Line 3" in sections[0].content
