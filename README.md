# Lexiro

> **Complex docs. Simple code.**
>
> *From documentation to code. Instantly.*

Lexiro is an AI integration platform that transforms chaotic product documentation (PDF, Swagger/OpenAPI, Postman, Markdown, Protobuf, web pages, Confluence) into a structured knowledge base with semantic search — enabling AI coding assistants to write accurate integration code via RAG + MCP.

**Live**: [https://lexiro.io](https://lexiro.io)

## Why

Developers integrating physical security and IoT products waste hours reading vendor documentation: 180-page PDFs with no search, scattered Swagger specs, outdated SDK examples. Lexiro indexes it all and serves relevant documentation to your AI assistant in real time.

```
Developer in Cursor:
  "Write C# code to open a door via HikCentral HTTP API"

Lexiro returns:
  — /acs/v1/door/doControl endpoint details
  — Request format: { doorIndexCodes, controlType, controlDirection }
  — AK/SK authentication headers
  — Working code with correct params

Total time: minutes, not hours.
```

## Project Structure

```
lexiro/
├── backend/              Python backend (FastAPI + Celery)
│   ├── app/
│   │   ├── mcp/          MCP server — AI coding assistant integration
│   │   ├── chat/         RAG chat with LLM (hybrid search, reranking, streaming)
│   │   ├── ingestion/    Document ingestion pipeline (8 formats)
│   │   ├── search/       Hybrid search: pgvector + BM25 + RRF fusion
│   │   ├── billing/      Per-model token billing, usage tracking, margin analysis
│   │   ├── admin/        Admin panel API (tenants, documents, chat audit, prompts)
│   │   └── ...
│   └── tests/            Unit + integration tests (Testcontainers)
├── frontend/             React SPA (TypeScript + Vite)
│   ├── src/pages/        Landing, Chat, Documents, Products, Analytics, Admin
│   └── src/locales/      i18n (EN/RU)
├── architecture/         Architecture docs (17 files — see below)
├── monitoring/           Grafana + Loki + Promtail + Prometheus configs
│   └── grafana/          9 dashboards, 10 alert rules
└── docker-compose.yml    Full stack: 12 services
```

## Core Components

### MCP Server

The heart of Lexiro — an MCP server that gives AI coding assistants (Cursor, Windsurf, GitHub Copilot) instant access to indexed product documentation.

10 tools:

| Tool | Purpose |
|------|---------|
| `search_documentation` | Semantic + hybrid search across all docs |
| `get_api_lifecycle` | **Full integration blueprint** — auth, init sequence, data models, error handling, code skeleton |
| `get_api_endpoint` | Look up a specific API endpoint by path |
| `list_products` | Discover available products |
| `list_documents` | List documents for a product |
| `get_document_outline` | Table of contents / heading structure |
| `get_section` | Full untruncated content of a section |
| `get_code_examples` | Find code snippets and integration patterns |
| `get_product_info` | Detailed product summary (versions, doc types, topics) |
| `grep_docs` | Exact text search (IPs, error codes, params) |

All search tools automatically enrich results with lifecycle context (auth flow, prerequisites, known errors) when available.

See **[MCP Server README](backend/app/mcp/README.md)** for tool reference, quick start, and connection instructions.

### Ingestion Pipeline

Multi-format async pipeline (Celery) with real-time progress tracking:

| Format | Parser | Notes |
|--------|--------|-------|
| Markdown | H1–H6 header chunking, code/table protection | Base format |
| Swagger / OpenAPI 2.0/3.x | 1 chunk per endpoint (structured) | Exact path matching |
| Postman Collection v2.1 | Request → endpoint docs conversion | Preserves examples |
| PDF (text) | PyMuPDF → parallel ThreadPoolExecutor (50-page chunks) | Parallel conversion |
| PDF (scanned) | Gemini Vision OCR (two-pass) | Language detection + per-image OCR |
| Web page | httpx + BeautifulSoup → cleanup | HTML → Markdown |
| Protobuf | proto-schema-parser → services/methods/messages | gRPC documentation |
| Confluence | Space crawl → parallel page ingestion | Full space import |

Pipeline stages: Download → Convert → Normalize (NFKC) → Parse (heading extraction) → Chunk (atomic blocks, split large, merge small) → LLM Metadata Extraction (Gemini Flash) → Enrich → Embed (Gemini Embedding) → Store (pgvector).

### API Lifecycle Analysis

Deep LLM-powered analysis of API documentation that extracts a complete integration blueprint — triggered manually per document or product.

**What it produces** (10 structured sections):

| Section | Description |
|---------|-------------|
| Prerequisites | Base URL, API keys, certificates, SDK requirements |
| Integration Phases | Ordered steps: auth → init → operations → cleanup, with HTTP method, request/response examples |
| Data Models | Request/response schemas with field types, constraints, examples |
| Error Catalog | HTTP statuses, error codes, meanings, recovery actions, retry timings |
| Data Access Patterns | Pagination, streaming, webhooks, long-polling mechanisms |
| Unique Patterns | Non-standard API behaviors (heartbeats, custom auth, XML quirks) |
| Dependency Chains | "Must do A before B" relationships with data flow |
| Code Skeleton | Production-ready Python code with error handling |
| Endpoint Coverage | Per-endpoint documentation quality score |
| Documentation Issues | 16 types of problems found in source docs (contradictions, missing examples, etc.) |

**How it's used:**
- **MCP**: `get_api_lifecycle` tool returns the full blueprint; all search tools inject compact lifecycle context (auth, prerequisites, errors) into results
- **Web chat**: RAG automatically enriches LLM context with lifecycle data for better answers
- **UI**: results viewable in a dedicated modal, downloadable as JSON

**Self-validation**: generated analysis goes through LLM validation + correction loop (up to 3 retries) to ensure completeness and consistency.

### RAG Chat

LLM-powered answers grounded in documentation with anti-hallucination guarantees:

- **Hybrid search**: vector (pgvector cosine) + BM25 full-text + RRF fusion (0.7/0.3 weights)
- **Query classification**: auto-routes to specialized prompts (overview, technical, code, comparison, troubleshooting)
- **Query decomposition**: complex questions split into 2-4 sub-queries, searched in parallel
- **Gemini-based reranking**: 20 candidates → top 10 via LLM relevance scoring
- **Small-to-big expansion**: search by small chunks, expand to full sections in context
- **LLM metadata enrichment**: doc_type + entities per chunk for topic-aware retrieval
- **Streaming**: SSE (token-by-token) with source attribution
- **Web search augmentation**: fallback to web when docs insufficient

### Frontend

Web UI: landing page, RAG chat, document management, product catalog, analytics dashboard, admin panel.

- React 19 + TypeScript + Vite
- Markdown rendering with syntax highlighting
- File upload with TUS protocol (resumable)
- Real-time ingestion progress (animated status badges + timing debug panel)
- Light/dark theme, i18n (EN/RU)

### Monitoring

Full observability stack with 9 Grafana dashboards and 10 alert rules:

- **Dashboards**: Overview, System Health, Ingestion Pipeline, Document Audit, Queue Monitor, AI Chat, Search Quality, MCP Tools, Alerts & SLA
- **Alerts**: High error rate, high latency, DB pool saturation, service down, ingestion failures, chat errors, S3/MinIO failures
- **Dual-stack**: Loki + structlog (application logs) + Prometheus + node-exporter + cAdvisor (system/container metrics)

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI + uvicorn |
| MCP | FastMCP (Python MCP SDK), Streamable HTTP |
| Database | PostgreSQL 16 + pgvector (HNSW cosine) + BM25 (tsvector/GIN) |
| Embeddings | Gemini Embedding 2 (1024 dims, L2-normalized) |
| LLM (chat) | Gemini 2.5 Pro (main), Gemini 2.5 Flash (auxiliary) |
| LLM (metadata) | Gemini 2.5 Flash (classification, reranking, OCR, query rewrite) |
| Object Storage | MinIO (S3-compatible) |
| Cache & Queue | Redis 7 + Celery |
| Frontend | React 19 + TypeScript + Vite |
| Reverse Proxy | nginx (SPA fallback, SSE support, TUS uploads) |
| Monitoring | Grafana 11.6 + Loki 3.4 + Promtail + Prometheus 3.2 |
| Host Metrics | Node Exporter 1.9 + cAdvisor 0.51 |
| Containers | Docker Compose (12 services) |

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.11+ (for local backend development)
- Node.js 18+ (for local frontend development)

### Run the full stack

```bash
git clone <repo-url>
cd lexiro
cp .env.example .env    # adjust settings if needed
docker compose up -d
```

Services:

| Service | URL |
|---------|-----|
| Web UI | http://localhost |
| API | http://localhost:8000 |
| API docs (Swagger) | http://localhost:8000/docs |
| MCP endpoint | http://localhost:8000/mcp |
| Grafana | http://localhost:3000 |
| Prometheus | http://localhost:9090 |
| MinIO console | http://localhost:9001 |

### Connect MCP to Cursor

Every MCP connection requires an API key. Generate one in the admin panel
(**Settings → API Keys**) or use the pre-seeded key from `.env`.
Keys use the `ipx_` prefix.

Add to your project's `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "lexiro": {
      "url": "http://localhost:8000/mcp",
      "headers": {
        "Authorization": "Bearer ipx_your_api_key_here"
      }
    }
  }
}
```

For the hosted version at [lexiro.io](https://lexiro.io):

```json
{
  "mcpServers": {
    "lexiro": {
      "url": "https://lexiro.io/mcp",
      "headers": {
        "Authorization": "Bearer ipx_your_api_key_here"
      }
    }
  }
}
```

> **Authentication**: The MCP endpoint validates the API key on every request.
> The key must belong to an active tenant with `is_active = true`.
> Invalid or missing keys receive a `401` JSON-RPC error.

Then ask your AI assistant:

```
How do I open a door via HikCentral HTTP API?
```

### Local development

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Frontend
cd frontend
npm install
npm run dev

# Tests
cd backend
pytest tests/ -v
```

## Architecture Docs

Detailed architecture documentation is in the [`architecture/`](architecture/) directory:

| Document | Description |
|----------|-------------|
| [PLAN.md](architecture/PLAN.md) | Architecture overview, tech stack, implementation phases |
| [API.md](architecture/API.md) | REST API endpoints, MCP tools, authentication |
| [DATABASE.md](architecture/DATABASE.md) | Database schema, indexes, vector search, BM25 |
| [FLOWS.md](architecture/FLOWS.md) | Ingestion pipeline (9 steps), RAG chat flow, E2E flows |
| [PROMPT_ROUTING.md](architecture/PROMPT_ROUTING.md) | Query classification, per-type system prompts |
| [DEPLOYMENT.md](architecture/DEPLOYMENT.md) | Docker Compose, environment config, CI/CD |
| [MONITORING.md](architecture/MONITORING.md) | Grafana dashboards, alert rules, structured logging |
| [DESIGN_SYSTEM.md](architecture/DESIGN_SYSTEM.md) | Frontend design system, components, theming |
| [MONETIZATION.md](architecture/MONETIZATION.md) | Pricing tiers, per-model billing, two-sided marketplace |
| [INFRASTRUCTURE_COSTS.md](architecture/INFRASTRUCTURE_COSTS.md) | Unit economics, COGS analysis, break-even |
| [MARKET_RESEARCH.md](architecture/MARKET_RESEARCH.md) | Market sizing, competitive analysis, TAM/SAM/SOM |
| [GTM_STRATEGY.md](architecture/GTM_STRATEGY.md) | Go-to-market strategy, launch phases |
| [PARTNERSHIP_MARKETING.md](architecture/PARTNERSHIP_MARKETING.md) | Vendor partnership program |
| [BRAND.md](architecture/BRAND.md) | Brand platform, naming, visual identity, risk analysis |
| [BRAND_SLOGANS.md](architecture/BRAND_SLOGANS.md) | Taglines, slogans, messaging |
| [CONTENT_PLAN.md](architecture/CONTENT_PLAN.md) | Documentation sources, vendor priorities, ingestion roadmap |
| [CONTENT_SOURCES.md](architecture/CONTENT_SOURCES.md) | Verified import URLs, link verification log, quick start |
| [BACKLOG.md](architecture/BACKLOG.md) | Feature backlog, priorities, roadmap |

## License

Proprietary. All rights reserved.
