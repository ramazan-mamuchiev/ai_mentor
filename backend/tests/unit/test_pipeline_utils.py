"""Unit tests for pipeline utility functions (detect_format, _file_hash)."""

import hashlib
import os

from app.ingestion.pipeline import _file_hash, detect_format


class TestDetectFormat:
    def test_markdown_extension(self, tmp_path):
        f = tmp_path / "doc.md"
        f.write_text("# Hello")
        assert detect_format(str(f)) == "markdown"

    def test_pdf_extension(self, tmp_path):
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"%PDF-1.4")
        assert detect_format(str(f)) == "pdf"

    def test_yaml_extension(self, tmp_path):
        f = tmp_path / "spec.yaml"
        f.write_text("openapi: '3.0.0'")
        assert detect_format(str(f)) == "swagger"

    def test_yml_extension(self, tmp_path):
        f = tmp_path / "spec.yml"
        f.write_text("swagger: '2.0'")
        assert detect_format(str(f)) == "swagger"

    def test_json_swagger(self, tmp_path):
        f = tmp_path / "spec.json"
        f.write_text('{"swagger": "2.0", "info": {}}')
        assert detect_format(str(f)) == "swagger"

    def test_json_openapi(self, tmp_path):
        f = tmp_path / "api.json"
        f.write_text('{"openapi": "3.0.0", "info": {}}')
        assert detect_format(str(f)) == "swagger"

    def test_json_non_swagger(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text('{"key": "value"}')
        assert detect_format(str(f)) == "markdown"

    def test_unknown_extension(self, tmp_path):
        f = tmp_path / "readme.txt"
        f.write_text("Some text")
        assert detect_format(str(f)) == "markdown"


class TestFileHash:
    def test_deterministic(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("Hello, world!")
        h1 = _file_hash(str(f))
        h2 = _file_hash(str(f))
        assert h1 == h2

    def test_correct_sha256(self, tmp_path):
        content = b"test content for hashing"
        f = tmp_path / "test.bin"
        f.write_bytes(content)
        expected = hashlib.sha256(content).hexdigest()
        assert _file_hash(str(f)) == expected

    def test_different_content_different_hash(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("content A")
        f2.write_text("content B")
        assert _file_hash(str(f1)) != _file_hash(str(f2))
