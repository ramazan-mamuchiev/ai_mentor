"""Unit tests for app.ingestion.parsers.swagger."""

import json

from app.ingestion.parsers.swagger import parse_swagger


MINIMAL_OPENAPI3 = """
openapi: "3.0.0"
info:
  title: Door API
  version: "1.0"
paths:
  /doors:
    get:
      summary: List all doors
      tags:
        - doors
      responses:
        "200":
          description: OK
  /doors/{id}/open:
    post:
      summary: Open a door
      tags:
        - doors
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: integer
      responses:
        "200":
          description: Door opened
"""

SWAGGER2_JSON = json.dumps({
    "swagger": "2.0",
    "info": {"title": "Camera API", "version": "2.0"},
    "paths": {
        "/cameras": {
            "get": {
                "summary": "List cameras",
                "tags": ["cameras"],
                "responses": {"200": {"description": "OK"}},
            }
        }
    },
    "definitions": {
        "Camera": {
            "type": "object",
            "description": "Camera device",
            "properties": {
                "id": {"type": "integer", "description": "Camera ID"},
                "name": {"type": "string", "description": "Camera name"},
            },
            "required": ["id"],
        }
    },
})


class TestParseSwagger:
    def test_openapi3_yaml(self):
        sections = parse_swagger(MINIMAL_OPENAPI3)
        assert len(sections) >= 3
        paths = [s.heading_path for s in sections]
        assert any("GET /doors" in p for p in paths)
        assert any("POST /doors/{id}/open" in p for p in paths)

    def test_swagger2_json(self):
        sections = parse_swagger(SWAGGER2_JSON, file_path="spec.json")
        assert len(sections) >= 2
        paths = [s.heading_path for s in sections]
        assert any("GET /cameras" in p for p in paths)

    def test_overview_section_created(self):
        sections = parse_swagger(MINIMAL_OPENAPI3)
        assert sections[0].heading_path == "Door API"
        assert sections[0].heading_level == 1
        assert "Door API" in sections[0].content

    def test_endpoint_has_parameters(self):
        sections = parse_swagger(MINIMAL_OPENAPI3)
        open_door = [s for s in sections if "POST /doors/{id}/open" in s.heading_path]
        assert len(open_door) == 1
        assert "id" in open_door[0].content
        assert "path" in open_door[0].content

    def test_models_parsed(self):
        sections = parse_swagger(SWAGGER2_JSON, file_path="spec.json")
        model_sections = [s for s in sections if "Camera" in s.heading_path and "Models" in s.heading_path]
        assert len(model_sections) == 1
        assert "Camera ID" in model_sections[0].content
        assert "Camera name" in model_sections[0].content

    def test_invalid_yaml_returns_empty(self):
        sections = parse_swagger("not: [valid: yaml: {{{")
        assert sections == []

    def test_invalid_json_returns_empty(self):
        sections = parse_swagger("{invalid json", file_path="bad.json")
        assert sections == []

    def test_empty_spec_returns_empty(self):
        sections = parse_swagger("")
        assert sections == []

    def test_endpoint_responses_included(self):
        sections = parse_swagger(MINIMAL_OPENAPI3)
        door_list = [s for s in sections if "GET /doors" in s.heading_path]
        assert len(door_list) == 1
        assert "200" in door_list[0].content

    def test_tags_in_heading_path(self):
        sections = parse_swagger(MINIMAL_OPENAPI3)
        door_sections = [s for s in sections if s.heading_level == 3]
        for s in door_sections:
            assert "doors" in s.heading_path
