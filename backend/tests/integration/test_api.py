"""Integration tests for FastAPI endpoints and full MCP lifecycle."""

import contextlib

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, patch

from app.ingestion.pipeline import ingest_file


def _create_test_app(db_engine):
    """Create a fresh FastAPI+MCP app instance (avoids session_manager reuse)."""
    from fastapi import FastAPI
    from starlette.routing import Mount
    from sqlalchemy import text
    from mcp.server.fastmcp import FastMCP
    from mcp.server.transport_security import TransportSecuritySettings

    from app.mcp.server import (
        tool_get_api_endpoint,
        tool_list_products,
        tool_search_documentation,
    )

    mcp = FastMCP(
        "AI Mentor",
        stateless_http=True,
        json_response=True,
        streamable_http_path="/",
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    mcp.tool(name="search_documentation")(tool_search_documentation)
    mcp.tool(name="get_api_endpoint")(tool_get_api_endpoint)
    mcp.tool(name="list_products")(tool_list_products)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        async with mcp.session_manager.run():
            yield

    app = FastAPI(title="AI Mentor-Test", version="0.1.0", lifespan=lifespan)
    app.router.routes.append(Mount("/mcp", app=mcp.streamable_http_app()))

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/ready")
    async def ready():
        try:
            async with db_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            db_status = "ok"
        except Exception as e:
            db_status = f"error: {e}"
        return {"db": db_status}

    return app


@pytest.fixture
async def client(db_session, db_engine):
    """AsyncClient wired to a fresh FastAPI+MCP app with test DB session + lifespan."""
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = db_session
    mock_cm.__aexit__.return_value = None

    with patch("app.mcp.server.async_session", return_value=mock_cm):
        app = _create_test_app(db_engine)
        async with LifespanManager(app) as manager:
            transport = ASGITransport(app=manager.app)
            async with AsyncClient(transport=transport, base_url="http://localhost") as ac:
                yield ac


class TestHealthEndpoints:
    async def test_health(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    async def test_ready(self, client):
        resp = await client.get("/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert "db" in data
        assert data["db"] == "ok"


class TestMCPProtocol:
    async def _mcp_call(self, client, method, params=None, req_id=1):
        body = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
        }
        if params is not None:
            body["params"] = params

        resp = await client.post(
            "/mcp/",
            json=body,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        return resp

    async def test_initialize(self, client):
        resp = await self._mcp_call(client, "initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["jsonrpc"] == "2.0"
        assert "result" in data
        assert data["result"]["serverInfo"]["name"] == "AI Mentor"
        assert "capabilities" in data["result"]
        assert "tools" in data["result"]["capabilities"]

    async def test_tools_list(self, client):
        await self._mcp_call(client, "initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0"},
        })

        resp = await self._mcp_call(client, "tools/list", {}, req_id=2)
        assert resp.status_code == 200
        data = resp.json()
        assert "result" in data
        tools = data["result"]["tools"]
        tool_names = [t["name"] for t in tools]
        assert "search_documentation" in tool_names
        assert "get_api_endpoint" in tool_names
        assert "list_products" in tool_names

    async def test_invalid_jsonrpc(self, client):
        resp = await client.post(
            "/mcp/",
            json={"invalid": "request"},
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        assert resp.status_code in (200, 400)
        data = resp.json()
        assert "error" in data

    async def test_full_lifecycle(self, client, db_session, sample_md_file):
        """Full MCP lifecycle: initialize -> ingest -> list_products -> search."""
        init_resp = await self._mcp_call(client, "initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "cursor-test", "version": "1.0"},
        })
        assert init_resp.status_code == 200
        assert "result" in init_resp.json()

        await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            product_name="LifecycleDevice",
            firmware_version="1.0",
            manufacturer="TestMfg",
        )

        list_resp = await self._mcp_call(client, "tools/call", {
            "name": "list_products",
            "arguments": {},
        }, req_id=3)
        assert list_resp.status_code == 200
        list_data = list_resp.json()
        assert "result" in list_data
        list_text = list_data["result"]["content"][0]["text"]
        assert "LifecycleDevice" in list_text

        search_resp = await self._mcp_call(client, "tools/call", {
            "name": "search_documentation",
            "arguments": {"query": "door control", "limit": 3},
        }, req_id=4)
        assert search_resp.status_code == 200
        search_data = search_resp.json()
        assert "result" in search_data
        assert search_data["result"]["isError"] is False
        search_text = search_data["result"]["content"][0]["text"]
        assert "[1]" in search_text

    async def test_tools_have_3_items(self, client):
        """Verify exactly 3 tools are registered (no ingest tools)."""
        await self._mcp_call(client, "initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0"},
        })
        resp = await self._mcp_call(client, "tools/list", {}, req_id=2)
        tools = resp.json()["result"]["tools"]
        assert len(tools) == 3
        tool_names = sorted(t["name"] for t in tools)
        assert tool_names == ["get_api_endpoint", "list_products", "search_documentation"]

    async def test_list_products_with_query_filter(self, client, db_session, sample_md_file):
        """Test list_products query parameter via MCP protocol."""
        await self._mcp_call(client, "initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0"},
        })

        await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            product_name="FilterTestDevice",
            firmware_version="1.0",
        )

        resp = await self._mcp_call(client, "tools/call", {
            "name": "list_products",
            "arguments": {"query": "FilterTest"},
        }, req_id=3)
        assert resp.status_code == 200
        text = resp.json()["result"]["content"][0]["text"]
        assert "FilterTestDevice" in text

        resp_miss = await self._mcp_call(client, "tools/call", {
            "name": "list_products",
            "arguments": {"query": "Nonexistent"},
        }, req_id=4)
        text_miss = resp_miss.json()["result"]["content"][0]["text"]
        assert "No products found" in text_miss

    async def test_get_api_endpoint_via_protocol(self, client, db_session, sample_md_file):
        """Test get_api_endpoint tool via MCP JSON-RPC."""
        await self._mcp_call(client, "initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0"},
        })

        await ingest_file(
            session=db_session,
            file_path=sample_md_file,
            product_name="EndpointTestDevice",
            firmware_version="1.0",
        )

        resp = await self._mcp_call(client, "tools/call", {
            "name": "get_api_endpoint",
            "arguments": {"endpoint": "Open Door"},
        }, req_id=3)
        assert resp.status_code == 200
        data = resp.json()
        assert data["result"]["isError"] is False
        text = data["result"]["content"][0]["text"]
        assert "EndpointTestDevice" in text
