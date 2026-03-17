"""Tests for Swagger/OpenAPI converter (migrated from doc2md-mcp)."""

import json

import pytest

from app.ingestion.converters.swagger import (
    is_swagger_file,
    _parse_openapi,
    _resolve_ref,
    _type_str,
    _openapi_to_markdown,
    convert_swagger_file,
    convert_swagger_text,
)
from tests.unit.converters.conftest import OPENAPI_V3_SPEC, SWAGGER_V2_SPEC


class TestIsSwaggerFile:
    def test_valid_swagger_yaml(self, sample_swagger_yaml):
        assert is_swagger_file(str(sample_swagger_yaml)) is True

    def test_valid_swagger_json(self, sample_swagger_json):
        assert is_swagger_file(str(sample_swagger_json)) is True

    def test_plain_yaml(self, plain_yaml):
        assert is_swagger_file(str(plain_yaml)) is False

    def test_txt_file(self, tmp_path):
        f = tmp_path / "readme.txt"
        f.write_text("just text", encoding="utf-8")
        assert is_swagger_file(str(f)) is False

    def test_invalid_json(self, tmp_path):
        f = tmp_path / "broken.json"
        f.write_text("{broken", encoding="utf-8")
        assert is_swagger_file(str(f)) is False


class TestParseOpenapi:
    def test_yaml(self, sample_swagger_yaml):
        spec = _parse_openapi(str(sample_swagger_yaml))
        assert spec["openapi"] == "3.0.0"
        assert spec["info"]["title"] == "Test Pet API"

    def test_json(self, sample_swagger_json):
        spec = _parse_openapi(str(sample_swagger_json))
        assert spec["swagger"] == "2.0"
        assert spec["info"]["title"] == "Test Pet API v2"


class TestResolveRef:
    def test_valid_ref(self):
        spec = {"definitions": {"Pet": {"type": "object", "properties": {"name": {"type": "string"}}}}}
        result = _resolve_ref(spec, "#/definitions/Pet")
        assert result is not None
        assert result["type"] == "object"

    def test_missing_path(self):
        spec = {"definitions": {}}
        result = _resolve_ref(spec, "#/definitions/Missing")
        assert result is None

    def test_not_hash_prefix(self):
        assert _resolve_ref({}, "definitions/Pet") is None

    def test_deep_ref(self):
        spec = {"components": {"schemas": {"Dog": {"type": "object"}}}}
        result = _resolve_ref(spec, "#/components/schemas/Dog")
        assert result == {"type": "object"}


class TestTypeStr:
    def test_ref(self):
        result = _type_str({"$ref": "#/definitions/Pet"})
        assert "Pet" in result

    def test_array(self):
        result = _type_str({"type": "array", "items": {"type": "string"}})
        assert "array of" in result
        assert "string" in result

    def test_enum(self):
        result = _type_str({"type": "string", "enum": ["active", "inactive"]})
        assert "enum" in result
        assert "active" in result

    def test_format(self):
        result = _type_str({"type": "string", "format": "date-time"})
        assert "date-time" in result

    def test_simple(self):
        assert _type_str({"type": "integer"}) == "integer"

    def test_empty(self):
        assert _type_str({}) == ""


class TestOpenapiToMarkdown:
    def test_v3_title(self):
        md = _openapi_to_markdown(OPENAPI_V3_SPEC)
        assert "Test Pet API" in md
        assert "v1.0.0" in md

    def test_v3_endpoints(self):
        md = _openapi_to_markdown(OPENAPI_V3_SPEC)
        assert "GET /pets" in md
        assert "GET /pets/{petId}" in md
        assert "List all pets" in md

    def test_v3_parameters(self):
        md = _openapi_to_markdown(OPENAPI_V3_SPEC)
        assert "limit" in md
        assert "petId" in md

    def test_v3_models(self):
        md = _openapi_to_markdown(OPENAPI_V3_SPEC)
        assert "Pet" in md
        assert "Models" in md

    def test_v3_server(self):
        md = _openapi_to_markdown(OPENAPI_V3_SPEC)
        assert "https://api.example.com/v1" in md

    def test_v3_security(self):
        md = _openapi_to_markdown(OPENAPI_V3_SPEC)
        assert "Security Schemes" in md
        assert "apiKey" in md

    def test_v2_title(self):
        md = _openapi_to_markdown(SWAGGER_V2_SPEC)
        assert "Test Pet API v2" in md

    def test_v2_base_url(self):
        md = _openapi_to_markdown(SWAGGER_V2_SPEC)
        assert "api.example.com" in md

    def test_v2_models(self):
        md = _openapi_to_markdown(SWAGGER_V2_SPEC)
        assert "Pet" in md


class TestConvertSwaggerFile:
    def test_yaml_returns_markdown_and_metadata(self, sample_swagger_yaml):
        md_text, meta = convert_swagger_file(str(sample_swagger_yaml))
        assert "Test Pet API" in md_text
        assert "GET /pets" in md_text
        assert meta["endpoints"] == 2
        assert meta["models"] == 1
        assert meta["api_title"] == "Test Pet API"
        assert meta["swagger_version"] == "3.0.0"

    def test_json_returns_markdown_and_metadata(self, sample_swagger_json):
        md_text, meta = convert_swagger_file(str(sample_swagger_json))
        assert "Test Pet API v2" in md_text
        assert meta["swagger_version"] == "2.0"
        assert meta["endpoints"] == 1
        assert meta["models"] == 1


class TestConvertSwaggerText:
    def test_valid_json(self):
        text = json.dumps(OPENAPI_V3_SPEC)
        result = convert_swagger_text(text, "application/json")
        assert result is not None
        md_text, meta = result
        assert "Test Pet API" in md_text
        assert meta["endpoints"] == 2

    def test_invalid_text(self):
        result = convert_swagger_text("just plain text", "text/plain")
        assert result is None

    def test_valid_yaml(self):
        import yaml
        text = yaml.dump(SWAGGER_V2_SPEC)
        result = convert_swagger_text(text, "text/yaml")
        assert result is not None
        md_text, meta = result
        assert "Test Pet API v2" in md_text
