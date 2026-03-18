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
| [PARTNERSHIP_MARKETING.md](PARTNERSHIP_MARKETING.md) | Go-to-market strategy: vendor partnerships, co-marketing playbook, target vendors, KPIs | ~330 |

---

## Product Summary

**IPCodex** is a commercial SaaS platform that transforms chaotic device documentation (PDF, Swagger, web pages) into a structured knowledge base with semantic search, and serves as a distribution hub for firmware, SDKs, and tools — enabling AI coding assistants (Cursor, Windsurf, GitHub Copilot) to write accurate device integration code via RAG + MCP.

**Target scale**: 1000+ developer tenants + 100+ device vendors. Two-sided marketplace with hybrid monetization (subscription + overage for developers, tiered plans for vendors).

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              CLIENTS                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │ Cursor / IDE  │  │   Web UI     │  │  REST API    │  │ Vendor     │ │
│  │ MCP over SSE  │  │  React SPA   │  │  (3rd-party) │  │ Portal API │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └─────┬──────┘ │
└─────────┼─────────────────┼─────────────────┼────────────────┼─────────┘
          │ API Key + SSE   │ JWT             │ API Key        │ Vendor Key
          ▼                 ▼                 ▼                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        API GATEWAY (FastAPI)                             │
│  Auth Middleware (Tenant Key | Vendor Key | JWT)                        │
│  → Usage Metering → Rate Limiter (Redis) → Router                      │
└───────┬──────────────────┬──────────────────┬───────────────────────────┘
        │                  │                  │
  ┌─────▼──────┐    ┌──────▼───────┐   ┌─────▼──────────┐
  │ MCP Server │    │ REST Routers │   │ Vendor Routers │
  │ HTTP/SSE   │    │ /api/v1/...  │   │ /vendor/v1/... │
  └─────┬──────┘    └──────┬───────┘   └────────┬───────┘
        │                  │                     │
        └────────┬─────────┘                     │
                 ▼                               ▼
┌────────────────────────┐          ┌──────────────────────┐
│    PostgreSQL 16       │          │       Redis          │
│  + pgvector            │          │  rate limits         │
│  tenants, vendors,     │          │  job queue           │
│  devices, chunks,      │          │  usage counters      │
│  usage_log,            │          └──────────┬───────────┘
│  vendor_analytics      │                     │
└────────────────────────┘                     ▼
                                ┌──────────────────────────┐
                                │     Celery Workers       │
                                │  ingest: chunk → embed   │
                                │  analytics: daily aggr.  │
                                │  billing: monthly calc.  │
                                └──────────────┬───────────┘
                                               │
                          ┌────────────────────┼────────────────────┐
                          ▼                    ▼                    ▼
                ┌──────────────────┐ ┌──────────────────┐ ┌────────────────┐
                │  MinIO / S3      │ │  Celery Beat     │ │  Stripe API    │
                │  original MD     │ │  periodic tasks  │ │  subscriptions │
                │  vendor logos    │ │  (analytics,     │ │  usage records │
                └──────────────────┘ │   billing)       │ │  invoices      │
                                     └──────────────────┘ └────────────────┘
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
- Every billable API call writes to `usage_log` table (async, non-blocking)
- Redis counters for real-time rate limiting (sliding window per tenant)
- Celery Beat schedules — see [DEPLOYMENT.md — Celery Beat Schedule](DEPLOYMENT.md#celery-beat-schedule)
- Stripe integration: Subscriptions for base tier, metered billing for overage
- Full pricing model: [MONETIZATION.md](MONETIZATION.md)

### Embedding Strategy
- **OpenAI `text-embedding-3-small`** (1536 dims) for cloud — best quality
- **`all-MiniLM-L6-v2`** (384 dims) for on-premise / offline — zero-padded to 1536
- Provider selected via `EMBEDDING_PROVIDER` env variable
- Fixed `vector(1536)` column in pgvector — no schema changes when switching providers
- Zero-padded vectors preserve cosine similarity correctness in the 384-dim subspace

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

Full details: [FLOWS.md — Supported Document Formats](FLOWS.md#supported-document-formats)

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
      main.py                # FastAPI app entry point + lifespan
      config.py              # Settings via pydantic-settings (env vars)
      models.py              # SQLAlchemy ORM models (all tables)
      database.py            # Async engine, session factory, connection pool
      deps.py                # FastAPI dependencies (auth, db session, rate limit)

      auth/
        api_key.py           # API Key validation → tenant resolution
        jwt.py               # JWT for Web UI (future)
        middleware.py         # Auth middleware for all routes

      tenants/
        router.py            # CRUD: create/update/delete tenants
        schemas.py           # Pydantic request/response schemas
        service.py           # Business logic, subscription management

      devices/
        router.py            # Device + firmware CRUD
        schemas.py
        service.py

      documents/
        router.py            # Upload markdown, trigger ingestion
        schemas.py
        service.py

      search/
        router.py            # REST search endpoint
        service.py           # Vector search with tenant isolation
        reranker.py          # Optional cross-encoder reranking

      mcp/
        server.py            # MCP tools: search_docs, get_endpoint, list_devices
        transport.py         # HTTP/SSE MCP transport adapter

      ingestion/
        chunker.py           # Base chunking logic (split/merge/overlap)
        embedder.py          # OpenAI + local embedding abstraction
        tasks.py             # Celery async tasks (ingest_document)
        pipeline.py          # Orchestration: detect format → parse → embed → store
        parsers/
          __init__.py        # Format router: detect_format(file) → parser class
          markdown.py        # MD → chunks by H1/H2/H3 headers
          swagger.py         # OpenAPI 2.0/3.x → 1 chunk per endpoint
          postman.py         # Postman Collection v2.1 → endpoint docs
          pdf.py             # PyMuPDF text extraction → chunks
          ocr.py             # EasyOCR (scanned PDFs) → text → chunks
          web.py             # httpx + BeautifulSoup → clean HTML → chunks

      billing/
        usage.py             # Write usage_log entries, query monthly totals
        limits.py            # Tier-based limits enforcement + quota checks
        stripe.py            # Stripe subscriptions, usage records, customer sync
        webhooks.py          # Stripe webhook handler (payment events)
        alerts.py            # Spending alerts at 80%/100% (email via SendGrid/SES)
        tasks.py             # Celery periodic tasks: daily analytics, monthly billing
        schemas.py

      vendor/
        router.py            # Vendor portal: publish docs, view analytics
        schemas.py           # Pydantic request/response schemas for vendor API
        service.py           # Vendor business logic, document publishing
        analytics.py         # Daily aggregation of search stats per vendor/device

      artifacts/
        router.py            # Vendor artifact upload + developer download endpoints
        schemas.py           # Pydantic schemas for artifacts
        service.py           # Upload, scan orchestration, presigned URL generation
        scanner.py           # Antivirus scanning (ClamAV integration)
        tasks.py             # Celery tasks: virus scan, notification, changelog diff

      importers/             # Custom vendor importers (Platinum tier)
        __init__.py          # Importer registry + base class
        base.py              # BaseImporter abstract class (crawl, parse, sync)
        hikvision_isapi.py   # Example: Hikvision ISAPI portal scraper
        dahua_http.py        # Example: Dahua HTTP API portal scraper
        tasks.py             # Celery tasks: scheduled auto-sync per vendor

    db/
      schema.sql             # Full DDL (tables, indexes, RLS)
      migrations/            # Alembic migrations
      alembic.ini

    celery_app.py            # Celery configuration (Redis broker) + beat_schedule

    tests/
      conftest.py            # Shared fixtures: test DB, Redis, S3, async client
      unit/
        test_chunker.py
        test_embedder.py
        test_auth.py
        test_billing.py
        test_schemas.py
      integration/
        test_db.py
        test_search.py
        test_ingestion.py
        test_s3.py
        test_rate_limiting.py
      e2e/
        test_developer_flow.py
        test_vendor_flow.py

    Dockerfile               # Python app container
    requirements.txt
    pyproject.toml

  docker-compose.yml         # Dev: PostgreSQL + Redis + API + Worker + MinIO
  docker-compose.prod.yml    # Production overrides (replicas, resources, etc.)
  .env.example               # Configuration template
  .github/
    workflows/
      ci.yml                 # Lint + test + build
      deploy.yml             # Deploy to staging / production
  README.md
```

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| API Gateway | FastAPI + uvicorn |
| MCP Server | FastMCP (Python MCP SDK), HTTP/SSE transport |
| Database | PostgreSQL 16 + pgvector (HNSW index, HASH partitioning at scale) |
| Cache / Rate Limit | Redis 7 |
| Object Storage | MinIO / AWS S3 |
| Background Jobs | Celery + Redis broker + Celery Beat (periodic) |
| Embedding (cloud) | OpenAI text-embedding-3-small (1536 dims) |
| Embedding (local) | sentence-transformers/all-MiniLM-L6-v2 (384 dims, zero-padded) |
| ORM | SQLAlchemy 2.0 (async) |
| Migrations | Alembic |
| Auth | API Key (SHA-256 hashed) + JWT (future) |
| Billing | Stripe (subscriptions + metered usage records) |
| Email Alerts | SendGrid or AWS SES (spending alerts, vendor reports) |
| Deployment | Docker Compose (dev) / Kubernetes (prod) |
| Token Counting | tiktoken |
| Antivirus | ClamAV (clamd TCP socket, clamav/clamav Docker image) |
| File Integrity | hashlib SHA-256 (auto-generated checksums) |

---

## Implementation Phases

### Phase 1 — Core (Working Search)

| # | Task | Key Files |
|---|------|-----------|
| 1 | Infrastructure: Docker Compose + PostgreSQL schema (incl. vendor tables) | `docker-compose.yml`, `db/schema.sql` |
| 2 | Configuration + database layer + SQLAlchemy models (all tables) | `config.py`, `database.py`, `models.py` |
| 3 | Markdown chunker with tests | `ingestion/chunker.py`, `tests/test_chunker.py` |
| 4 | Embedding abstraction (OpenAI + local) with tests | `ingestion/embedder.py`, `tests/test_embedder.py` |
| 5 | Ingestion pipeline + Celery task | `ingestion/pipeline.py`, `ingestion/tasks.py` |
| 6 | Vector search service with tenant isolation | `search/service.py`, `tests/test_search.py` |

### Phase 2 — API + Auth + Metering

| # | Task | Key Files |
|---|------|-----------|
| 7 | FastAPI application with routers | `main.py`, routers, `deps.py` |
| 8 | Dual API Key auth: tenant keys (`ipx_`) + vendor keys (`ipv_`) | `auth/api_key.py`, `auth/middleware.py` |
| 9 | Rate limiting middleware (Redis sliding window) | `deps.py`, `billing/limits.py` |
| 10 | Usage metering: log every billable call, real-time quota check | `billing/usage.py`, `billing/limits.py` |
| 11 | REST endpoints: devices, documents, search, ingest | all tenant routers |

### Phase 3 — MCP + IDE Integration

| # | Task | Key Files |
|---|------|-----------|
| 12 | MCP server with HTTP/SSE transport | `mcp/server.py`, `mcp/transport.py` |
| 13 | MCP tools with billing integration (check_and_meter on each call) | `mcp/server.py`, `deps.py` |
| 14 | Cursor IDE integration testing | manual testing |

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

| # | Task | Key Files |
|---|------|-----------|
| 19 | Stripe integration: subscriptions, usage records, webhooks | `billing/stripe.py`, `billing/webhooks.py` |
| 20 | Spending alerts: email at 80%/100% quota (Celery Beat hourly) | `billing/alerts.py` |
| 21 | Monthly overage calculation + Stripe reporting (Celery Beat) | `billing/tasks.py` |
| 22 | Database migrations (Alembic) | `db/migrations/`, `alembic.ini` |
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
- [ ] Web UI technology: React + TypeScript SPA vs Next.js
- [ ] On-premise deployment: Helm chart for Kubernetes
- [ ] Monitoring: Prometheus + Grafana vs cloud-native (Datadog, etc.)
- [ ] CDN for static assets and S3 presigned URLs
- [ ] Backup strategy: pg_dump schedule, S3 versioning
- [ ] AI Chat interface (Phase 2 from CONTEXT.md): LLM + RAG conversational UI
- [ ] Self-hosted embedding model selection: nomic-embed-text-v1.5 vs BGE-M3 vs all-MiniLM-L6-v2

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
