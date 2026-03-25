# Plexicode MCP Server

> **Complex APIs. Simple answers.**
>
> *From docs to code. Instantly.*

Plexicode is an MCP server that gives your AI coding assistant instant access to API documentation for hardware devices (IP cameras, access controllers, intercoms) and software platforms (VMS, PSIM, IoT platforms, SDKs) — so it can write accurate integration code instead of hallucinating APIs.

## The Problem

Developers integrating physical security and IoT products waste hours reading chaotic vendor documentation:

- 180-page PDFs with no search
- Swagger specs scattered across vendor portals
- Outdated SDK examples that don't compile
- Protocol details buried in page 94 of a manual

**Result:** 8-12 hours to write a single device integration.

## The Solution

Plexicode indexes product documentation (PDF, Swagger/OpenAPI, Markdown, web pages) into a semantic knowledge base and serves it to AI assistants via MCP.

```
Developer in Cursor:
  "Write Python code to stream video from a Hikvision camera
   and register it in Axxon One with analytics metadata"

Plexicode returns:
  — Hikvision RTSP streaming endpoint (from camera docs)
  — Hikvision authentication method (from camera docs)
  — Axxon One gRPC camera registration API (from VMS SDK docs)
  — Working code combining all three

Total time: minutes, not hours.
```

## Quick Start

### 1. Run the server

```bash
docker compose up -d
```

### 2. Connect from Cursor

Add to your `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "plexicode": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

### 3. Start coding

Ask your AI assistant anything about the indexed products:

```
How do I open a door via HikCentral HTTP API?
```

```
Show me the ONVIF PTZ continuous move command for pan and tilt.
```

```
What's the RTSP stream URL format for Hikvision DS-2CD2347G2-LU?
```

Plexicode automatically provides the relevant documentation to your AI assistant.

## MCP Tools

Plexicode exposes 3 tools via the Model Context Protocol:

### `search_documentation`

Semantic search across all indexed product documentation. Use this to find API endpoints, authentication methods, request/response formats, and code examples.

| Parameter | Required | Description |
|-----------|----------|-------------|
| `query` | Yes | Natural language query (e.g. "how to open a door via API") |
| `product` | No | Filter by product name (e.g. "HikCentral", "Axxon One") |
| `version` | No | Filter by firmware/API version (e.g. "V2.6.1") |
| `limit` | No | Number of results, 1-20 (default: 5) |

### `get_api_endpoint`

Look up documentation for a specific API endpoint path. Performs exact match first, then falls back to semantic search.

| Parameter | Required | Description |
|-----------|----------|-------------|
| `endpoint` | Yes | API path (e.g. "/acs/v1/door/doControl", "/ISAPI/AccessControl/Door/param") |
| `product` | No | Filter by product name |

### `list_products`

Discover what products have indexed documentation. **Call this first** to see what's available.

| Parameter | Required | Description |
|-----------|----------|-------------|
| `category` | No | Filter by category (e.g. "camera", "vms", "access_control") |
| `query` | No | Search by product name or manufacturer (e.g. "Hikvision", "Axxon") |

## Supported Document Formats

| Format | Extensions | How It's Parsed |
|--------|-----------|-----------------|
| Markdown | `.md` | Chunked by H1/H2/H3 headers |
| Swagger / OpenAPI | `.json`, `.yaml` | 1 chunk per endpoint (structured) |
| PDF | `.pdf` | Text extraction + optional OCR |
| Web page | URL | HTML scraping + cleanup |
| Protobuf | `.proto` | Service/method extraction |

## Architecture

```
Cursor / AI IDE                    IPCodex Server
┌──────────────┐                  ┌──────────────────────────┐
│  Developer   │  MCP over HTTP   │  FastAPI + FastMCP       │
│  asks AI to  │ ───────────────> │                          │
│  write code  │                  │  ┌────────────────────┐  │
│              │ <─────────────── │  │ Semantic Search     │  │
│  AI gets     │  documentation   │  │ (pgvector + HNSW)   │  │
│  accurate    │  chunks          │  └────────────────────┘  │
│  code        │                  │           │              │
└──────────────┘                  │  ┌────────▼───────────┐  │
                                  │  │ PostgreSQL 16      │  │
                                  │  │ + pgvector          │  │
                                  │  │ (embeddings)        │  │
                                  │  └────────────────────┘  │
                                  └──────────────────────────┘
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| API | FastAPI + uvicorn |
| MCP | FastMCP (Python MCP SDK), Streamable HTTP |
| Database | PostgreSQL 16 + pgvector (HNSW cosine similarity) |
| Embeddings | Gemini gemini-embedding-2-preview / local E5 models |
| Object Storage | MinIO / S3 |
| Cache | Redis |

## Development

### Prerequisites

- Docker and Docker Compose
- Python 3.12+

### Local setup

```bash
# Clone and start infrastructure
git clone <repo-url>
cd ipcodex
docker compose up -d

# Install backend dependencies
cd backend
pip install -r requirements.txt

# Run the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Running tests

```bash
cd backend
pytest tests/ -v
```

Integration tests use Testcontainers (PostgreSQL + pgvector) — Docker must be running.

## Compared to Context7

| | Context7 | Plexicode |
|---|---|---|
| **Domain** | Open-source software libraries (React, Next.js) | Hardware devices + software platforms (cameras, VMS, access control) |
| **Sources** | Public GitHub repos | PDF, Swagger, web pages, vendor portals |
| **Versioning** | Library versions | Firmware versions + API versions |
| **OCR** | No | Yes (scanned PDFs) |
| **Target user** | Web/app developers | System integrators, IoT developers |

## License

Proprietary. All rights reserved.
