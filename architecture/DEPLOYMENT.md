# IPCodex — Deployment, Security & Operations

> Part of [IPCodex Architecture](PLAN.md) | See also: [Infrastructure Costs](INFRASTRUCTURE_COSTS.md)

---

## Docker Compose (Development)

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    ports: ["5432:5432"]
    environment:
      POSTGRES_DB: ipcodex
      POSTGRES_USER: ipcodex
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-ipcodex_dev}
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
      MINIO_ROOT_USER: ipcodex
      MINIO_ROOT_PASSWORD: ${MINIO_PASSWORD:-ipcodex_dev}
    volumes:
      - minio_data:/data

  api:
    build: ./backend
    ports: ["8000:8000"]
    depends_on: [postgres, redis, minio]
    environment:
      - DATABASE_URL=postgresql+asyncpg://ipcodex:${POSTGRES_PASSWORD:-ipcodex_dev}@postgres:5432/ipcodex
      - REDIS_URL=redis://redis:6379/0
      - S3_ENDPOINT=http://minio:9000
      - EMBEDDING_PROVIDER=${EMBEDDING_PROVIDER:-openai}
      - OPENAI_API_KEY=${OPENAI_API_KEY:-}
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000

  worker:
    build: ./backend
    depends_on: [postgres, redis, minio]
    environment:
      - DATABASE_URL=postgresql+asyncpg://ipcodex:${POSTGRES_PASSWORD:-ipcodex_dev}@postgres:5432/ipcodex
      - REDIS_URL=redis://redis:6379/0
      - S3_ENDPOINT=http://minio:9000
      - EMBEDDING_PROVIDER=${EMBEDDING_PROVIDER:-openai}
      - OPENAI_API_KEY=${OPENAI_API_KEY:-}
    command: celery -A celery_app worker --loglevel=info --concurrency=4

  beat:
    build: ./backend
    depends_on: [postgres, redis]
    environment:
      - DATABASE_URL=postgresql+asyncpg://ipcodex:${POSTGRES_PASSWORD:-ipcodex_dev}@postgres:5432/ipcodex
      - REDIS_URL=redis://redis:6379/0
      - STRIPE_API_KEY=${STRIPE_API_KEY:-}
    command: celery -A celery_app beat --loglevel=info

  clamav:
    image: clamav/clamav:1.2
    ports: ["3310:3310"]
    volumes:
      - clamav_data:/var/lib/clamav    # virus definition database

  # Qdrant — dedicated vector DB (Stage 3 scaling, optional)
  # Uncomment when migrating from pgvector to Qdrant
  # qdrant:
  #   image: qdrant/qdrant:v1.12
  #   ports: ["6333:6333", "6334:6334"]
  #   volumes:
  #     - qdrant_data:/qdrant/storage
  #   environment:
  #     QDRANT__SERVICE__GRPC_PORT: 6334

volumes:
  pgdata:
  minio_data:
  clamav_data:
  # qdrant_data:    # uncomment with Qdrant service
```

---

## S3 Key Structure

```
ipcodex-storage/
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

```bash
# === Database ===
DATABASE_URL=postgresql+asyncpg://ipcodex:password@postgres:5432/ipcodex
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10

# === Redis ===
REDIS_URL=redis://redis:6379/0

# === S3 / MinIO ===
S3_ENDPOINT=http://minio:9000
S3_ACCESS_KEY=ipcodex
S3_SECRET_KEY=ipcodex_dev
S3_BUCKET=ipcodex-storage
S3_REGION=us-east-1

# === Embedding ===
EMBEDDING_PROVIDER=openai                    # openai | local
OPENAI_API_KEY=sk-...
EMBEDDING_MODEL=text-embedding-3-small       # for openai provider
LOCAL_MODEL_NAME=all-MiniLM-L6-v2            # for local provider
EMBEDDING_DIMS=1536                          # fixed, do not change
EMBEDDING_BATCH_SIZE=512                     # texts per API call

# === Auth ===
API_KEY_PREFIX_TENANT=ipx_
API_KEY_PREFIX_VENDOR=ipv_
JWT_SECRET_KEY=...                           # for Web UI (future)
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440                      # 24 hours

# === Stripe ===
STRIPE_API_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ID_PRO=price_...
STRIPE_PRICE_ID_TEAM=price_...
STRIPE_PRICE_ID_VENDOR_PRO=price_...
STRIPE_PRICE_ID_VENDOR_ENTERPRISE=price_...

# === Email ===
EMAIL_PROVIDER=sendgrid                      # sendgrid | ses
SENDGRID_API_KEY=SG....
EMAIL_FROM=noreply@ipcodex.dev

# === Rate Limiting ===
RATE_LIMIT_WINDOW_SECONDS=60
RATE_LIMIT_FREE_RPM=10
RATE_LIMIT_PRO_RPM=60
RATE_LIMIT_TEAM_RPM=300
RATE_LIMIT_ENTERPRISE_RPM=1000

# === Antivirus (ClamAV) ===
CLAMAV_HOST=clamav
CLAMAV_PORT=3310
CLAMAV_TIMEOUT=120                       # seconds (large files)
ARTIFACT_MAX_SIZE_MB=2048                # 2 GB max upload
ARTIFACT_SCAN_ENABLED=true

# === Vector Search Backend ===
SEARCH_BACKEND=pgvector                      # pgvector | qdrant
QDRANT_HOST=qdrant                           # only when SEARCH_BACKEND=qdrant
QDRANT_PORT=6333
QDRANT_GRPC_PORT=6334
QDRANT_COLLECTION=ipcodex_chunks
QDRANT_API_KEY=                              # optional, for Qdrant Cloud

# === Application ===
APP_ENV=development                          # development | staging | production
APP_DEBUG=true
APP_LOG_LEVEL=INFO
CORS_ORIGINS=http://localhost:3000           # comma-separated
```

---

## Security

### Transport
- **HTTPS only** in production (TLS 1.2+)
- HTTP allowed only in development (`APP_ENV=development`)
- HSTS headers in production

### CORS
- Configurable `CORS_ORIGINS` via env variable
- Production: only `https://app.ipcodex.dev` and customer domains
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

```python
# celery_app.py

beat_schedule = {
    # Spending alerts: check tenants approaching quota limits
    "spending-alerts": {
        "task": "billing.tasks.check_spending_alerts",
        "schedule": crontab(minute=0),   # every hour, on the hour
    },

    # Vendor analytics: aggregate daily search stats per vendor/device
    "vendor-analytics-daily": {
        "task": "vendor.tasks.aggregate_daily_analytics",
        "schedule": crontab(hour=2, minute=0),   # daily at 02:00 UTC
    },

    # Monthly billing: calculate overage, report to Stripe
    "monthly-billing": {
        "task": "billing.tasks.process_monthly_billing",
        "schedule": crontab(day_of_month=1, hour=6, minute=0),  # 1st of month, 06:00 UTC
    },

    # Storage snapshot: calculate per-tenant storage usage
    "storage-snapshot": {
        "task": "billing.tasks.snapshot_storage_usage",
        "schedule": crontab(hour=3, minute=0),   # daily at 03:00 UTC
    },

    # Cleanup: purge old usage_log entries (> 2 years)
    "usage-log-cleanup": {
        "task": "billing.tasks.cleanup_old_usage_logs",
        "schedule": crontab(day_of_month=15, hour=4, minute=0),  # 15th of month
    },

    # Artifact virus scan retry (re-scan pending/errored artifacts)
    "artifact-scan-retry": {
        "task": "artifacts.tasks.retry_pending_scans",
        "schedule": crontab(minute=30),   # every hour at :30
    },

    # Custom importers auto-sync (Platinum vendors)
    "importers-auto-sync": {
        "task": "importers.tasks.run_scheduled_imports",
        "schedule": crontab(hour=5, minute=0),   # daily at 05:00 UTC
    },
}
```

---

## Testing Strategy

### Test Pyramid

```
         ╱╲
        ╱ E2E ╲          ~10 tests: full API flows (register → ingest → search)
       ╱────────╲
      ╱Integration╲      ~30 tests: DB queries, S3 ops, Redis, Celery tasks
     ╱──────────────╲
    ╱   Unit Tests    ╲   ~100 tests: chunker, embedder, auth, billing logic
   ╱────────────────────╲
```

### Unit Tests
- **Chunker**: split by headers, merge small, split large, overlap, heading_path
- **Embedder**: mock OpenAI, mock local model, zero-padding, batch size
- **Auth**: key generation, hashing, prefix extraction, scope validation
- **Billing**: quota check, overage calculation, tier limits
- **Schemas**: Pydantic validation, edge cases

### Integration Tests
- **DB**: CRUD operations, RLS enforcement, vector search accuracy
- **S3**: upload/download, key structure
- **Redis**: rate limiting window, counter expiration
- **Celery**: task queuing, result tracking, error handling

### E2E Tests
- Register tenant → create API key → ingest document → wait for ready → search → verify results
- Register vendor → publish docs → verify in public catalog → tenant adds device → searches vendor docs
- Rate limiting: exceed limit → 429 → wait → succeed
- Quota: Free tier → 200 searches → 201st blocked

### Tools
- `pytest` + `pytest-asyncio` for async tests
- `httpx.AsyncClient` for FastAPI testing (no server needed)
- `testcontainers` for PostgreSQL + Redis in CI
- `moto` or `localstack` for S3 mocking
- `fakeredis` for unit-level Redis tests

### Test Location

```
backend/
  tests/
    unit/
      test_chunker.py
      test_embedder.py
      test_auth.py
      test_billing.py
    integration/
      test_db.py
      test_search.py
      test_ingestion.py
      test_s3.py
    e2e/
      test_developer_flow.py
      test_vendor_flow.py
      test_rate_limiting.py
    conftest.py              # shared fixtures, test DB setup
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

### Structured Logging

All logs in JSON format (for ELK/Datadog/CloudWatch ingestion):

```json
{
  "timestamp": "2026-03-15T14:30:00Z",
  "level": "INFO",
  "service": "api",
  "tenant_id": "550e8400-...",
  "action": "search",
  "duration_ms": 45,
  "chunks_returned": 5,
  "similarity_top": 0.89,
  "request_id": "req_abc123"
}
```

- Library: `structlog` (structured logging for Python)
- `request_id` generated per request (UUID), passed through all layers
- Sensitive data (API keys, passwords) **never** logged

### Health Endpoints

| Endpoint | Checks | Response |
|----------|--------|----------|
| `GET /health` | Process is running | `200 {"status": "ok"}` |
| `GET /ready` | DB connection + Redis ping + S3 bucket exists | `200 {"db": "ok", "redis": "ok", "s3": "ok"}` or `503` |

### Metrics (for Prometheus / Datadog)

Key metrics to expose:

| Metric | Type | Description |
|--------|------|-------------|
| `ipcodex_search_requests_total` | Counter | Total search requests (by tenant_tier, status) |
| `ipcodex_search_duration_seconds` | Histogram | Search latency distribution |
| `ipcodex_ingest_requests_total` | Counter | Total ingestion requests |
| `ipcodex_ingest_duration_seconds` | Histogram | Ingestion latency |
| `ipcodex_active_sse_connections` | Gauge | Current MCP SSE connections |
| `ipcodex_chunks_total` | Gauge | Total chunks in pgvector |
| `ipcodex_rate_limit_hits_total` | Counter | Rate limit 429 responses |
| `ipcodex_quota_exceeded_total` | Counter | Quota block events (Free tier) |

### Alerting Rules

| Alert | Condition | Severity |
|-------|-----------|----------|
| API error rate > 5% | 5xx / total > 0.05 for 5 min | Critical |
| Search latency p99 > 2s | p99 > 2000ms for 10 min | Warning |
| DB connection pool exhausted | pool_size = active connections | Critical |
| Celery queue backlog > 100 | pending tasks > 100 for 15 min | Warning |
| Disk usage > 80% | pgvector storage > 80% capacity | Warning |
