"""Unit tests for app.ingestion.text_cleaner."""

from app.ingestion.text_cleaner import clean_for_embedding, clean_heading, normalize_unicode


class TestNormalizeUnicode:
    def test_nfkc_fullwidth(self):
        assert normalize_unicode("\uff21\uff22\uff23") == "ABC"

    def test_ligature(self):
        assert normalize_unicode("\ufb01") == "fi"

    def test_normal_ascii_unchanged(self):
        assert normalize_unicode("hello world") == "hello world"

    def test_non_breaking_space(self):
        result = normalize_unicode("hello\u00a0world")
        assert result == "hello world"


class TestCleanHeading:
    def test_bold_removed(self):
        assert clean_heading("**Bold Title**") == "Bold Title"

    def test_italic_removed(self):
        assert clean_heading("*Italic Title*") == "Italic Title"

    def test_inline_code_removed(self):
        assert clean_heading("`GET /api/doors`") == "GET /api/doors"

    def test_link_keeps_text(self):
        assert clean_heading("[Authentication](https://example.com)") == "Authentication"

    def test_image_removed(self):
        assert clean_heading("![icon](img/icon.png) Title") == "Title"

    def test_strikethrough_removed(self):
        assert clean_heading("~~Deprecated~~ New") == "Deprecated New"

    def test_html_tags_removed(self):
        assert clean_heading("Title <br> Subtitle") == "Title  Subtitle"

    def test_complex_heading(self):
        result = clean_heading("**`GET`** [/doors/{id}](https://api.example.com/doors)")
        assert result == "GET /doors/{id}"

    def test_plain_text_unchanged(self):
        assert clean_heading("Simple Title") == "Simple Title"

    def test_autolink_keeps_url(self):
        assert clean_heading("<https://example.com>") == "https://example.com"


class TestCleanForEmbedding:
    def test_bold_removed(self):
        assert "**" not in clean_for_embedding("This is **bold** text.")

    def test_italic_removed(self):
        result = clean_for_embedding("This is *italic* text.")
        assert "*" not in result
        assert "italic" in result

    def test_link_text_preserved(self):
        result = clean_for_embedding("See [documentation](https://example.com) for details.")
        assert "documentation" in result
        assert "https://example.com" not in result

    def test_image_removed(self):
        result = clean_for_embedding("Diagram: ![architecture](img/arch.png)")
        assert "![" not in result
        assert "img/arch.png" not in result

    def test_html_tags_stripped(self):
        result = clean_for_embedding("Text <br> more <div class='x'>content</div>.")
        assert "<br>" not in result
        assert "<div" not in result
        assert "content" in result

    def test_code_blocks_preserved(self):
        text = "Before.\n\n```python\ndef foo():\n    return **bar**\n```\n\nAfter."
        result = clean_for_embedding(text)
        assert "```python" in result
        assert "def foo():" in result
        assert "**bar**" in result

    def test_inline_code_unwrapped(self):
        result = clean_for_embedding("Use `POST /api/login` to authenticate.")
        assert "POST /api/login" in result
        assert "`" not in result

    def test_heading_hashes_removed(self):
        result = clean_for_embedding("## Section Title\nContent here.")
        assert "##" not in result
        assert "Section Title" in result

    def test_bare_urls_removed(self):
        result = clean_for_embedding("Visit https://example.com/docs for info.")
        assert "https://example.com" not in result
        assert "Visit" in result

    def test_multiple_newlines_collapsed(self):
        result = clean_for_embedding("Para 1.\n\n\n\n\nPara 2.")
        assert "\n\n\n" not in result
        assert "Para 1." in result
        assert "Para 2." in result

    def test_empty_string(self):
        assert clean_for_embedding("") == ""

    def test_plain_text_unchanged(self):
        text = "Simple plain text without any formatting."
        assert clean_for_embedding(text) == text

    def test_strikethrough_removed(self):
        result = clean_for_embedding("~~old~~ new approach.")
        assert "~~" not in result
        assert "old" in result
        assert "new approach" in result

    def test_complex_markdown(self):
        text = (
            "## **Authentication** Guide\n\n"
            "Use [HMAC-SHA256](https://en.wikipedia.org/wiki/HMAC) for signing.\n\n"
            "![diagram](img/auth.png)\n\n"
            "```python\nimport hmac\n```\n\n"
            "See <https://docs.example.com> for more."
        )
        result = clean_for_embedding(text)
        assert "**" not in result
        assert "##" not in result
        assert "wikipedia.org" not in result
        assert "![" not in result
        assert "```python" in result
        assert "import hmac" in result
        assert "HMAC-SHA256" in result
        assert "Authentication" in result

    def test_double_backtick_inline_code(self):
        """Double backticks (``code``) should be unwrapped like single backticks."""
        result = clean_for_embedding("Use ``GET /api/doors`` to list doors.")
        assert "GET /api/doors" in result
        assert "``" not in result

    def test_bold_italic_does_not_span_lines(self):
        """Bold/italic regex should not greedily match across newlines."""
        text = "This is *italic* text.\nAnother *italic* line."
        result = clean_for_embedding(text)
        assert "*" not in result
        assert "italic" in result

    def test_bold_across_lines_not_matched(self):
        """**bold** should not match across line boundaries."""
        text = "Start **bold\nnot bold** end."
        result = clean_for_embedding(text)
        assert "Start" in result
        assert "end" in result

    def test_blockquotes_stripped(self):
        """Blockquote markers (>) should be removed."""
        text = "> This is a quote.\n> Second line of quote.\n\nNormal text."
        result = clean_for_embedding(text)
        assert ">" not in result
        assert "This is a quote." in result
        assert "Normal text." in result

    def test_nested_blockquotes(self):
        text = "> Level 1\n>> Level 2\n> Back to 1"
        result = clean_for_embedding(text)
        assert result.startswith("Level 1")
        assert "Level 2" in result

    def test_blockquotes_inside_code_blocks_preserved(self):
        """Blockquote markers inside code blocks should NOT be stripped."""
        text = "```\n> this is code, not a quote\n```"
        result = clean_for_embedding(text)
        assert ">" in result

    def test_unordered_list_markers_removed(self):
        """Unordered list markers (-, *, +) should be stripped."""
        text = "- Item one\n* Item two\n+ Item three"
        result = clean_for_embedding(text)
        assert result == "Item one\nItem two\nItem three"

    def test_ordered_list_markers_removed(self):
        """Ordered list markers (1., 2., etc.) should be stripped."""
        text = "1. First\n2. Second\n10. Tenth"
        result = clean_for_embedding(text)
        assert "1." not in result
        assert "2." not in result
        assert "First" in result
        assert "Second" in result
        assert "Tenth" in result

    def test_nested_list_markers_removed(self):
        """Nested list markers should be stripped, preserving indentation structure."""
        text = "- Parent\n  - Child\n    - Grandchild"
        result = clean_for_embedding(text)
        assert "- " not in result
        assert "Parent" in result
        assert "Child" in result
        assert "Grandchild" in result

    def test_list_markers_inside_code_blocks_preserved(self):
        """List markers inside code blocks should NOT be stripped."""
        text = "```\n- this is code\n1. also code\n```"
        result = clean_for_embedding(text)
        assert "- this is code" in result
        assert "1. also code" in result

    def test_unclosed_code_block_preserved(self):
        """Unclosed code block should be treated as code, not cleaned."""
        text = "Before.\n\n```python\ndef foo(**kwargs):\n    return bar"
        result = clean_for_embedding(text)
        assert "```python" in result
        assert "def foo(" in result
        assert "kwargs" in result

    def test_triple_backtick_inline_code(self):
        """Triple backticks used inline (no newline) should be unwrapped."""
        result = clean_for_embedding("Use ```GET /api/doors``` to list doors.")
        assert "GET /api/doors" in result
        assert "```" not in result


class TestCleanHeadingDoubleBackticks:
    def test_double_backtick_heading(self):
        assert clean_heading("``GET /api``") == "GET /api"

    def test_single_backtick_still_works(self):
        assert clean_heading("`POST /api`") == "POST /api"

    def test_triple_backtick_inline_heading(self):
        assert clean_heading("```GET /api```") == "GET /api"
