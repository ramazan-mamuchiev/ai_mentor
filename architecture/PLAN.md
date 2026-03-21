# IPCodex SaaS Platform — Architecture & Implementation Plan

> **Status**: Draft v1.0 — March 15, 2026
> **Author**: Oleg Voitekhovich

---

## Documentation Map

| Document | Description | ~Lines |
|----------|-------------|:------:|
| **PLAN.md** (this file) | Architecture overview, key decisions, project structure, tech stack, implementation phases | ~370 |
| [DATABASE.md](DATABASE.md) | Database schema (all tables), indexes, RLS policies, vector search query, sharing model | ~340 |
| [API.md](API.md) | REST API endpoints, MCP tools, API key flows, registration flows, error handling | ~310 |
| [MONETIZATION.md](MONETIZATION.md) | Developer tiers, vendor tiers, billing units, marketplace strategy, revenue streams | ~270 |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Docker Compose, .env config, S3 structure, security, Celery Beat, testing, CI/CD, logging | ~370 |
| [FLOWS.md](FLOWS.md) | Ingestion pipeline, supported formats, E2E flows (developer, vendor docs, firmware) | ~190 |
| [MARKET_RESEARCH.md](MARKET_RESEARCH.md) | Market sizing, competitive analysis, pricing rationale, revenue projections | ~270 |
| [INFRASTRUCTURE_COSTS.md](INFRASTRUCTURE_COSTS.md) | Per-component cost breakdown, unit economics, break-even, revenue vs infra cross-check | ~460 |
| [PARTNERSHIP_MARKETING.md](PARTNERSHIP_MARKETING.md) | Go-to-market strategy: vendor partnerships, co-marketing playbook, target vendors, KPIs | ~430 |
| [GTM_STRATEGY.md](GTM_STRATEGY.md) | AI-first positioning, messaging framework, 12-month execution roadmap, channel priorities, budget | ~400 |
| [MONITORING.md](MONITORING.md) | Monitoring stack (Grafana + Loki + Promtail), dashboards, alert rules, structured logging | ~200 |
| [BRAND_SLOGANS.md](BRAND_SLOGANS.md) | Competitor slogan analysis, 28 IPCodex slogan candidates (EN/RU), next steps for partner review | ~130 |
| [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md) | Design system: colors, typography, icons, components, logo, animations, UI/UX competitor analysis | ~310 |

---

## Product Summary

**IPCodex** is a commercial SaaS platform that transforms chaotic product documentation — for both hardware devices (IP cameras, access controllers, intercoms, sensors) and software platforms (VMS, PSIM, IoT platforms, SDKs) — into a structured knowledge base with semantic search, and serves as a distribution hub for firmware, SDKs, and tools — enabling AI coding assistants (Cursor, Windsurf, GitHub Copilot) to write accurate integration code via RAG + MCP.

**Target scale**: 1000+ developer tenants + 100+ device vendors. Two-sided marketplace with hybrid monetization (subscription + overage for developers, tiered plans for vendors).

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              CLIENTS                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │ Cursor / IDE  │  │   Web UI     │  │  REST API    │  │ Vendor     │ │
│  │ MCP over HTTP │  │  React SPA   │  │  (3rd-party) │  │ Portal API │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └─────┬──────┘ │
└─────────┼─────────────────┼─────────────────┼────────────────┼─────────┘
          │ API Key         │ JWT (future)    │ API Key        │ Vendor Key
          ▼                 ▼                 ▼                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        API GATEWAY (FastAPI)                             │
│  Request Logging Middleware (request_id, access log)                    │
│  → Auth → Rate Limiter (Redis) → Router                                │
└──┬──────────┬──────────────┬──────────────┬─────────────────────────────┘
   │          │              │              │
┌──▼───┐ ┌───▼────┐  ┌──────▼───────┐ ┌───▼──────────┐
│ MCP  │ │  RAG   │  │ REST Routers │ │Vendor Routers│
│Server│ │  Chat  │  │ /api/v1/...  │ │/vendor/v1/.. │
│ /mcp │ │  SSE   │  │ docs, upload │ │  (future)    │
└──┬───┘ └───┬────┘  └──────┬───────┘ └──────────────┘
   │         │              │
   └────┬────┘──────────────┘
        ▼
┌────────────────────────┐          ┌──────────────────────┐
│    PostgreSQL 16       │          │       Redis          │
│  + pgvector (HNSW)     │          │  Celery broker       │
│  products, chunks,     │          │  TUS upload state    │
│  chat_sessions,        │          │  rate limits         │
│  upload_sessions       │          └──────────┬───────────┘
└────────────────────────┘                     │
        │                                      ▼
        │                       ┌──────────────────────────┐
        │                       │  Celery Worker + Beat    │
        │                       │  ingest: chunk → embed   │
        │                       │  cleanup: expired uploads│
        │                       │  monitoring: health      │
        │                       └──────────────┬───────────┘
        │                                      │
        │                 ┌────────────────────┼────────────────┐
        │                 ▼                    ▼                ▼
        │       ┌──────────────────┐ ┌──────────────┐ ┌────────────────┐
        │       │  MinIO / S3      │ │  Gemini 2.5  │ │  Loki +        │
        │       │  documents       │ │  Flash (LLM) │ │  Grafana       │
        └──────▶│  uploads         │ │  via OpenAI  │ │  (monitoring)  │
                └──────────────────┘ └──────────────┘ └────────────────┘
```

---

## Key Architectural Decisions

### Multi-tenancy
- Every tenant (organization) sees **only their own data**
- `tenant_id` column on `devices`, `documents`, `chunks` tables
- Row Level Security (RLS) in PostgreSQL as defense-in-depth — see [DATABASE.md](DATABASE.md#rls-policies)
- `tenant_id` denormalized into `chunks` table to avoid JOINs during vector search (critical for performance)

### MCP over HTTP/SSE (not stdio)
- Standard MCP stdio transport = 1 process per user (not scalable)
- HTTP/SSE transport = 1 server serves 1000+ concurrent users
- Endpoint: `POST /mcp/message` (JSON-RPC) + `GET /mcp/sse` (Server-Sent Events)
- Each SSE connection authenticated via API Key in `Authorization` header
- Stateless: `tenant_id` resolved from every request

### Authentication
- **API Key** for MCP connections and REST API: `ipx_a1b2c3d4e5f6...`
- **JWT** for Web UI (future phase)
- Keys stored as `SHA-256(key)` — only prefix `ipx_a1b2` kept for identification
- One tenant can have multiple keys with different scopes (search, ingest, admin)
- Full details: [API.md — API Key Flow](API.md#api-key-flow)

### Rate Limiting
- Redis-based sliding window per tenant
- Limits depend on subscription tier — see [MONETIZATION.md](MONETIZATION.md)
- Returns `429 Too Many Requests` with `Retry-After` header

### Background Ingestion
- Chunking + embedding is CPU/memory intensive → offloaded to Celery workers
- API returns immediately with `job_id` for status polling
- Workers are horizontally scalable (N workers for throughput)
- Multi-format pipeline: [FLOWS.md — Ingestion Pipeline](FLOWS.md#ingestion-pipeline-async-via-celery-multi-format)

### Dual Auth: Tenants vs Vendors
- Two separate API key tables: `api_keys` (tenants/developers) and `vendor_api_keys` (vendors)
- Key prefix distinguishes type: `ipx_` for tenants, `ipv_` for vendors
- Auth middleware resolves key type first, then routes to tenant context or vendor context
- Vendor keys grant access only to `/vendor/v1/...` routes
- Tenant keys grant access to `/api/v1/...` routes and MCP endpoints
- JWT (future) for both tenant Web UI and vendor dashboard

### Usage Metering & Billing Pipeline
- ✅ Every billable API call writes to `usage_log` table (async, non-blocking, fire-and-forget)
- ✅ `usage_log` is partitioned by month (`PARTITION BY RANGE (created_at)`) for scalability and archival
- ✅ Celery Beat task `ensure_usage_partitions` auto-creates partitions 2 months ahead
- ✅ Dual cost tracking: `cogs_usd` (our LLM/infra cost) + `charge_usd` (user-facing price) per record
- ✅ Full prompt decomposition: `query_tokens`, `context_tokens`, `history_tokens`, `system_prompt_tokens` — enables billing formula changes without data loss
- ✅ LLM token extraction: `prompt_tokens` and `completion_tokens` from OpenAI-compatible API (`stream_options: {"include_usage": True}`)
- ✅ Pricing module: `billing/pricing.py` with `MODEL_COGS` (real API prices) and `MODEL_CHARGE` (user-facing rates with margin)
- Planned: Redis counters for real-time rate limiting (sliding window per tenant)
- Planned: Stripe integration — subscriptions for base tier, metered billing for overage
- Planned: Spending alerts — email at 80%/100% quota
- Full pricing model: [MONETIZATION.md](MONETIZATION.md)

### RAG Chat (LLM-Powered Conversational Interface)
- AI chat with retrieval-augmented generation — answers grounded in indexed documentation
- SSE streaming: tokens streamed to client as they are generated
- Source attribution: each response includes source chunks with similarity scores
- Auto-detection of product from user query (no explicit filter required)
- **LLM query rewriting**: follow-up questions are reformulated into standalone queries via a lightweight LLM call (Gemini with `reasoning_effort=none`, `temperature=0`). Self-contained questions pass through unchanged. Fallback to original query on error
- **Similarity threshold**: `rag_min_similarity` (default 0.35) filters out low-relevance chunks after retrieval
- History-aware: last N messages included in LLM context for multi-turn conversations
- **History limits**: `rag_history_messages` (default 6), `rag_history_max_tokens` (default 8,000) — trims oldest messages first to stay within budget
- **Structured grounding prompt** (XML-tagged `<role>`, `<constraints>`, `<instructions>`, `<output_format>`):
  - 9 grounding constraints following Google's recommendations
  - Strict factual grounding: API details (endpoints, params, URLs) must come from context only
  - Code generation allowed in any language using documented API details + general programming knowledge
  - Mandatory response in the user's language
  - Summary section for overview questions
- **Prompt architecture** (5-part message sequence for Gemini implicit caching):
  1. System message — `SYSTEM_PROMPT` (static, cacheable)
  2. User message — `<documentation_context>` with retrieved chunks (cacheable for same query)
  3. Assistant ack — "Understood. I will answer strictly based on the documentation context provided above."
  4. History messages — recent conversation turns (up to 6 messages / 8,000 tokens)
  5. User query — with anchor phrase: "Based on the documentation above, answer the following question:"
- **Persistent debug/analytics**: every assistant response saves detailed metrics to `chat_message_analytics` table (LLM params, timing, RAG quality, rewrite_ms). Survives page reload and enables future admin search, billing reconciliation, and quality analysis
- **Billing audit**: every chat completion writes to `usage_log` with full prompt decomposition (`query_tokens`, `context_tokens`, `history_tokens`, `system_prompt_tokens`) plus `cogs_usd` (our LLM cost) and `charge_usd` (user-facing price)
- Implementation: `chat/router.py`, `chat/rag.py`, `llm/client.py`, `billing/usage_writer.py`

### Search Analytics (MCP & API Observability)
- Every MCP tool call (`search_documentation`, `get_api_endpoint`, `list_products`) records a `search_analytics` entry
- Tracks: query, product/version filters, result count, top similarity, duration, embedding model
- Separate from chat analytics — different metric set, no LLM involvement
- **Billing audit**: MCP search/endpoint calls also write to `usage_log` with `query_tokens`, `response_tokens`, `cogs_usd`, `charge_usd`
- Enables: search quality analysis, popular query tracking, billing verification, vendor analytics (future)
- Fire-and-forget writes — analytics failures never block the search response
- Implementation: `mcp/server.py`, `models.py` (`SearchAnalytics`), `billing/usage_writer.py`
- Schema: [DATABASE.md — search_analytics](DATABASE.md#current-schema-implemented)

### LLM Provider
- **Tiered model strategy**: different developer tiers use different LLM models
- **Gemini 2.5 Flash** (default): primary production model via OpenAI-compatible API, thinking disabled (`reasoning_effort=none`) for speed and cost efficiency
- **Ollama** (local): development fallback only, zero API cost
- **OpenAI-compatible API**: any endpoint that implements the OpenAI chat completions API
- Provider selected via `LLM_PROVIDER` env variable (`ollama` | `openai`)
- Model routing by tier: Free/Pro → Gemini Flash, Team/Enterprise → Opus 4.6
- Streaming support for both providers (Ollama JSON lines, OpenAI SSE)
- **Per-model billing**: input + output charged separately at model-specific rates
- Configurable: model, temperature, max_tokens, timeout, reasoning_effort

**Production models:**

| Model | Provider | Input / Output (per 1M tokens) | Cost per query | Tier |
|-------|----------|:------------------------------:|:--------------:|------|
| Gemini 2.5 Flash | Google AI Studio | $0.30 / $2.50 | ~$0.004 | Free, Pro (default) |
| Claude Opus 4.6 | Anthropic | $5.00 / $25.00 | ~$0.045 | Team, Enterprise, Pro (option: 100/mo) |
| Ollama | Local | $0 (GPU ~$200-400/mo) | ~$0 | Development fallback only |

Opus 4.6 serves as a premium **anchor product** — its superior quality drives tier upgrades while per-model billing protects margins. See [MONETIZATION.md](MONETIZATION.md#ai-model-tiers) for tier mapping and [INFRASTRUCTURE_COSTS.md](INFRASTRUCTURE_COSTS.md#26-llm-api-for-rag-chat) for detailed cost analysis.

### TUS Resumable Upload
- TUS v1.0.0 protocol for large file uploads (up to 5 GB)
- Chunked upload directly to S3 via multipart upload
- Pause/resume support — upload state persisted in `upload_sessions` table
- Incremental SHA-256 hash computed during upload (state serialized between chunks)
- Auto-expiration of incomplete uploads (`tus_upload_ttl_hours`, default 24h)
- Celery Beat task cleans up expired sessions and aborts S3 multipart uploads
- Quota enforcement: per-file, per-product, and global storage limits
- Implementation: `uploads/router.py`, `uploads/quota.py`

### Archive Ingestion
- Upload a single archive containing multiple documentation files
- Supported archive formats: ZIP, 7z, tar, tar.gz, tar.bz2, tar.xz, RAR
- Each file inside the archive is detected and ingested independently
- Supported file types inside archives: `.md`, `.json`, `.yaml`, `.yml`, `.pdf`, `.proto`, `.txt`, `.wsdl`, `.xml`
- Archive size limit: `MAX_ARCHIVE_SIZE_MB` (default 350 MB)
- Implementation: `documents/archive.py`, `documents/router.py`

### Monitoring & Observability
- **Grafana + Loki + Promtail** — log-based monitoring (no Prometheus)
- 9 Grafana dashboards: overview, system, ingestion, doc audit, queue, AI chat, search, MCP tools, alerts/SLA
- 8 alert rules: error rate, latency, DB pool, service down, ingestion failures, chat errors, Ollama health
- Structured JSON logging via `structlog` with `request_id` correlation
- Request logging middleware: timing, status codes, active request count
- Full details: [MONITORING.md](MONITORING.md)

### Embedding Strategy
- **OpenAI `text-embedding-3-small`** (1536 dims) for cloud — best quality
- **`intfloat/multilingual-e5-small`** (1024 dims) for local / offline — default for development
- Provider selected via `EMBEDDING_PROVIDER` env variable (`local` | `openai`)
- Fixed `vector(1024)` column in pgvector for local; `vector(1536)` for OpenAI
- E5 models use instruction-prefixed queries (`query:` / `passage:`) for better retrieval

### Supported Document Formats

All formats are normalized to **chunks** in pgvector. The original file is preserved in S3 in its native format.

| Format | Extensions | Parser | Billable Units | Internal Cost |
|--------|-----------|--------|:-:|-----|
| Markdown | `.md` | Direct H1/H2/H3 chunking | **1** | ~$0.001 |
| Swagger / OpenAPI 2.0/3.x | `.json`, `.yaml` | Structural: 1 chunk per endpoint | **1** | ~$0.001 |
| Postman Collection v2.1 | `.json` | Convert requests → endpoint docs | **1** | ~$0.001 |
| PDF (text-based) | `.pdf` | PyMuPDF text extract → chunking | **2** | ~$0.005 |
| PDF (scanned / OCR) | `.pdf` | EasyOCR → text → chunking | **5** | ~$0.02 |
| Web page | URL | httpx + BeautifulSoup → cleaning → chunking | **2** | ~$0.003 |
| Protobuf | `.proto` | Service/method/message extraction → Markdown | **1** | ~$0.001 |

Full details: [FLOWS.md — Supported Document Formats](FLOWS.md#supported-document-formats)

### Internationalization (i18n)
- Frontend uses `react-i18next` with `i18next-browser-languagedetector`
- Default language: **en** (English) — used as the reference locale and fallback
- Translation files: flat JSON in `frontend/src/locales/{lang}.json` (one file per language)
- Language detection order: `localStorage` → browser `navigator` preference
- User's language choice persisted in `localStorage` under `ipcodex-lang` key
- All UI strings extracted to translation keys — no hardcoded text in components
- Adding a new language requires only a new `{lang}.json` file; tests auto-discover all locale files and validate structure, key completeness, and interpolation placeholder consistency against the reference locale

### Vector Search
- pgvector HNSW index with cosine similarity
- `ef_construction=128`, `m=16` for quality/speed balance
- Tenant-scoped queries: `WHERE tenant_id = $tenant AND ... ORDER BY embedding <=> $query LIMIT $n`
- Optional filters: device, firmware version
- Optional cross-encoder reranking for top results (Phase 4+)
- Full query: [DATABASE.md — Vector Search Query](DATABASE.md#vector-search-query-tenant-isolated)

### Vector Search Scaling Strategy

Three-stage approach to avoid over-engineering at launch while having a clear path to scale:

| Stage | Trigger | Solution | Capacity |
|-------|---------|----------|:--------:|
| **1. Start** | 0–2M chunks, 0–500 tenants | pgvector, single HNSW index | ~64 GB RAM server |
| **2. Growth** | 2–10M chunks, 500–2000 tenants | pgvector + HASH partitioning (32–64 partitions) | ~128 GB RAM server |

At projected Year 3 scale (1,000 developers + 60 vendors ≈ 3M chunks), Stage 2 provides sufficient headroom (up to 10M chunks). A dedicated vector database (Qdrant, Milvus) would only be needed if the platform grows to 10,000+ customers — a decision to revisit if and when that growth materializes.

Full partitioning DDL and details: [DATABASE.md — Vector Search Scaling](DATABASE.md#vector-search-scaling)

---

## Project Structure

```
ipcodex/
  backend/
    app/
      main.py                # FastAPI app + FastMCP registration + lifespan
      config.py              # Settings via pydantic-settings (env vars)
      models.py              # SQLAlchemy ORM models (all tables)
      database.py            # Async engine, session factory, connection pool
      celery_app.py          # Celery configuration (Redis broker) + beat_schedule
      s3.py                  # S3/MinIO client (upload, download, presigned URLs)
      logging_config.py      # structlog setup, JSON + file handlers, rotation

      chat/                  # ✅ RAG Chat with LLM
        router.py            # REST API: sessions CRUD, send message (SSE streaming)
        rag.py               # RAG service: LLM query rewrite, structured prompt building, similarity filtering, grounding
        schemas.py           # Pydantic: CreateSessionRequest, SessionResponse, SourceInfo, etc.

      llm/                   # ✅ LLM provider abstraction
        client.py            # stream_chat_completion (Ollama / OpenAI-compatible), health check

      documents/
        router.py            # Upload file/URL/archive, list, status, download, delete, reindex
        archive.py           # ✅ Archive extraction: ZIP, 7z, tar, tar.gz, tar.bz2, tar.xz, RAR
        schemas.py           # Pydantic: IngestResponse, DocumentStatus, DocumentListItem

      uploads/               # ✅ TUS resumable upload
        router.py            # TUS v1.0.0: POST/HEAD/PATCH/DELETE, multipart S3 upload
        quota.py             # Storage quota enforcement (per-file, per-product, global)

      search/
        service.py           # Vector search (pgvector cosine similarity, heading_path match)

      mcp/
        server.py            # MCP tools: search_documentation, get_api_endpoint, list_products

      billing/               # ✅ Usage metering & pricing (Phase 2 partial)
        __init__.py
        pricing.py           # MODEL_COGS (LLM API cost) + MODEL_CHARGE (user-facing price)
        usage_writer.py      # Async fire-and-forget writer for usage_log audit table

      reindex/               # ✅ Background reindexing operations
        __init__.py
        router.py            # REST API: create/list/cancel reindex jobs
        schemas.py           # Pydantic: ReindexRequest, ReindexJobResponse
        service.py           # Reindex orchestration: reingest or re-embed documents

      ingestion/
        chunker.py           # Chunking logic (split/merge/overlap by token count)
        embedder.py          # Embedding abstraction (E5 local + OpenAI)
        pipeline.py          # Orchestration: detect format → convert → parse → chunk → embed → store
        converters/
          pdf.py             # PDF → Markdown (pymupdf4llm + optional EasyOCR)
          swagger.py         # Swagger/OpenAPI → Markdown (structured endpoints)
          web.py             # URL → Markdown (Swagger UI detection, Crawl4AI fallback)
          proto.py           # ✅ Protobuf → Markdown (services, methods, messages)
        parsers/
          markdown.py        # Markdown → sections by H1/H2/H3 headers
          swagger.py         # OpenAPI → 1 section per endpoint

      middleware/            # ✅ Request logging
        request_logging.py   # RequestLoggingMiddleware: request_id, access log, timing

      # --- Planned (not yet implemented) ---
      auth/                  # API Key + JWT auth (Phase 2)
      tenants/               # Tenant CRUD (Phase 2)
      billing/stripe.py      # Stripe subscriptions + metered billing (Phase 5)
      billing/alerts.py      # Spending alerts: email at 80%/100% quota (Phase 5)
      billing/limits.py      # Rate limiting + quota enforcement (Phase 2)
      vendor/                # Vendor portal + analytics (Phase 4)
      artifacts/             # Firmware/SDK distribution (Phase 4b)
      importers/             # Custom vendor importers (Phase 6)

    db/
      schema.sql             # Full DDL (tables, indexes)

    scripts/
      upload_document.py     # CLI: upload document or archive to API
      check_documents.py     # CLI: check document/chunk counts and DB health
      convert_to_md.py       # CLI: offline document → Markdown conversion

    tests/
      conftest.py            # Shared fixtures: Testcontainers PostgreSQL, mock embedder
      unit/                  # ~25 test files: chunker, embedder, parsers, converters,
                             #   chat, LLM, TUS, quota, S3, RAG, reindex, archives
        converters/          # PDF, Swagger, web converter tests
      integration/           # ~13 test files: pipeline, search, MCP tools, chat,
                             #   TUS upload, archives (7z, tar, RAR), reindex, dedup
      smoke/                 # Real embedding + pgvector smoke test

    Dockerfile
    requirements.txt
    pyproject.toml

  frontend/
    src/
      pages/                 # ✅ LandingPage, ChatApp (route-level components)
      components/            # ChatWindow, FileUpload, SessionList, Layout, etc.
      hooks/                 # useChat (SSE streaming), useTheme
      api/                   # HTTP client, chat API
      locales/               # en.json, ru.json (i18n)
      styles/                # globals.css, chat.css, landing.css
      App.tsx                # Router (react-router-dom Routes)
      main.tsx               # BrowserRouter + App
    package.json
    vite.config.ts

  monitoring/                # ✅ Grafana + Loki + Promtail
    loki-config.yml
    promtail-config.yml
    grafana/provisioning/    # 9 dashboards, 8 alert rules, Loki datasource

  architecture/              # Architecture documentation (this directory)
  promo/                     # Landing pages and marketing materials
  scripts/                   # Utility scripts (Ollama entrypoint)

  docker-compose.yml         # Full stack: API, Worker, PostgreSQL, Redis, MinIO,
                             #   Ollama, Frontend, Loki, Promtail, Grafana
  docker-compose.dev.yml     # Lightweight: PostgreSQL only (for local development)
  .env.example               # Configuration template
  README.md                  # Project overview + quick start
```

---

## Technology Stack

| Layer | Technology | Status |
|-------|-----------|:------:|
| API Gateway | FastAPI + uvicorn | ✅ |
| MCP Server | FastMCP (Python MCP SDK), Streamable HTTP | ✅ |
| LLM (cloud) | Gemini 2.5 Flash (default, `reasoning_effort=none`) + Claude Opus 4.6 (Team/Enterprise) | ✅ |
| LLM (local) | Ollama — development fallback only | ✅ |
| Database | PostgreSQL 16 + pgvector (HNSW index) | ✅ |
| Cache / Queue | Redis 7 (Celery broker, TUS state) | ✅ |
| Object Storage | MinIO / AWS S3 | ✅ |
| Background Jobs | Celery + Redis broker + Celery Beat (periodic) | ✅ |
| Embedding (local) | intfloat/multilingual-e5-small (1024 dims) | ✅ |
| Embedding (cloud) | OpenAI text-embedding-3-small (1536 dims) | ✅ |
| ORM | SQLAlchemy 2.0 (async) | ✅ |
| Upload Protocol | TUS v1.0.0 (resumable, chunked to S3 multipart) | ✅ |
| Archive Support | py7zr, rarfile, zipfile, tarfile | ✅ |
| Monitoring | Grafana 11.6 + Loki 3.4 + Promtail 3.4 | ✅ |
| Logging | structlog (JSON) + request_id middleware | ✅ |
| Frontend | React + TypeScript + Vite | ✅ |
| Routing | react-router-dom v7 (`/` landing, `/app` chat) | ✅ |
| Landing Page | Marketing page with i18n, responsive design | ✅ |
| Internationalization | i18next + react-i18next (en, ru) | ✅ |
| Theme | Light/dark theme (CSS variables + data-theme) | ✅ |
| File Integrity | hashlib SHA-256 (incremental during TUS upload) | ✅ |
| Migrations | Alembic | Planned |
| Auth | API Key (SHA-256 hashed) + JWT (future) | Planned |
| Billing (audit) | usage_log (partitioned), pricing module, COGS/charge tracking | ✅ |
| Billing (payments) | Stripe (subscriptions + metered usage records) | Planned |
| Antivirus | ClamAV (clamd TCP socket) | Planned |

---

## Implementation Phases

### Phase 1 — Core (Working Search) ✅

| # | Task | Status | Key Files |
|---|------|:------:|-----------|
| 1 | Infrastructure: Docker Compose + PostgreSQL schema | ✅ | `docker-compose.yml`, `db/schema.sql` |
| 2 | Configuration + database layer + SQLAlchemy models | ✅ | `config.py`, `database.py`, `models.py` |
| 3 | Markdown chunker with tests | ✅ | `ingestion/chunker.py`, `tests/test_chunker.py` |
| 4 | Embedding abstraction (local E5 + OpenAI) with tests | ✅ | `ingestion/embedder.py`, `tests/test_embedder.py` |
| 5 | Ingestion pipeline + Celery task + multi-format converters | ✅ | `ingestion/pipeline.py`, `ingestion/converters/` |
| 6 | Vector search service | ✅ | `search/service.py`, `tests/test_search.py` |
| 6a | PDF converter (pymupdf4llm + optional OCR) | ✅ | `ingestion/converters/pdf.py` |
| 6b | Swagger/OpenAPI converter | ✅ | `ingestion/converters/swagger.py` |
| 6c | Web page converter (Swagger UI + Crawl4AI) | ✅ | `ingestion/converters/web.py` |
| 6d | Protobuf converter | ✅ | `ingestion/converters/proto.py` |
| 6e | Archive ingestion (ZIP, 7z, tar, RAR) | ✅ | `documents/archive.py` |

### Phase 1b — RAG Chat + Upload ✅

| # | Task | Status | Key Files |
|---|------|:------:|-----------|
| 6f | RAG Chat: LLM + retrieval + SSE streaming | ✅ | `chat/router.py`, `chat/rag.py`, `llm/client.py` |
| 6g | TUS resumable upload (up to 5 GB) | ✅ | `uploads/router.py`, `uploads/quota.py` |
| 6h | Monitoring: Grafana + Loki + Promtail (9 dashboards, 8 alerts) | ✅ | `monitoring/` |
| 6i | Request logging middleware | ✅ | `middleware/request_logging.py` |
| 6j | Frontend: React SPA (chat, upload, i18n, dark/light theme) | ✅ | `frontend/src/` |
| 6k | Landing page + react-router-dom routing (`/` landing, `/app` chat) | ✅ | `pages/LandingPage.tsx`, `pages/ChatApp.tsx`, `styles/landing.css`, `App.tsx` |

### Phase 2 — API + MCP + IDE Integration (partially done)

| # | Task | Status | Key Files |
|---|------|:------:|-----------|
| 7 | FastAPI application with routers | ✅ | `main.py`, routers |
| 8 | Dual API Key auth: tenant keys (`ipx_`) + vendor keys (`ipv_`) | Planned | `auth/` |
| 9 | Rate limiting middleware (Redis sliding window) | Planned | `billing/limits.py` |
| 10 | Usage metering: log every billable call (usage_log, partitioned) | ✅ | `billing/usage_writer.py`, `billing/pricing.py` |
| 10a | Quota check (per-tenant limits enforcement) | Planned | `billing/limits.py` |
| 11 | REST endpoints: documents, search, ingest, chat, upload | ✅ | all routers |
| 12 | MCP server with Streamable HTTP transport | ✅ | `mcp/server.py` |
| 13 | MCP tools (3): search_documentation, get_api_endpoint, list_products | ✅ | `mcp/server.py` |
| 14 | Cursor IDE integration testing | ✅ | `.cursor/mcp.json` |

### Phase 4 — Vendor Portal + Marketplace

| # | Task | Key Files |
|---|------|-----------|
| 15 | Vendor CRUD: registration, API key generation | `vendor/router.py`, `vendor/service.py` |
| 16 | Vendor document publishing API: bulk upload, firmware notification | `vendor/router.py`, `vendor/schemas.py` |
| 17 | Vendor analytics: daily aggregation Celery task + REST endpoints | `vendor/analytics.py`, `vendor/router.py` |
| 18 | Celery Beat configuration for periodic tasks | `celery_app.py` |

### Phase 4b — Firmware & Artifact Distribution

| # | Task | Key Files |
|---|------|-----------|
| 18a | Artifact upload/download endpoints + S3 storage | `artifacts/router.py`, `artifacts/service.py` |
| 18b | ClamAV antivirus integration + scan Celery task | `artifacts/scanner.py`, `artifacts/tasks.py` |
| 18c | SHA-256 checksums + changelog diff generation | `artifacts/service.py` |
| 18d | New firmware notification to subscribed developers | `artifacts/tasks.py` |
| 18e | Vendor storage quota enforcement per tier | `vendor/service.py`, `billing/limits.py` |
| 18f | Release notes auto-indexing (as searchable chunks) | `artifacts/tasks.py`, `ingestion/pipeline.py` |

### Phase 5 — Billing + Production Readiness

| # | Task | Status | Key Files |
|---|------|:------:|-----------|
| 19a | Usage audit log (partitioned, append-only, COGS + charge) | ✅ | `billing/usage_writer.py`, `db/schema.sql` |
| 19b | Pricing module (MODEL_COGS + MODEL_CHARGE, per-token) | ✅ | `billing/pricing.py` |
| 19c | LLM token extraction (prompt + completion from API) | ✅ | `llm/client.py` |
| 19d | Celery Beat: auto-create usage_log partitions | ✅ | `celery_app.py` |
| 19 | Stripe integration: subscriptions, usage records, webhooks | Planned | `billing/stripe.py`, `billing/webhooks.py` |
| 20 | Spending alerts: email at 80%/100% quota (Celery Beat hourly) | Planned | `billing/alerts.py` |
| 21 | Monthly overage calculation + Stripe reporting (Celery Beat) | Planned | `billing/tasks.py` |
| 22 | Database migrations (Alembic) | Planned | `db/migrations/`, `alembic.ini` |
| 23 | Production Docker config + Celery Beat service | `Dockerfile`, `docker-compose.prod.yml` |
| 24 | API documentation + README | auto-generated from FastAPI + `README.md` |
| 25 | Health checks, monitoring, observability | `/health`, `/ready` endpoints |

### Phase 6 — Custom Importers (Platinum)

| # | Task | Key Files |
|---|------|-----------|
| 26 | BaseImporter abstract class: crawl, parse, sync, diff detection | `importers/base.py` |
| 27 | Importer registry + Celery task for scheduled auto-sync | `importers/__init__.py`, `importers/tasks.py` |
| 28 | First reference importer (e.g., Hikvision ISAPI) | `importers/hikvision_isapi.py` |
| 29 | Vendor admin: configure importer schedule, view sync status | `vendor/router.py` |
| 30 | Change detection: diff new scrape vs previous → re-index only changed docs | `importers/base.py` |

### Phase 7 — Vector Search Scaling (triggered by growth)

| # | Task | Trigger | Key Changes |
|---|------|---------|-------------|
| 31 | pgvector HASH partitioning (32 partitions on `tenant_id`) | >2M chunks | `db/migrations/`, schema.sql |
| 32 | Split cross-tenant search into 2 queries (private + public) and merge in app | with partitioning | `search/service.py` |
| 33 | Self-hosted embedding model (replace OpenAI dependency) | production readiness | `ingestion/embedder.py`, Docker GPU worker |
| 34 | CDN (CloudFront) for firmware downloads | egress > 1 TB/mo | infrastructure config |

Details: [DATABASE.md — Vector Search Scaling](DATABASE.md#vector-search-scaling)

---

## Open Questions / TODO

### Technical
- [ ] Reranking strategy: cross-encoder model selection for top-N reranking
- [x] ~~Web UI technology: React + TypeScript SPA vs Next.js~~ → React + TypeScript SPA + Vite. Landing page: custom React page with i18n, responsive design, deployed at `/`; app at `/app` via react-router-dom v7
- [ ] On-premise deployment: Helm chart for Kubernetes
- [x] ~~Monitoring: Prometheus + Grafana vs cloud-native~~ → Grafana + Loki + Promtail (log-based, see [MONITORING.md](MONITORING.md))
- [ ] CDN for static assets and S3 presigned URLs
- [ ] Backup strategy: pg_dump schedule, S3 versioning
- [x] ~~AI Chat interface~~ → Implemented: RAG Chat with Gemini 2.5 Flash, SSE streaming, LLM query rewrite, structured grounding prompt, source attribution
- [x] ~~Self-hosted embedding model selection~~ → `intfloat/multilingual-e5-small` (1024 dims, multilingual)

### Billing & Payments
- [ ] Stripe integration: Subscriptions for base tiers + Usage Records for overage
- [ ] Spending alerts: email at 80%/100% of quota — implementation (SendGrid / SES)
- [ ] Hard cap on overage: tenant-configurable max overage amount
- [ ] Invoice generation for Enterprise contracts
- [ ] Free trial period for Pro tier (7 days? 14 days?)

### Vendor Marketplace
- [ ] Vendor onboarding flow: self-service registration vs invite-only (Phase 1)
- [ ] Documentation quality control: automated validation or manual review?
- [ ] Privacy/anonymization level: how much search data to share with vendors
- [ ] Vendor Terms of Service and data usage agreement
- [ ] Revenue share model: if a vendor brings their own developers, do they get a discount?
- [ ] "Verified Vendor" badge criteria and verification process
- [ ] Vendor dashboard UI: separate app or section within main Web UI?
- [ ] Competitive analytics anonymization: how to show category averages without revealing competitors

### Compliance
- [ ] GDPR compliance: data deletion, export
- [ ] SOC 2 readiness for Enterprise customers
