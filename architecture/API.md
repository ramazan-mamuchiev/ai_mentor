# IPCodex — API Reference & MCP Tools

> Part of [IPCodex Architecture](PLAN.md) | See also: [Database Schema](DATABASE.md)

---

## API Key Flow

1. Tenant registers (Web UI or API) → receives `tenant_id`
2. Tenant creates API Key → receives `ipx_a1b2c3d4e5f6...` (shown once)
3. Database stores only `SHA-256(key)` + prefix `ipx_a1b2`
4. Cursor MCP configuration:

```json
{
  "mcpServers": {
    "ipcodex": {
      "url": "https://api.ipcodex.dev/mcp/sse",
      "headers": { "Authorization": "Bearer ipx_a1b2c3d4e5f6..." }
    }
  }
}
```

5. Every request: `Authorization` header → hash → lookup `api_keys` → resolve `tenant_id` → all queries scoped to tenant

### Vendor API Key Flow

1. Vendor registers at `POST /vendor/v1/register` → receives `vendor_id`
2. Vendor creates API Key → receives `ipv_x1y2z3w4a5b6...` (shown once)
3. Database stores `SHA-256(key)` in `vendor_api_keys` + prefix `ipv_x1y2`
4. Vendor CI/CD or scripts use key:
   ```
   Authorization: Bearer ipv_x1y2z3w4a5b6...
   ```
5. Every request: `ipv_` prefix → lookup `vendor_api_keys` → resolve `vendor_id` → scoped to vendor

---

## REST API Endpoints

### Tenant Endpoints (`/api/v1/...`) — require `ipx_` API Key

**Auth & Registration:**

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `/api/v1/register` | Create tenant account | Public |
| POST | `/api/v1/api-keys` | Generate new API key for tenant | API Key (admin scope) |
| GET | `/api/v1/api-keys` | List tenant API keys (prefix only) | API Key (admin scope) |
| DELETE | `/api/v1/api-keys/{key_id}` | Revoke an API key | API Key (admin scope) |
| GET | `/api/v1/me` | Current tenant info + tier + usage | API Key (any scope) |

**Devices:**

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/api/v1/devices` | List tenant devices + firmware versions | API Key (list scope) |
| POST | `/api/v1/devices` | Create device (or link from public catalog) | API Key (admin scope) |
| GET | `/api/v1/devices/{id}` | Device details + documents + versions | API Key (list scope) |
| PUT | `/api/v1/devices/{id}` | Update device metadata | API Key (admin scope) |
| DELETE | `/api/v1/devices/{id}` | Delete device + cascade documents | API Key (admin scope) |

**Documents & Ingestion:** ✅

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `/api/v1/documents/ingest` | Upload file (any format) + trigger indexing | API Key |
| POST | `/api/v1/documents/ingest-archive` | Upload archive (ZIP/7z/tar/RAR) + ingest all files | API Key |
| GET | `/api/v1/documents` | List documents with status, progress_percent, progress_stage | API Key |
| GET | `/api/v1/documents/{id}` | Document details + chunk count + progress | API Key |
| GET | `/api/v1/documents/{id}/status` | Ingestion job status + progress | API Key |
| GET | `/api/v1/documents/{id}/download` | Presigned S3 URL (15 min TTL) | API Key |
| DELETE | `/api/v1/documents/{id}` | Delete document + chunks | API Key |
| GET | `/api/v1/documents/queue-stats` | Celery queue statistics | API Key |
| POST | `/api/v1/documents/requeue-pending` | Re-enqueue stuck documents | API Key |
| POST | `/api/v1/documents/reindex` | Reindex all documents | API Key |
| POST | `/api/v1/documents/reingest` | Re-ingest documents (optional product/format filter) | API Key |

**Chat (RAG):** ✅

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `/api/v1/chat/sessions` | Create chat session (optional product/version filter) | API Key |
| GET | `/api/v1/chat/sessions` | List chat sessions (newest first) | API Key |
| GET | `/api/v1/chat/sessions/{id}` | Session details with message history | API Key |
| DELETE | `/api/v1/chat/sessions/{id}` | Delete session and messages | API Key |
| POST | `/api/v1/chat/sessions/{id}/messages` | Send message → SSE stream (RAG + LLM) | API Key |

**Uploads (TUS):** ✅

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| OPTIONS | `/api/v1/uploads` | TUS capabilities (version, extensions, max size) | None |
| POST | `/api/v1/uploads` | Create TUS upload session | API Key |
| HEAD | `/api/v1/uploads/{id}` | Get upload offset (resume point) | API Key |
| PATCH | `/api/v1/uploads/{id}` | Upload chunk (append bytes) | API Key |
| DELETE | `/api/v1/uploads/{id}` | Cancel upload + cleanup S3 | API Key |

**Search:**

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `/api/v1/search` | Semantic search (same as MCP tool) | API Key |
| POST | `/api/v1/search/endpoint` | Find specific API endpoint | API Key |

**Billing & Usage (planned):**

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/api/v1/usage` | Current month usage summary | API Key |
| GET | `/api/v1/usage/history` | Usage history by month | API Key |
| GET | `/api/v1/billing/portal` | Redirect to Stripe billing portal | API Key |

**Public Catalog (planned):**

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/api/v1/catalog/products` | Browse public product catalog (vendor-published) | API Key |
| POST | `/api/v1/catalog/products/{id}/add` | Add public product to tenant's catalog | API Key |
| GET | `/api/v1/catalog/products/{id}/artifacts` | List firmware/SDK/tools for a product | API Key |
| GET | `/api/v1/artifacts/{id}/download` | Download firmware/SDK (presigned S3 URL) | API Key |

### Vendor Endpoints (`/vendor/v1/...`) — require `ipv_` API Key

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `/vendor/v1/register` | Create vendor account | Public |
| POST | `/vendor/v1/api-keys` | Generate vendor API key | Vendor Key (admin scope) |
| GET | `/vendor/v1/me` | Vendor info + tier + device count | Vendor Key (any scope) |
| POST | `/vendor/v1/documents/publish` | Bulk upload documentation | Vendor Key (publish scope) |
| POST | `/vendor/v1/firmware/notify` | Notify new firmware release | Vendor Key (publish scope) |
| GET | `/vendor/v1/devices` | List vendor's devices | Vendor Key (any scope) |
| GET | `/vendor/v1/analytics/searches` | Search stats per device | Vendor Key (analytics scope) |
| GET | `/vendor/v1/analytics/trends` | Usage trends over time | Vendor Key (analytics scope) |
| GET | `/vendor/v1/analytics/top-queries` | Most searched queries | Vendor Key (analytics scope) |
| PUT | `/vendor/v1/documents/{id}/policy` | Set download policy per document | Vendor Key (publish scope) |
| POST | `/vendor/v1/artifacts/upload` | Upload firmware/SDK/tool binary | Vendor Key (publish scope) |
| GET | `/vendor/v1/artifacts` | List vendor's artifacts | Vendor Key (any scope) |
| GET | `/vendor/v1/artifacts/{id}/scan-status` | Check antivirus scan result | Vendor Key (any scope) |
| DELETE | `/vendor/v1/artifacts/{id}` | Remove artifact from distribution | Vendor Key (publish scope) |

### MCP Endpoint ✅

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET/POST | `/mcp` | Streamable HTTP MCP endpoint (FastMCP) | API Key (future) |

### System Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/health` | Liveness check (is the process running?) | None |
| GET | `/ready` | Readiness check (DB + Redis + S3 connected?) | None |
| POST | `/webhooks/stripe` | Stripe webhook handler (payment events) | Stripe signature |

---

## MCP Tools ✅

IPCodex exposes **3 tools** via the Model Context Protocol. The MCP server is focused on its core purpose: helping AI coding assistants find documentation for writing integration code.

Ingestion tools (`ingest_document`, `ingest_url`) were intentionally excluded from MCP — they are administrative operations available via REST API only.

```python
@mcp.tool(name="search_documentation")
async def tool_search_documentation(
    query: str,
    product: str | None = None,
    version: str | None = None,
    limit: int = 5,
) -> str:
    """Search IPCodex knowledge base for product integration documentation.

    IPCodex indexes API documentation for hardware devices (IP cameras, access controllers,
    intercoms, sensors) and software platforms (VMS, PSIM, IoT platforms, SDKs).

    Use this tool when you need to write integration code and need to find:
    - REST/HTTP/gRPC/SOAP API endpoints and their parameters
    - Authentication methods (API keys, OAuth, digest, ONVIF)
    - Request/response formats, data models, and protocol details
    - Code examples and integration patterns

    Args:
        query: Describe what you need in natural language.
            Good: "how to open a door via HikCentral HTTP API"
            Bad: "door" (too vague)
        product: Filter by product name. Use list_products first.
        version: Filter by firmware or API version.
        limit: Number of results (1-20, default 5).
    """

@mcp.tool(name="get_api_endpoint")
async def tool_get_api_endpoint(
    endpoint: str,
    product: str | None = None,
) -> str:
    """Look up documentation for a specific API endpoint path.

    Performs exact path match first, then falls back to semantic search.

    Args:
        endpoint: The API endpoint path.
            Examples: "/acs/v1/door/doControl", "/ISAPI/AccessControl/Door/param"
        product: Filter by product name.
    """

@mcp.tool(name="list_products")
async def tool_list_products(
    category: str | None = None,
    query: str | None = None,
) -> str:
    """List products with indexed documentation available in IPCodex.

    Call this FIRST to discover what products are available before using search_documentation.

    Args:
        category: Filter by product category.
            Examples: "camera", "vms", "access_control", "intercom", "nvr", "sdk"
        query: Search products by name or manufacturer.
            Examples: "Hikvision", "Axxon", "DS-2CD"
    """
```

**Output format**: compact single-line metadata + content (optimized for AI context windows):

```
[1] HikCentral | V2.6.1 | Door Control API > POST /acs/v1/door/doControl (similarity: 0.89)

<chunk content>

---

[2] HikCentral | V2.6.1 | Door Control API > Authentication (similarity: 0.85)

<chunk content>
```

---

## Registration Flows

### Tenant Registration

```
POST /api/v1/register
{
  "company_name": "Acme Integrations",
  "email": "admin@acme-int.com",
  "password": "..."   // for Web UI login (future)
}

Response 201:
{
  "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
  "slug": "acme-integrations",
  "tier": "free",
  "api_key": "ipx_a1b2c3d4e5f6g7h8i9j0..."   // shown ONCE
}

→ Stripe: create Customer with metadata { tenant_id }
→ DB: insert into tenants + api_keys
→ Email: welcome email with getting started guide
```

### Vendor Registration

```
POST /vendor/v1/register
{
  "company_name": "Hikvision",
  "website": "https://www.hikvision.com",
  "contact_email": "partners@hikvision.com",
  "category": "video_surveillance"   // video_surveillance | access_control | intercom | ...
}

Response 201:
{
  "vendor_id": "660e8400-e29b-41d4-a716-446655440001",
  "slug": "hikvision",
  "tier": "basic",
  "api_key": "ipv_x1y2z3w4a5b6c7d8e9f0..."   // shown ONCE
}

→ DB: insert into vendors + vendor_api_keys
→ Email: welcome email with documentation upload guide
→ Admin: notify IPCodex team for review (optional manual verification)
```

---

## Error Handling

### Standard Error Response Format

All API errors follow a consistent JSON format:

```json
{
  "error": {
    "code": "QUOTA_EXCEEDED",
    "message": "Monthly search quota exceeded. Upgrade to Pro or wait until next month.",
    "details": {
      "limit": 200,
      "used": 200,
      "tier": "free",
      "resets_at": "2026-04-01T00:00:00Z"
    }
  }
}
```

### HTTP Status Codes

| Code | Meaning | When |
|:----:|---------|------|
| 200 | OK | Successful read/search |
| 201 | Created | Tenant/vendor/device/document created |
| 202 | Accepted | Ingestion job queued (async) |
| 400 | Bad Request | Invalid input, missing required fields |
| 401 | Unauthorized | Missing or invalid API key |
| 403 | Forbidden | Key lacks required scope, or wrong key type for route |
| 404 | Not Found | Resource not found within tenant scope |
| 409 | Conflict | Duplicate resource (e.g., same document hash) |
| 422 | Unprocessable | Validation error (Pydantic details included) |
| 429 | Too Many Requests | Rate limit or quota exceeded |
| 500 | Internal Error | Unexpected server error (logged, alert sent) |
| 503 | Service Unavailable | DB/Redis/S3 unreachable (readiness check fails) |

### Error Codes

| Code | Description |
|------|-------------|
| `AUTH_REQUIRED` | No Authorization header |
| `AUTH_INVALID` | API key not found or revoked |
| `AUTH_WRONG_TYPE` | Tenant key on vendor route (or vice versa) |
| `SCOPE_DENIED` | Key lacks required scope |
| `QUOTA_EXCEEDED` | Monthly usage limit reached (Free tier) |
| `RATE_LIMITED` | Too many requests per minute |
| `DEVICE_LIMIT` | Max devices for tier reached |
| `DOCUMENT_LIMIT` | Max documents for tier reached |
| `STORAGE_LIMIT` | Max storage for tier reached |
| `DUPLICATE_RESOURCE` | Document with same hash already exists |
| `INGESTION_FAILED` | Document processing error |
| `VENDOR_TIER_LIMIT` | Vendor tier limit reached (devices/docs) |
| `VENDOR_STORAGE_LIMIT` | Vendor storage quota exceeded |
| `ARTIFACT_TOO_LARGE` | File exceeds max size for vendor tier |
| `ARTIFACT_SCAN_PENDING` | Artifact still being scanned (retry later) |
| `ARTIFACT_INFECTED` | Artifact failed antivirus scan (quarantined) |
| `ARTIFACT_TYPE_INVALID` | Unsupported file extension |
