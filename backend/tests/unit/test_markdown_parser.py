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

    def test_h4_heading_parsed(self):
        text = """# API
## Endpoints
### GET /doors
#### Parameters
The timeout parameter.
#### Response
Returns JSON.
"""
        sections = parse_markdown(text)
        paths = [s.heading_path for s in sections]
        assert "API > Endpoints > GET /doors > Parameters" in paths
        assert "API > Endpoints > GET /doors > Response" in paths

    def test_h5_and_h6_headings(self):
        text = """# Top
## Mid
### Sub
#### Detail
##### Fine
Content at H5.
###### Finest
Content at H6.
"""
        sections = parse_markdown(text)
        paths = [s.heading_path for s in sections]
        levels = {s.heading_path: s.heading_level for s in sections}
        assert any("Fine" in p for p in paths)
        assert any("Finest" in p for p in paths)
        fine_section = [s for s in sections if s.heading_path.endswith("Fine")]
        assert fine_section[0].heading_level == 5
        finest_section = [s for s in sections if s.heading_path.endswith("Finest")]
        assert finest_section[0].heading_level == 6

    def test_h4_resets_properly(self):
        text = """# API
### Method A
#### Param X
Details X.
### Method B
#### Param Y
Details Y.
"""
        sections = parse_markdown(text)
        paths = [s.heading_path for s in sections]
        assert any("Method A > Param X" in p for p in paths)
        assert any("Method B > Param Y" in p for p in paths)
        assert not any("Method A > Param Y" in p for p in paths)

    def test_heading_markdown_formatting_cleaned(self):
        text = """# **Bold Title**
Content under bold.

## `GET /api/doors`
Endpoint docs.

## [Authentication](https://example.com)
Auth docs.
"""
        sections = parse_markdown(text)
        paths = [s.heading_path for s in sections]
        assert "Bold Title" in paths
        assert "**Bold Title**" not in paths
        assert any("GET /api/doors" in p for p in paths)
        assert not any("`" in p for p in paths)
        assert any("Authentication" in p for p in paths)
        assert not any("https://example.com" in p for p in paths)

    def test_unicode_normalization(self):
        text = "# \uff21\uff30\uff29\n\uff32\uff45\uff46\uff45\uff52\uff45\uff4e\uff43\uff45"
        sections = parse_markdown(text)
        assert sections[0].heading_path == "API"
        assert "Reference" in sections[0].content

    def test_headings_inside_code_blocks_ignored(self):
        """Headings inside fenced code blocks must NOT be treated as real headings."""
        text = """# Real Heading
Some intro text.

```bash
# This is a comment, not a heading
echo "hello"
## Another comment
grep -r "pattern" .
```

More content after code block.

## Second Real Heading
Content here.
"""
        sections = parse_markdown(text)
        paths = [s.heading_path for s in sections]
        assert "Real Heading" in paths
        assert "Real Heading > Second Real Heading" in paths
        assert not any("This is a comment" in p for p in paths)
        assert not any("Another comment" in p for p in paths)
        assert len(sections) == 2

    def test_headings_between_code_blocks(self):
        """Headings between code blocks should be parsed normally."""
        text = """# Top

```python
# comment in code
x = 1
```

## Middle Heading
Real content.

```js
// another code block
# not a heading
```

## Last Heading
Final content.
"""
        sections = parse_markdown(text)
        paths = [s.heading_path for s in sections]
        assert "Top" in paths
        assert "Top > Middle Heading" in paths
        assert "Top > Last Heading" in paths
        assert not any("comment in code" in p for p in paths)

    def test_code_block_only_document(self):
        """Document with only a code block and no real headings."""
        text = """```yaml
# This looks like a heading but is YAML comment
key: value
## Also YAML comment
nested:
  - item
```"""
        sections = parse_markdown(text)
        assert len(sections) == 1
        assert sections[0].heading_path == "Document"
        assert "key: value" in sections[0].content

    def test_unclosed_code_block(self):
        """Unclosed code block should protect everything after opening fence."""
        text = """# Real Heading
Some content.

```python
# This is inside unclosed code block
def foo():
    pass
## Also inside unclosed block
"""
        sections = parse_markdown(text)
        paths = [s.heading_path for s in sections]
        assert "Real Heading" in paths
        assert not any("This is inside" in p for p in paths)
        assert not any("Also inside" in p for p in paths)

    def test_unclosed_code_block_no_headings_after(self):
        """Document where unclosed code block is the only content after heading."""
        text = """# Setup

```bash
# install deps
apt-get install python3
"""
        sections = parse_markdown(text)
        assert len(sections) == 1
        assert sections[0].heading_path == "Setup"
