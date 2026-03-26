# Lexiro

> **Complex docs. Simple code.**
>
> *From documentation to code. Instantly.*

Lexiro is a platform that transforms chaotic product documentation (PDF, Swagger/OpenAPI, Markdown, web pages, Protobuf) into a structured knowledge base with semantic search — enabling AI coding assistants to write accurate integration code via RAG + MCP.

## Why

Developers integrating physical security and IoT products waste hours reading vendor documentation: 180-page PDFs with no search, scattered Swagger specs, outdated SDK examples. Lexiro indexes it all and serves relevant documentation to your AI assistant in real time.

## Project Structure

```
ipcodex/
├── backend/              Python backend (FastAPI + Celery)
│   ├── app/
│   │   ├── mcp/          MCP server — AI coding assistant integration
│   │   ├── chat/         RAG chat with LLM
│   │   ├── ingestion/    Document ingestion pipeline
│   │   ├── search/       Semantic search (pgvector)
│   │   └── ...
│   └── tests/            Unit + integration tests (Testcontainers)
├── frontend/             React SPA (TypeScript + Vite)
├── architecture/         Architecture docs, API spec, DB schema
├── promo/                Landing pages and marketing materials
├── monitoring/           Grafana + Loki + Promtail configs
├── scripts/              Utility scripts (Ollama entrypoint, etc.)
└── docker-compose.yml    Full stack: API, worker, DB, Redis, MinIO, Ollama, Grafana
```

## Components

### MCP Server

The core of Lexiro — an MCP server that gives AI coding assistants (Cursor, Windsurf, GitHub Copilot) instant access to indexed product documentation.

3 tools: `search_documentation`, `get_api_endpoint`, `list_products`.

See **[MCP Server README](backend/app/mcp/README.md)** for tool reference, quick start, and connection instructions.

### Backend (FastAPI)

REST API for document management, ingestion, search, and RAG chat.

- **Ingestion pipeline** — PDF (with OCR), Swagger/OpenAPI, Markdown, Protobuf, web pages
- **Semantic search** — pgvector with HNSW index, cosine similarity
- **RAG chat** — LLM-powered answers grounded in documentation
- **Async workers** — Celery for background ingestion and monitoring tasks

### Frontend (React)

Web UI for uploading documents, searching the knowledge base, and chatting with the RAG assistant.

- TypeScript + Vite + React
- Markdown rendering with syntax highlighting
- File upload with TUS protocol (resumable)
- i18n support (EN/RU)

### Monitoring

Grafana dashboards with Loki log aggregation via Promtail.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI + uvicorn |
| MCP | FastMCP (Python MCP SDK), Streamable HTTP |
| Database | PostgreSQL 16 + pgvector (HNSW cosine similarity) |
| Embeddings | Local models (sentence-transformers) / OpenAI |
| LLM | Ollama (qwen2.5-coder) / OpenAI-compatible API (Gemini) |
| Object Storage | MinIO (S3-compatible) |
| Cache & Queue | Redis + Celery |
| Frontend | React + TypeScript + Vite |
| Monitoring | Grafana + Loki + Promtail |
| Containers | Docker Compose |

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.12+ (for local backend development)
- Node.js 18+ (for local frontend development)

### Run the full stack

```bash
git clone <repo-url>
cd ipcodex
cp .env.example .env    # adjust settings if needed
docker compose up -d
```

**LLM Provider Selection:**

By default, the stack uses **Google Gemini API** (`LLM_PROVIDER=gemini`). You can switch to alternative providers:

```bash
# Option 1: Google Gemini (default)
echo "GEMINI_API_KEY=AIza_your_key" >> .env
echo "LLM_PROVIDER=gemini" >> .env

# Option 2: BotHub aggregator API (https://bothub.ru)
echo "BOTHUB_API_KEY=your_bothub_key" >> .env
echo "BOTHUB_LLM_MODEL=gpt-4.5-turbo" >> .env
echo "LLM_PROVIDER=bothub" >> .env

# Option 3: Local Ollama (development only)
echo "LLM_PROVIDER=ollama" >> .env
echo "LLM_MODEL=qwen2.5-coder:7b" >> .env
```

Then restart:
```bash
docker compose down
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
| MinIO console | http://localhost:9001 |

### Connect MCP to Cursor

Add to `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "lexiro": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

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
| [DATABASE.md](architecture/DATABASE.md) | Database schema, indexes, vector search |
| [FLOWS.md](architecture/FLOWS.md) | Ingestion pipeline, supported formats, E2E flows |
| [DEPLOYMENT.md](architecture/DEPLOYMENT.md) | Docker Compose, environment config, CI/CD |
| [MONETIZATION.md](architecture/MONETIZATION.md) | Pricing tiers, billing, marketplace strategy |
| [MARKET_RESEARCH.md](architecture/MARKET_RESEARCH.md) | Market sizing, competitive analysis |

## License

Proprietary. All rights reserved.
