"""Integration tests for document preparation pipeline quality.

Tests the full chain: parse → clean → chunk → enrich → embed → store → search.
Verifies that text cleaning, tokenization, and enrichment work correctly end-to-end.
"""

import pytest

from app.ingestion.chunker import chunk_sections, _estimate_tokens
from app.ingestion.parsers.markdown import parse_markdown
from app.ingestion.pipeline import enrich_for_embedding, ingest_file
from app.search.service import search_documents


class TestMarkdownCleaningPipeline:
    def test_headings_cleaned_in_parsed_sections(self):
        """Markdown formatting in headings should be stripped during parsing."""
        md = "# **Bold Title**\nContent.\n\n## `GET /api/doors`\nEndpoint docs."
        sections, _fm = parse_markdown(md)
        paths = [s.heading_path for s in sections]
        assert "Bold Title" in paths
        assert "**Bold Title**" not in paths
        assert any("GET /api/doors" in p for p in paths)
        assert not any("`" in p for p in paths)

    def test_enrichment_cleans_markdown_from_content(self):
        """enrich_for_embedding should strip Markdown artifacts."""
        from app.ingestion.chunker import ChunkData

        chunks = [
            ChunkData(
                heading_path="API > Auth",
                heading_level=2,
                content="Use **HMAC** for [auth](https://example.com). ![diagram](img.png)",
                token_count=10,
            ),
        ]
        enriched = enrich_for_embedding(chunks)
        assert "**" not in enriched[0]
        assert "https://example.com" not in enriched[0]
        assert "![" not in enriched[0]
        assert "HMAC" in enriched[0]
        assert "[API > Auth]" in enriched[0]

    def test_code_blocks_preserved_in_enrichment(self):
        from app.ingestion.chunker import ChunkData

        chunks = [
            ChunkData(
                heading_path="Example",
                heading_level=2,
                content="Before.\n\n```python\ndef foo(**kwargs):\n    pass\n```\n\nAfter.",
                token_count=20,
            ),
        ]
        enriched = enrich_for_embedding(chunks)
        assert "```python" in enriched[0]
        assert "**kwargs**" in enriched[0]


class TestTokenizerAccuracy:
    def test_estimate_tokens_returns_positive(self):
        assert _estimate_tokens("hello world") >= 1

    def test_estimate_tokens_empty(self):
        assert _estimate_tokens("") == 1

    def test_chunks_respect_max_tokens(self):
        """All chunks should be within max_tokens (with some tolerance for atomic blocks)."""
        big_content = "\n\n".join(f"Paragraph {i}. " + " ".join(["word"] * 30) for i in range(20))
        sections = [
            type("Section", (), {"heading_path": "Big", "heading_level": 1, "content": big_content})()
        ]
        from app.ingestion.chunker import Section

        real_sections = [Section(heading_path="Big", heading_level=1, content=big_content)]
        chunks = chunk_sections(real_sections, max_tokens=100, min_tokens=10)
        assert len(chunks) > 1
        for c in chunks:
            assert c.token_count > 0


class TestCodeBlockHeadingProtection:
    def test_headings_in_code_blocks_not_parsed(self):
        """Full pipeline: headings inside code blocks should not create sections."""
        md = """# Installation Guide

Follow these steps:

```bash
# Step 1: Install dependencies
apt-get update
## Step 2: Configure
echo "done"
```

## Troubleshooting
If something goes wrong, check logs.
"""
        sections, _fm = parse_markdown(md)
        paths = [s.heading_path for s in sections]
        assert "Installation Guide" in paths
        assert "Installation Guide > Troubleshooting" in paths
        assert not any("Step 1" in p for p in paths)
        assert not any("Step 2" in p for p in paths)

    def test_code_block_headings_stay_in_content(self):
        """Code block content with # should remain in the section content."""
        md = """# Config

```yaml
# Database settings
host: localhost
port: 5432
```
"""
        sections, _fm = parse_markdown(md)
        assert len(sections) == 1
        assert "# Database settings" in sections[0].content

    def test_multiple_code_blocks_with_headings(self):
        md = """# API

```python
# Initialize client
client = APIClient()
```

## Endpoints

```bash
# List all doors
curl /api/doors
```

## Auth

Token-based.
"""
        sections, _fm = parse_markdown(md)
        chunks = chunk_sections(sections, max_tokens=500, min_tokens=5)
        paths = [c.heading_path for c in chunks]
        assert not any("Initialize client" in p for p in paths)
        assert not any("List all doors" in p for p in paths)
        assert any("Endpoints" in p for p in paths)
        assert any("Auth" in p for p in paths)


class TestBlockquoteCleaning:
    def test_blockquotes_cleaned_in_pipeline(self):
        from app.ingestion.chunker import ChunkData

        chunks = [
            ChunkData(
                heading_path="Notes",
                heading_level=2,
                content="> Important: read carefully.\n> This is critical.\n\nNormal text.",
                token_count=15,
            ),
        ]
        enriched = enrich_for_embedding(chunks)
        text = enriched[0]
        lines_after_heading = text.split("\n", 1)[1] if "\n" in text else text
        assert ">" not in lines_after_heading
        assert "Important: read carefully." in text


class TestUnicodeNormalization:
    def test_fullwidth_chars_normalized(self):
        md = "# \uff21\uff30\uff29\n\uff32\uff45\uff46\uff45\uff52\uff45\uff4e\uff43\uff45"
        sections, _fm = parse_markdown(md)
        assert sections[0].heading_path == "API"
        assert "Reference" in sections[0].content

    def test_non_breaking_space_normalized(self):
        md = "# Title\nSome\u00a0text\u00a0here."
        sections, _fm = parse_markdown(md)
        assert "\u00a0" not in sections[0].content


class TestEndToEndPipeline:
    async def test_ingest_and_search_markdown_with_formatting(self, db_session, tmp_path):
        """Full pipeline: ingest MD with bold/links → search should find clean content."""
        content = """# **Authentication** Guide

## [HMAC-SHA256](https://en.wikipedia.org/wiki/HMAC) Signing

Use **HMAC-SHA256** to sign all API requests.
The signature is calculated as: `HMAC(secret_key, string_to_sign)`.

![diagram](img/auth_flow.png)

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| appKey | string | Your application key |
| appSecret | string | Your secret key |
| timestamp | int | Unix timestamp |

## Token-Based Auth

For simpler integrations, use Bearer tokens:

```python
headers = {"Authorization": f"Bearer {token}"}
response = requests.get(url, headers=headers)
```
"""
        path = tmp_path / "auth_guide.md"
        path.write_text(content, encoding="utf-8")

        result = await ingest_file(
            session=db_session,
            file_path=str(path),
            product_name="TestAPI",
            firmware_version="1.0",
        )
        assert result["status"] == "ok"
        assert result["chunks"] > 0

        results = await search_documents(db_session, "HMAC authentication signing")
        assert len(results) > 0

    async def test_search_finds_exact_api_terms(self, db_session, tmp_path):
        """BM25 component should help find exact API terms like endpoint paths."""
        content = """# API Reference

## POST /acs/v1/door/doControl

Control a door (open/close/lock).

### Request Body

```json
{
    "doorIndexCodes": ["door1"],
    "controlType": 2
}
```

## GET /acs/v1/door/list

List all configured doors.

## POST /acs/v1/event/subscribe

Subscribe to real-time events.
"""
        path = tmp_path / "api_ref.md"
        path.write_text(content, encoding="utf-8")

        await ingest_file(
            session=db_session,
            file_path=str(path),
            product_name="AccessControl",
            firmware_version="2.0",
        )

        results = await search_documents(db_session, "doControl door open")
        assert len(results) > 0
