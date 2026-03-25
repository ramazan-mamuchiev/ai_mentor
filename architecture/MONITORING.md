# Plexicode — Monitoring, Logging & Alerting

> Part of [Plexicode Architecture](PLAN.md) | See also: [Deployment](DEPLOYMENT.md)

---

## Stack

| Component | Technology | Role |
|-----------|-----------|------|
| Log aggregation | Grafana Loki 3.4 | Stores and queries structured logs |
| Log collection | Promtail 3.4 | Ships Docker container logs to Loki |
| Dashboards & alerts | Grafana 11.6 | Visualization, alerting, SLA tracking |

All monitoring is **log-based** (not metrics-based). Loki queries structured JSON logs emitted by the application via `structlog`. No Prometheus or StatsD required.

---

## Structured Logging

### Format

All application logs are JSON, written to stdout (for Promtail) and rotated files:

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

### Library

- `structlog` with JSON renderer for stdout
- Custom `_RequestIdFilter` injects `request_id` from `ContextVar` into every log record
- Human-readable format for file logs (`app.log`, `error.log`)

### Log Files

| File | Level | Content |
|------|-------|---------|
| stdout | All | JSON (consumed by Promtail) |
| `app.log` | INFO+ | Application events, human-readable |
| `error.log` | ERROR+ | Errors and exceptions |
| `access.log` | INFO+ | HTTP request/response log |

File rotation: `SizeAwareTimedRotatingFileHandler` — rotates by size (`log_max_size_mb`, default 50 MB) and daily. Retention: `log_retention_days` (default 30).

### Ingestion Progress Logging

The ingestion pipeline emits structured log events at each stage, enabling monitoring of progress and performance:

```json
{"event": "PDF conversion started", "pages": 250, "parallel": true, "workers": 4, "total_chunks": 5, "pages_per_chunk": 50}
{"event": "PDF page range conversion failed, retrying", "pages": "0-49", "attempt": 1, "max_retries": 2}
{"event": "Language detected via Gemini", "raw_response": "en,ru", "easyocr_langs": ["en", "ru"]}
{"event": "OCR completed", "ocr_ms": 8500, "detected_languages": ["en", "ru"], "ocr_images_total": 12, "ocr_images_success": 9, "ocr_images_failed": 1}
{"event": "OCR failed for image, continuing", "image": "/tmp/img_042.png", "error_type": "RuntimeError"}
{"event": "Gemini embedding batch completed", "batch_index": 3, "total_batches": 5, "texts_count": 100, "duration_ms": 2340}
{"event": "Worker ingestion completed", "document_id": 42, "chunks": 180, "duration_sec": 45.2, "convert_ms": 12000, "embed_ms": 28000, "ocr_applied": true}
```

Key fields for monitoring: `parallel`, `workers`, `total_chunks`, `batch_index`, `total_batches`, `convert_ms`, `ocr_ms`, `ocr_images_total`, `ocr_images_failed`, `detected_languages`, `embed_ms`, `db_ms`.

### Request Logging Middleware

`RequestLoggingMiddleware` runs on every HTTP request:

- Generates `X-Request-ID` (UUID) and sets it in `ContextVar`
- Tracks `active_requests_count` gauge
- Logs to `access` logger: method, path, status_code, duration_ms, client_ip, user_agent, request/response size
- Skips `/health` endpoint
- Flags slow requests (> 5s threshold)

---

## Log Collection (Promtail)

Promtail collects logs from all Docker containers via `docker_sd_configs`:

```yaml
scrape_configs:
  - job_name: docker
    docker_sd_configs:
      - host: unix:///var/run/docker.sock
        refresh_interval: 5s
    pipeline_stages:
      - json:
          expressions:
            level: level
            logger: logger
            request_id: request_id
            event: event
      - labels:
          level:
          logger:
```

Extracted labels (`level`, `logger`) enable efficient Loki queries like:

```logql
{container="/ipcodex-api-1", logger="mcp"} | json
```

---

## Loki Configuration

- Schema: `v13` (TSDB)
- Storage: filesystem (`/loki/chunks`)
- Retention: 30 days (`720h`)
- Compaction: every 10 minutes
- Single-node deployment (no replication)

---

## Grafana Dashboards

9 provisioned dashboards in the `Plexicode` folder:

| Dashboard | File | Key Panels |
|-----------|------|------------|
| **Overview** | `ipcodex-overview.json` | Request rate, error rate, avg response time, uptime, traffic by status code, latency percentiles, top endpoints, live logs |
| **System Health** | `ipcodex-system.json` | Uptime, DB pool usage, active requests, errors/min, embedding duration, log volume by level/logger |
| **Ingestion Pipeline** | `ipcodex-ingestion.json` | Ingestion count, chunks created, timing (5 stages: read/convert/parse/embed/db), format breakdown (PDF/Swagger/Markdown/Proto), queue depth, upload size, converter details, parallel PDF workers, progress tracking |
| **Document Audit** | `ipcodex-doc-audit.json` | Uploads over time, ingestion timing, embedding speed, search latency, similarity score distribution |
| **Queue Monitor** | `ipcodex-queue.json` | Celery pending/processing (4 workers), queue depth, wait time, task lifecycle, worker health, task runtime, Beat heartbeat |
| **AI Chat** | `ipcodex-ai-chat.json` | Chat requests, errors, response time, tokens/sec, RAG context build time, Ollama health, error log |
| **Search Quality** | `ipcodex-search.json` | Total/empty searches, avg similarity, avg results per query, search duration, low-similarity searches |
| **MCP Tools** | `ipcodex-mcp-tools.json` | Tool calls by instrument, duration, errors, live tool logs |
| **Alerts & SLA** | `ipcodex-alerts.json` | Availability %, latency SLA compliance, error budget burn, threshold lines, alert status |

All dashboards use Loki as the sole datasource. Panels use LogQL queries with `json` parser, `unwrap` for numeric aggregations, and `count_over_time` / `quantile_over_time` for statistics.

---

## Alert Rules

8 alert rules provisioned via `monitoring/grafana/provisioning/alerting/rules.yml`:

| Alert | Condition | For | Severity |
|-------|-----------|-----|----------|
| **High Error Rate** | >5% of 5xx responses over 5 min | 5m | Critical |
| **High Latency** | p95 response time > 10s over 5 min | 5m | Warning |
| **DB Pool Saturation** | Connection pool > 80% utilized | 5m | Warning |
| **Service Down** | No logs from API container for 5 min | 5m | Critical |
| **Ingestion Failures** | >3 ingestion failures in 15 min | 0s | Warning |
| **Chat High Latency** | Chat p95 > 60s over 5 min | 5m | Warning |
| **Chat Errors** | >5 chat stream errors in 15 min | 0s | Warning |
| **Ollama Unreachable** | >2 Ollama connection failures in 5 min | 2m | Critical |

All alerts query Loki via LogQL expressions. `noDataState: OK` for most rules (no data = no problem). `Service Down` uses `noDataState: Alerting` (no data = service is down).

---

## File Structure

```
monitoring/
├── loki-config.yml                          Loki server configuration
├── promtail-config.yml                      Promtail log collection config
└── grafana/
    └── provisioning/
        ├── datasources/
        │   └── loki.yml                     Loki datasource for Grafana
        ├── dashboards/
        │   ├── provider.yml                 Dashboard provisioning config
        │   ├── ipcodex-overview.json        Overview dashboard
        │   ├── ipcodex-system.json          System Health dashboard
        │   ├── ipcodex-ingestion.json       Ingestion Pipeline dashboard
        │   ├── ipcodex-doc-audit.json       Document Audit dashboard
        │   ├── ipcodex-queue.json           Queue Monitor dashboard
        │   ├── ipcodex-ai-chat.json         AI Chat dashboard
        │   ├── ipcodex-search.json          Search Quality dashboard
        │   ├── ipcodex-mcp-tools.json       MCP Tools dashboard
        │   └── ipcodex-alerts.json          Alerts & SLA dashboard
        └── alerting/
            └── rules.yml                    8 alert rules (YAML)
```

---

## Docker Compose Services

```yaml
loki:
  image: grafana/loki:3.4.2
  ports: ["3100:3100"]
  volumes:
    - ./monitoring/loki-config.yml:/etc/loki/local-config.yaml
    - lokidata:/loki

promtail:
  image: grafana/promtail:3.4.2
  volumes:
    - ./monitoring/promtail-config.yml:/etc/promtail/config.yml
    - /var/run/docker.sock:/var/run/docker.sock:ro
  depends_on: [loki]

grafana:
  image: grafana/grafana:11.6.0
  ports: ["3000:3000"]
  environment:
    GF_AUTH_ANONYMOUS_ENABLED: "true"
    GF_AUTH_ANONYMOUS_ORG_ROLE: Admin
    GF_AUTH_DISABLE_LOGIN_FORM: "true"
    GF_UNIFIED_ALERTING_ENABLED: "true"
  volumes:
    - ./monitoring/grafana/provisioning:/etc/grafana/provisioning
    - grafanadata:/var/lib/grafana
  depends_on: [loki]
```

Access Grafana at `http://localhost:3000` — anonymous admin access enabled for development.
