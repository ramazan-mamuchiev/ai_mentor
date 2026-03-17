"""Tests for web/URL converter (migrated from doc2md-mcp)."""

import json
import ssl
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from app.ingestion.converters.web import (
    _fetch_url,
    _try_parse_as_openapi,
    _detect_swagger_spec_url,
    _make_ssl_context,
    convert_url,
)


# ---------------------------------------------------------------------------
# _try_parse_as_openapi
# ---------------------------------------------------------------------------

class TestTryParseAsOpenapi:
    def test_json_swagger(self):
        body = json.dumps({"swagger": "2.0", "info": {"title": "T"}}).encode()
        result = _try_parse_as_openapi(body, "application/json")
        assert result is not None
        assert result["swagger"] == "2.0"

    def test_json_openapi(self):
        body = json.dumps({"openapi": "3.0.0", "info": {"title": "T"}}).encode()
        result = _try_parse_as_openapi(body, "application/json")
        assert result is not None
        assert result["openapi"] == "3.0.0"

    def test_yaml_openapi(self):
        body = b"openapi: '3.0.0'\ninfo:\n  title: T\n"
        result = _try_parse_as_openapi(body, "text/yaml")
        assert result is not None

    def test_html_returns_none(self):
        body = b"<html><body>Hello</body></html>"
        result = _try_parse_as_openapi(body, "text/html")
        assert result is None

    def test_broken_json(self):
        body = b"{broken json"
        result = _try_parse_as_openapi(body, "application/json")
        assert result is None

    def test_plain_dict_no_swagger_key(self):
        body = json.dumps({"name": "test"}).encode()
        result = _try_parse_as_openapi(body, "application/json")
        assert result is None


# ---------------------------------------------------------------------------
# _detect_swagger_spec_url
# ---------------------------------------------------------------------------

class TestDetectSwaggerSpecUrl:
    def test_swagger_ui_bundle(self):
        html = """
        <script>
        const ui = SwaggerUIBundle({
            url: "/api/swagger.json",
            dom_id: '#swagger-ui'
        })
        </script>
        """
        result = _detect_swagger_spec_url(html, "https://example.com/docs")
        assert result == "https://example.com/api/swagger.json"

    def test_spec_url_attribute(self):
        html = '<redoc spec-url="/openapi.yaml"></redoc>'
        result = _detect_swagger_spec_url(html, "https://example.com/")
        assert result == "https://example.com/openapi.yaml"

    def test_redoc_init(self):
        html = """
        <script>
        Redoc.init("https://cdn.example.com/spec.json")
        </script>
        """
        result = _detect_swagger_spec_url(html, "https://example.com/")
        assert result is None  # Redoc.init not in our extractors

    def test_plain_html_returns_none(self):
        html = "<html><body><h1>Hello</h1></body></html>"
        result = _detect_swagger_spec_url(html, "https://example.com/")
        assert result is None

    def test_relative_url_resolved(self):
        html = """<script>SwaggerUIBundle({url: "spec.yaml"})</script>"""
        result = _detect_swagger_spec_url(html, "https://example.com/docs/index.html")
        assert result == "https://example.com/docs/spec.yaml"


# ---------------------------------------------------------------------------
# _fetch_url (with mock)
# ---------------------------------------------------------------------------

class TestFetchUrl:
    def test_returns_tuple(self):
        mock_resp = MagicMock()
        mock_resp.headers = {"Content-Type": "application/json"}
        mock_resp.url = "https://example.com/api.json"
        mock_resp.read.return_value = b'{"openapi": "3.0.0"}'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            body, ct, url = _fetch_url("https://example.com/api.json")

        assert body == b'{"openapi": "3.0.0"}'
        assert ct == "application/json"
        assert url == "https://example.com/api.json"


# ---------------------------------------------------------------------------
# _make_ssl_context
# ---------------------------------------------------------------------------

class TestMakeSslContext:
    def test_returns_ssl_context(self):
        ctx = _make_ssl_context()
        assert isinstance(ctx, ssl.SSLContext)

    def test_no_verify(self):
        ctx = _make_ssl_context()
        assert ctx.check_hostname is False


# ---------------------------------------------------------------------------
# convert_url (async, with mocks)
# ---------------------------------------------------------------------------

class TestConvertUrl:
    @pytest.mark.asyncio
    async def test_direct_openapi_spec(self):
        spec_json = json.dumps({
            "openapi": "3.0.0",
            "info": {"title": "Remote API", "version": "1.0"},
            "paths": {"/test": {"get": {"summary": "Test endpoint", "responses": {"200": {"description": "OK"}}}}},
        })

        with patch(
            "app.ingestion.converters.web._fetch_url",
            return_value=(spec_json.encode(), "application/json", "http://x.com/spec.json"),
        ):
            md_text, meta = await convert_url("http://x.com/spec.json")

        assert "Remote API" in md_text
        assert meta["detection_method"] == "direct_openapi_spec"

    @pytest.mark.asyncio
    async def test_swagger_ui_extracted(self):
        html = b"""
        <html><body>
        <script>SwaggerUIBundle({url: "/openapi.json"})</script>
        </body></html>
        """
        spec_json = json.dumps({
            "openapi": "3.0.0",
            "info": {"title": "Extracted API", "version": "1.0"},
            "paths": {"/test": {"get": {"summary": "Test", "responses": {"200": {"description": "OK"}}}}},
        })

        call_count = 0

        def mock_fetch(url, accept="*/*"):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (html, "text/html", "http://x.com/docs")
            return (spec_json.encode(), "application/json", url)

        with patch("app.ingestion.converters.web._fetch_url", side_effect=mock_fetch):
            md_text, meta = await convert_url("http://x.com/docs")

        assert "Extracted API" in md_text
        assert meta["detection_method"] == "swagger_ui_extracted"

    @pytest.mark.asyncio
    async def test_crawl4ai_fallback(self):
        html = b"<html><body><p>Regular page</p></body></html>"

        with patch(
            "app.ingestion.converters.web._fetch_url",
            return_value=(html, "text/html", "http://x.com/page"),
        ), patch(
            "app.ingestion.converters.web._crawl4ai_available",
            return_value=True,
        ), patch(
            "app.ingestion.converters.web._crawl_url",
            new_callable=AsyncMock,
            return_value=("# Crawled Content", "Page Title"),
        ):
            md_text, meta = await convert_url("http://x.com/page")

        assert "Crawled Content" in md_text
        assert meta["detection_method"] == "crawl4ai_fallback"
