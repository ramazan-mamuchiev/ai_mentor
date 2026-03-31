"""Unit tests for app.ingestion.parsers.markdown."""

from app.ingestion.parsers.markdown import parse_markdown, strip_front_matter, FrontMatter


class TestParseMarkdown:
    def test_empty_text(self):
        assert parse_markdown("") == ([], None)
        assert parse_markdown("   ") == ([], None)

    def test_no_headings(self):
        text = "Just some plain text\nwith multiple lines."
        sections, fm = parse_markdown(text)
        assert len(sections) == 1
        assert sections[0].heading_path == "Document"
        assert sections[0].heading_level == 1
        assert "plain text" in sections[0].content

    def test_single_h1(self):
        text = "# Overview\nSome content here."
        sections, fm = parse_markdown(text)
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
        sections, fm = parse_markdown(text)
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
        sections, fm = parse_markdown(text)
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
        sections, fm = parse_markdown(text)
        paths = [s.heading_path for s in sections]
        assert "Title > Empty Section" not in paths
        assert "Title > Section With Content" in paths

    def test_preamble_before_first_heading(self):
        text = """This is preamble text.

# First Heading
Content.
"""
        sections, fm = parse_markdown(text)
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
        sections, fm = parse_markdown(text)
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
        sections, fm = parse_markdown(text)
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
        sections, fm = parse_markdown(text)
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
        sections, fm = parse_markdown(text)
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
        sections, fm = parse_markdown(text)
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
        sections, fm = parse_markdown(text)
        paths = [s.heading_path for s in sections]
        assert "Bold Title" in paths
        assert "**Bold Title**" not in paths
        assert any("GET /api/doors" in p for p in paths)
        assert not any("`" in p for p in paths)
        assert any("Authentication" in p for p in paths)
        assert not any("https://example.com" in p for p in paths)

    def test_unicode_normalization(self):
        text = "# \uff21\uff30\uff29\n\uff32\uff45\uff46\uff45\uff52\uff45\uff4e\uff43\uff45"
        sections, fm = parse_markdown(text)
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
        sections, fm = parse_markdown(text)
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
        sections, fm = parse_markdown(text)
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
        sections, fm = parse_markdown(text)
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
        sections, fm = parse_markdown(text)
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
        sections, fm = parse_markdown(text)
        assert len(sections) == 1
        assert sections[0].heading_path == "Setup"


class TestFrontMatter:
    def test_strip_front_matter(self):
        text = """---
layer: BL
topic: "gRPC API"
doc_number: "04a"
related_docs:
  - BL/03-SERVICE-REGISTRY.md
  - MMSS/01-HTTP-REST-API.md
chunking: heading
---
# Title
Content here.
"""
        body, fm = strip_front_matter(text)
        assert fm is not None
        assert fm.layer == "BL"
        assert fm.topic == "gRPC API"
        assert fm.doc_number == "04a"
        assert "BL/03-SERVICE-REGISTRY.md" in fm.related_docs
        assert "MMSS/01-HTTP-REST-API.md" in fm.related_docs
        assert fm.chunking == "heading"
        assert "# Title" in body
        assert "---" not in body.split("\n")[0]

    def test_no_front_matter(self):
        text = "# Just a heading\nSome text."
        body, fm = strip_front_matter(text)
        assert fm is None
        assert body == text

    def test_invalid_yaml_returns_none(self):
        text = "---\n[invalid yaml: {{{\n---\n# Title\nContent."
        body, fm = strip_front_matter(text)
        assert fm is None

    def test_parse_markdown_strips_front_matter(self):
        text = """---
layer: INTEGRATION
topic: "Video Streaming API"
doc_number: "11"
related_docs:
  - INTEGRATION/12-ARCHIVE-ACCESS.md
chunking: heading
---
# Video Streaming API

## RTSP Endpoints
Content about RTSP.
"""
        sections, fm = parse_markdown(text)
        assert fm is not None
        assert fm.layer == "INTEGRATION"
        assert fm.topic == "Video Streaming API"
        paths = [s.heading_path for s in sections]
        assert "Video Streaming API" in paths
        for s in sections:
            assert "---" not in s.content[:10]

    def test_front_matter_not_in_chunk_content(self):
        text = """---
layer: BL
topic: Test
---
# Title
Real content only.
"""
        sections, fm = parse_markdown(text)
        for s in sections:
            assert "layer:" not in s.content
            assert "topic:" not in s.content
