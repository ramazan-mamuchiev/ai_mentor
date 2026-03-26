# Lexiro — Deployment, Security & Operations

> Part of [Lexiro Architecture](PLAN.md) | See also: [Infrastructure Costs](INFRASTRUCTURE_COSTS.md), [Monitoring](MONITORING.md)

---

## Docker Compose (Current — Full Stack)

The actual `docker-compose.yml` in the repository. Runs all services including monitoring.

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    ports: ["5432:5432"]
    environment:
      POSTGRES_DB: lexiro
      POSTGRES_USER: lexiro
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-lexiro_dev}
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./backend/db/schema.sql:/docker-entrypoint-initdb.d/01-schema.sql

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

  minio:
    image: minio/minio
    ports: ["9000:9000", "9001:9001"]
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: ${S3_ACCESS_KEY:-lexiro}
      MINIO_ROOT_PASSWORD: ${S3_SECRET_KEY:-lexiro_dev}

  api:
    build: ./backend
    ports: ["8000:8000"]
    depends_on: [postgres, redis, minio, ollama]
    environment:
      DATABASE_URL: postgresql+asyncpg://lexiro:${POSTGRES_PASSWORD:-lexiro_dev}@postgres:5432/lexiro
      DATABASE_URL_SYNC: postgresql://lexiro:${POSTGRES_PASSWORD:-lexiro_dev}@postgres:5432/lexiro
      REDIS_URL: redis://redis:6379/0
      S3_ENDPOINT: http://minio:9000
      EMBEDDING_PROVIDER: ${EMBEDDING_PROVIDER:-gemini}
      LLM_PROVIDER: ${LLM_PROVIDER:-openai}
      OLLAMA_URL: http://ollama:11434
      LLM_MODEL: ${LLM_MODEL:-qwen2.5-coder:7b}
      OPENAI_BASE_URL: ${OPENAI_BASE_URL:-https://generativelanguage.googleapis.com/v1beta/openai}
      GEMINI_API_KEY: ${GEMINI_API_KEY:-}
      OPENAI_LLM_MODEL: ${OPENAI_LLM_MODEL:-gemini-2.5-flash}
      LLM_REASONING_EFFORT: ${LLM_REASONING_EFFORT:-none}
      RAG_TOP_K: ${RAG_TOP_K:-10}
      RAG_MIN_SIMILARITY: ${RAG_MIN_SIMILARITY:-0.35}
      RAG_HISTORY_MESSAGES: ${RAG_HISTORY_MESSAGES:-6}
      RAG_HISTORY_MAX_TOKENS: ${RAG_HISTORY_MAX_TOKENS:-8000}
      MAX_UPLOAD_SIZE_MB: ${MAX_UPLOAD_SIZE_MB:-50}
      MAX_ARCHIVE_SIZE_MB: ${MAX_ARCHIVE_SIZE_MB:-350}
      HF_HOME: /root/.cache/huggingface
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level warning

  worker:
    build: ./backend
    depends_on: [postgres, redis, minio]
    environment:
      # same as api (DATABASE_URL, REDIS_URL, S3_*, EMBEDDING_PROVIDER, HF_HOME)
    command: celery -A app.celery_app worker --loglevel=info --concurrency=4 -Q celery,monitoring

  beat:
    build: ./backend
    depends_on: [postgres, redis]
    environment:
      # same as api (DATABASE_URL, REDIS_URL)
    command: celery -A app.celery_app beat --loglevel=info

  web:
    build: ./frontend
    ports: ["80:80"]
    depends_on: [api]

  ollama:
    image: ollama/ollama
    ports: ["11434:11434"]
    environment:
      LLM_MODEL: ${LLM_MODEL:-qwen2.5-coder:7b}
    volumes:
      - ollama_data:/root/.ollama
      - ./scripts/ollama-entrypoint.sh:/entrypoint.sh:ro
    entrypoint: ["bash", "/entrypoint.sh"]

  loki:
    image: grafana/loki:3.4.2
    ports: ["3100:3100"]

  promtail:
    image: grafana/promtail:3.4.2
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    depends_on: [loki]

  grafana:
    image: grafana/grafana:11.6.0
    ports: ["3000:3000"]
    depends_on: [loki]

volumes:
  pgdata:
  redisdata:
  minio_data:
  hfcache:
  ollama_data:
  lokidata:
  grafanadata:
```

### Docker Compose (Dev — Lightweight)

`docker-compose.dev.yml` — PostgreSQL only, for local backend development:

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    ports: ["5432:5432"]
    environment:
      POSTGRES_DB: lexiro
      POSTGRES_USER: lexiro
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-lexiro_dev}
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./backend/db/schema.sql:/docker-entrypoint-initdb.d/01-schema.sql
```

### Service URLs (Local)

| Service | URL | Description |
|---------|-----|-------------|
| Web UI | http://localhost | React SPA (nginx) |
| API | http://localhost:8000 | FastAPI backend |
| API docs | http://localhost:8000/docs | Swagger UI (auto-generated) |
| MCP | http://localhost:8000/mcp | MCP endpoint for Cursor/IDE |
| Grafana | http://localhost:3000 | Dashboards + alerts |
| MinIO | http://localhost:9001 | Object storage console |
| Ollama | http://localhost:11434 | LLM API |

### Service URLs (Production VPS)

| Service | URL | Description |
|---------|-----|-------------|
| Web UI + Landing | https://lexiro.io | Landing (`/`) + App (`/app`) via nginx |
| API | https://lexiro.io/api/ | Proxied to api:8000 by nginx |

### Planned Docker Compose (Production)

```yaml
# docker-compose.prod.yml — not yet implemented
# Will add: replicas, resource limits, ClamAV, Stripe webhooks, production logging
```

---

## VPS Deployment (Production)

Production environment.

### Server

| Parameter | Value |
|-----------|-------|
| Domain | `lexiro.io` |
| IP | `82.38.66.177` |
| OS | Ubuntu (Docker pre-installed) |
| Access | `ssh root@lexiro.io` |
| Project path | `/opt/lexiro` |
| Repository | [`github.com/olegvphoenix/lexiro`](https://github.com/olegvphoenix/lexiro) (branch: `main`) |

### Running Services

| Service | Status | Notes |
|---------|:------:|-------|
| web (nginx + React SPA) | ✅ | |
| api (FastAPI + uvicorn) | ✅ | |
| worker (Celery, concurrency=4) | ✅ | DB pool: pool_size=8, max_overflow=4 |
| beat (Celery Beat, separate container) | ✅ | Periodic tasks only |
| postgres (pgvector) | ✅ | |
| redis | ✅ | |
| minio | ✅ | |

Monitoring stack (Loki, Promtail, Grafana) and Ollama are not deployed on staging VPS.

### Deploy Commands

**Full stack rebuild (backend + frontend):**

```bash
ssh root@lexiro.io "cd /opt/lexiro && git pull && docker compose build api web && docker compose up -d api worker beat web"
```

**Frontend only:**

```bash
ssh root@lexiro.io "cd /opt/lexiro && git pull && docker compose build web && docker compose up -d web"
```

**Backend only:**

```bash
ssh root@lexiro.io "cd /opt/lexiro && git pull && docker compose build api && docker compose up -d api worker beat"
```

**View logs:**

```bash
ssh root@lexiro.io "cd /opt/lexiro && docker compose logs -f web api"
```

---

## S3 Key Structure

```
lexiro-storage/
  tenants/
    {tenant_id}/
      documents/
        {document_id}/
          source.md                          # or source.json, source.yaml, source.pdf
          metadata.json                      # { title, device, firmware, format,
                                             #   original_filename, file_size, uploaded_at }
  vendors/
    {vendor_id}/
      documents/
        {device_slug}/
          {firmware_version}/
            source.json                      # native format preserved (swagger, postman, etc.)
            source.pdf                       # or .md, .yaml — whatever vendor uploaded
            metadata.json                    # { format, download_policy, ... }
      artifacts/
        {device_slug}/
          {firmware_version}/
            firmware/
              DS-2CD2347_V5.7.21.bin         # firmware binary
              DS-2CD2347_V5.7.21.bin.sha256  # checksum file
            sdk/
              HikSDK_V5.7.21.zip             # SDK package
            tools/
              SADP_V3.0.exe                   # utility
            release_notes.md                  # auto-indexed into chunks
      assets/
        logo.png                             # vendor logo (for catalog)
  exports/
    {tenant_id}/
      usage-{month}.csv                      # monthly usage export (GDPR)
```

File naming convention: `source.{ext}` where `ext` matches the original format (`.md`, `.json`, `.yaml`, `.pdf`). The `format` field in `metadata.json` and `documents` table is the authoritative source for parser selection.

---

## Configuration Reference (.env)

### Currently Implemented

```bash
# === Database ===
DATABASE_URL=postgresql+asyncpg://lexiro:password@postgres:5432/lexiro
DATABASE_URL_SYNC=postgresql://lexiro:password@postgres:5432/lexiro

# === Redis ===
REDIS_URL=redis://redis:6379/0

# === S3 / MinIO ===
S3_ENDPOINT=http://minio:9000
S3_ACCESS_KEY=lexiro
S3_SECRET_KEY=lexiro_dev
S3_BUCKET=lexiro-storage

# === Auth ===
API_KEY=ipx_dev_key_12345                    # single API key (MVP, no multi-tenancy yet)

# === Gemini API ===
GEMINI_API_KEY=AIza...                       # single key for LLM + embeddings

# === Embedding ===
EMBEDDING_PROVIDER=gemini                    # local | gemini
EMBEDDING_DIMS=1024                          # vector dimensionality (Matryoshka for Gemini)
EMBEDDING_MODEL_GEMINI=gemini-embedding-2-preview
# Local: intfloat/multilingual-e5-large (1024 dims), auto-downloaded on first run
# Gemini: gemini-embedding-2-preview — uses GEMINI_API_KEY, MTEB Multilingual leader

# === LLM (RAG Chat) — Tiered Model Strategy ===
# Default provider for production (Gemini via OpenAI-compatible API):
LLM_PROVIDER=openai                          # ollama | openai
LLM_MAX_TOKENS=4096
LLM_TEMPERATURE=0.2
LLM_TIMEOUT=600                              # seconds
LLM_REASONING_EFFORT=none                    # none | low | medium | high — Gemini thinking budget (none = disabled for speed)

# Gemini Flash — default for Free & Pro tiers ($0.30/$2.50 per 1M tokens)
OPENAI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
OPENAI_LLM_MODEL=gemini-2.5-flash

# Ollama — development fallback only ($0 cost):
OLLAMA_URL=http://ollama:11434
LLM_MODEL=qwen2.5-coder:7b                  # Ollama model name

# Claude Opus 4.6 — default for Team & Enterprise tiers ($5/$25 per 1M tokens)
OPUS_BASE_URL=https://api.anthropic.com/v1
OPUS_API_KEY=...
OPUS_MODEL=claude-opus-4-6-20260319

# Per-model billing: input+output tokens metered separately per model.
# Model routing by tier: Free/Pro → OPENAI_LLM_MODEL, Team/Ent → OPUS_MODEL.
# Pro users get 100 Opus queries/mo included (PRO_OPUS_QUOTA).
PRO_OPUS_QUOTA=100                           # Opus queries included in Pro tier
OPUS_OVERAGE_PRO=0.05                        # $/query overage for Pro
OPUS_OVERAGE_TEAM=0.04                       # $/query overage for Team

# === RAG ===
RAG_TOP_K=10                                 # number of chunks to retrieve for context
RAG_MIN_SIMILARITY=0.35                      # minimum cosine similarity threshold (discard below)
RAG_HISTORY_MESSAGES=6                       # max conversation messages included in LLM context
RAG_HISTORY_MAX_TOKENS=8000                  # max tokens from chat history in prompt

# === Upload Limits ===
MAX_UPLOAD_SIZE_MB=50                        # single file upload limit
MAX_ARCHIVE_SIZE_MB=350                      # archive upload limit
TUS_MAX_FILE_SIZE_GB=5                       # TUS resumable upload limit
TUS_UPLOAD_TTL_HOURS=24                      # auto-expire incomplete uploads

# === Logging ===
APP_ENV=development                          # development | staging | production
APP_LOG_LEVEL=INFO
LOG_DIR=/app/logs
LOG_MAX_SIZE_MB=50                           # log file rotation size
LOG_RETENTION_DAYS=30
```

### Planned (Not Yet Implemented)

```bash
# === Auth (multi-tenancy) ===
API_KEY_PREFIX_TENANT=ipx_
API_KEY_PREFIX_VENDOR=ipv_
JWT_SECRET_KEY=...
JWT_ALGORITHM=HS256

# === Stripe ===
STRIPE_API_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...

# === Rate Limiting ===
RATE_LIMIT_FREE_RPM=10
RATE_LIMIT_PRO_RPM=60

# === Antivirus (ClamAV) ===
CLAMAV_HOST=clamav
CLAMAV_PORT=3310

# === Email ===
EMAIL_PROVIDER=sendgrid
SENDGRID_API_KEY=SG....
```

---

## Security

### Transport
- **HTTPS only** in production (TLS 1.2+)
- HTTP allowed only in development (`APP_ENV=development`)
- HSTS headers in production

### CORS
- Configurable `CORS_ORIGINS` via env variable
- Production: only `https://lexiro.io` and customer domains
- Credentials mode: `allow_credentials=True` (for JWT cookies)

### Input Validation
- All inputs validated via Pydantic schemas (FastAPI auto-validation)
- Documentation uploads: max size 50 MB, only `.md` / `.json` / `.yaml` / `.pdf` extensions
- Artifact uploads: max size 2 GB, allowed types: `.bin`, `.img`, `.hex`, `.dav`, `.zip`, `.tar.gz`, `.exe`, `.msi`, `.dmg`, `.sdk`
- SQL injection: prevented by SQLAlchemy parameterized queries (never raw SQL)
- XSS: API-only (no HTML rendering), JSON responses only

### Artifact Security (Firmware/SDK/Tools)
- **Antivirus scanning**: every uploaded binary is scanned via ClamAV before being made available for download
- Scan is asynchronous (Celery task): upload returns immediately, artifact is `scan_status='pending'`
- Only artifacts with `scan_status='clean'` are listed in API/MCP responses
- Infected artifacts: quarantined (not deleted), vendor notified via email
- **SHA-256 checksums**: auto-generated on upload, stored in DB and as `.sha256` sidecar file in S3
- Developers can verify integrity: `sha256_hash` field returned in artifact metadata
- **File size limits**: Basic 100 MB/file, Pro 500 MB/file, Enterprise/Platinum 2 GB/file
- **Storage quotas**: enforced per vendor tier (Basic 1 GB, Pro 50 GB, Enterprise 500 GB, Platinum unlimited)
- **Presigned URLs**: download links expire in 15 minutes, single-use token for large files

### API Key Security
- Keys generated with `secrets.token_urlsafe(32)` (256-bit entropy)
- Stored as SHA-256 hash (irreversible)
- Prefix stored for identification (`ipx_a1b2` / `ipv_x1y2`)
- Key shown to user exactly once (on creation)
- Keys can be revoked instantly (soft delete: `is_active = FALSE`)
- Scope-based access control: `search`, `ingest`, `list`, `admin`, `publish`, `analytics`

### Rate Limiting Details
- Redis sliding window algorithm: `ZADD + ZRANGEBYSCORE + ZCARD`
- Key: `ratelimit:{tenant_id}:{minute_bucket}`
- TTL: 120 seconds (auto-cleanup)
- Per-minute limits by tier (see .env config)
- Monthly limits enforced via `usage_log` aggregation (not Redis — for accuracy)
- Returns `Retry-After` header with seconds until next window

### Data Isolation
- Row Level Security (RLS) policies enforce tenant data isolation at DB level
- Application-level `WHERE tenant_id = $t` as primary enforcement
- RLS is defense-in-depth (catches bugs in application layer)

---

## Celery Beat Schedule

### Currently Implemented

Beat runs as a **separate container** (`beat` service) — no longer embedded in the worker via `-B` flag. This frees all 4 worker slots for ingestion tasks. Worker processes queues `celery` and `monitoring`:

```python
# celery_app.py — current beat_schedule

beat_schedule = {
    "cleanup-expired-uploads": {
        "task": "app.celery_app.cleanup_expired_uploads",
        "schedule": crontab(minute=0),   # every hour
    },
}
```

### Planned (Not Yet Implemented)

```python
beat_schedule = {
    "spending-alerts": { ... },           # hourly: check quota limits
    "vendor-analytics-daily": { ... },    # daily: aggregate search stats
    "monthly-billing": { ... },           # monthly: Stripe overage
    "artifact-scan-retry": { ... },       # hourly: ClamAV retry
    "importers-auto-sync": { ... },       # daily: vendor auto-sync
}
```

---

## Testing Strategy

### Test Inventory (42 test files)

```
         ╱╲
        ╱Smoke╲           1 file: real embedding + pgvector
       ╱────────╲
      ╱Integration╲      13 files: PostgreSQL + pgvector via Testcontainers
     ╱──────────────╲
    ╱   Unit Tests    ╲   28 files: mocked dependencies, fast execution
   ╱────────────────────╲
```

### Unit Tests (~28 files)

| Area | Test Files | What's Tested |
|------|-----------|---------------|
| Ingestion | `test_chunker`, `test_embedder`, `test_pipeline_utils`, `test_ingest_from_bytes` | Chunking, embedding, format detection, full ingestion from bytes |
| Converters | `test_pdf`, `test_swagger`, `test_web`, `test_proto_converter` | PDF/OCR, Swagger/OpenAPI, URL, Protobuf → Markdown conversion |
| Parsers | `test_markdown_parser`, `test_swagger_parser` | Markdown H1/H2/H3 splitting, OpenAPI endpoint extraction |
| Archives | `test_archive_7z`, `test_archive_tar`, `test_archive_rar`, `test_archive_schemas` | ZIP/7z/tar/RAR extraction, format parity, edge cases |
| Chat & LLM | `test_chat_router`, `test_llm_client`, `test_rag` | Chat API, LLM streaming, RAG context building |
| Upload | `test_tus_router`, `test_quota` | TUS protocol, metadata parsing, storage quotas |
| Celery | `test_celery_task`, `test_cleanup_task` | Ingestion task lifecycle, expired upload cleanup |
| Documents | `test_documents_router`, `test_search_dedup` | REST API, deduplication |
| Reindex | `test_reindex_router`, `test_reindex_service` | Reindex job API, stale detection |
| S3 | `test_s3`, `test_s3_multipart` | Upload/download, multipart, key generation |

### Integration Tests (~13 files)

All integration tests use **Testcontainers** (PostgreSQL + pgvector) — Docker must be running.

| Area | Test Files | What's Tested |
|------|-----------|---------------|
| Pipeline | `test_pipeline`, `test_proto_pipeline` | Full ingestion pipeline with real DB |
| Search | `test_search` | Vector search accuracy, endpoint matching |
| MCP | `test_mcp_tools`, `test_api` | All 3 MCP tools, HTTP protocol, tool listing |
| Chat | `test_chat`, `test_chat_api` | Session CRUD, message persistence, RAG with real DB |
| Upload | `test_tus_upload` | TUS model, status transitions, SHA-256, concurrent sessions |
| Archives | `test_archive_7z_pipeline`, `test_archive_tar_pipeline`, `test_archive_rar_pipeline` | Full archive → ingest pipeline |
| Documents | `test_document_dedup` | Hash-based deduplication with real DB |
| Reindex | `test_reindex_api` | Reindex API with real DB + mocked Celery |

### Tools
- `pytest` + `pytest-asyncio` for async tests
- `httpx.AsyncClient` for FastAPI testing (no server needed)
- `testcontainers` for PostgreSQL + pgvector in CI
- Mock embedder (returns deterministic vectors) for fast tests

### Running Tests

```bash
cd backend
pytest tests/ -v                    # all tests
pytest tests/unit/ -v               # unit only (fast, no Docker)
pytest tests/integration/ -v        # integration (requires Docker)
```

---

## CI/CD Pipeline

```
  Push to branch
       │
       ▼
  GitHub Actions (or GitLab CI)
       │
       ├─ Lint: ruff check + ruff format --check
       ├─ Type check: mypy
       ├─ Unit tests: pytest tests/unit/ (fast, no external deps)
       │
       ▼ (parallel)
       ├─ Integration tests: pytest tests/integration/
       │    (testcontainers: PostgreSQL + Redis)
       │
       ▼ (on main branch merge)
       ├─ Build Docker image → push to registry (GHCR / ECR)
       ├─ E2E tests against staging
       │
       ▼ (manual approval for production)
       └─ Deploy to production (rolling update)
           ├─ Run Alembic migrations
           ├─ Deploy API + Worker + Beat
           ├─ Health check verification
           └─ Notify Slack / email
```

---

## Logging & Observability

Monitoring is fully implemented using **Grafana + Loki + Promtail** (log-based, not metrics-based).

Full details: [MONITORING.md](MONITORING.md) — dashboards, alert rules, structured logging, Promtail config.

### Structured Logging

All logs in JSON format, consumed by Promtail → Loki:

```json
{
  "timestamp": "2026-03-15T14:30:00.123Z",
  "level": "info",
  "logger": "mcp",
  "event": "MCP search_documentation completed",
  "request_id": "a1b2c3d4",
  "duration_ms": 45,
  "result_count": 5
}
```

- Library: `structlog` (structured logging for Python)
- `request_id` generated per request (UUID via `RequestLoggingMiddleware`), passed through all layers
- Log files: `app.log` (INFO+), `error.log` (ERROR+), `access.log` (HTTP requests)
- File rotation: by size (50 MB default) and daily, 30-day retention

### Health Endpoint

| Endpoint | Checks | Response |
|----------|--------|----------|
| `GET /health` | Process is running, DB connected | `200 {"status": "ok", "db_pool_size": N, ...}` |

### Dashboards & Alerts

9 Grafana dashboards and 8 alert rules are provisioned automatically. See [MONITORING.md](MONITORING.md) for the full list.
