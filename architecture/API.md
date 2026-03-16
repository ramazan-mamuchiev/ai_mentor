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

**Documents & Ingestion:**

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `/api/v1/documents/ingest` | Upload file (any format) + trigger indexing | API Key (ingest scope) |
| GET | `/api/v1/documents` | List documents with status | API Key (list scope) |
| GET | `/api/v1/documents/{id}` | Document details + chunk count | API Key (list scope) |
| GET | `/api/v1/documents/{id}/status` | Ingestion job status | API Key (list scope) |
| DELETE | `/api/v1/documents/{id}` | Delete document + chunks | API Key (admin scope) |
| GET | `/api/v1/documents/{id}/download` | Presigned S3 URL (15 min TTL) | API Key (search scope) |

**Search:**

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `/api/v1/search` | Semantic search (same as MCP tool) | API Key (search scope) |
| POST | `/api/v1/search/endpoint` | Find specific API endpoint | API Key (search scope) |

**Billing & Usage:**

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/api/v1/usage` | Current month usage summary | API Key (any scope) |
| GET | `/api/v1/usage/history` | Usage history by month | API Key (admin scope) |
| GET | `/api/v1/billing/portal` | Redirect to Stripe billing portal | API Key (admin scope) |

**Public Catalog:**

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/api/v1/catalog/devices` | Browse public device catalog (vendor-published) | API Key (any scope) |
| POST | `/api/v1/catalog/devices/{id}/add` | Add public device to tenant's catalog | API Key (admin scope) |
| GET | `/api/v1/catalog/devices/{id}/artifacts` | List firmware/SDK/tools for a device | API Key (any scope) |
| GET | `/api/v1/artifacts/{id}/download` | Download firmware/SDK (presigned S3 URL) | API Key (search scope) |

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

### MCP Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/mcp/sse` | SSE stream for MCP protocol | API Key in header |
| POST | `/mcp/message` | JSON-RPC MCP messages | API Key in header |

### System Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/health` | Liveness check (is the process running?) | None |
| GET | `/ready` | Readiness check (DB + Redis + S3 connected?) | None |
| POST | `/webhooks/stripe` | Stripe webhook handler (payment events) | Stripe signature |

---

## MCP Tools (Tenant-Scoped, Metered)

Every MCP tool call goes through `check_and_meter` dependency:
1. Authenticate API Key → resolve `tenant_id`
2. Check monthly quota (`usage_log` count vs tier limit)
3. If Free tier and over limit → return error "Monthly limit reached"
4. If Pro/Team and over limit → allow but flag as overage
5. Execute tool logic
6. Write to `usage_log` (action, billable_units, tokens, duration)

```python
@mcp.tool()
async def search_documentation(
    query: str,
    device: str | None = None,
    version: str | None = None,
    limit: int = 5,
) -> str:
    """Search device API documentation by semantic similarity.
    Returns the most relevant chunks for your query.
    Use this to find API endpoints, parameters, data formats, and examples."""

@mcp.tool()
async def get_api_endpoint(
    endpoint: str,
    device: str | None = None,
) -> str:
    """Get detailed documentation for a specific API endpoint path.
    Example: get_api_endpoint('/acs/v1/door/doControl')"""

@mcp.tool()
async def list_devices() -> str:
    """List all indexed devices with their firmware versions
    and document counts in your account."""

@mcp.tool()
async def ingest_document(
    file_path: str,
    device_name: str,
    firmware_version: str,
    manufacturer: str = "",
    format: str = "auto",   # auto | markdown | swagger | postman | pdf | web
) -> str:
    """Upload and index a documentation file (Markdown, Swagger/OpenAPI, Postman, PDF, or web URL).
    Format is auto-detected or can be specified explicitly.
    Processing happens in background — returns job_id for status polling.
    Billable units depend on format: 1 (md/swagger/postman), 2 (pdf/web), 5 (scanned PDF/OCR)."""

@mcp.tool()
async def download_document(
    device: str,
    version: str | None = None,
    document_id: int | None = None,
) -> str:
    """Get a download link for the full original documentation file.
    Returns a presigned S3 URL valid for 15 minutes.
    Requires Pro tier or above. Respects vendor download policy."""

@mcp.tool()
async def get_firmware(
    device: str,
    version: str | None = None,
    artifact_type: str = "firmware",  # firmware | sdk | tool | driver
) -> str:
    """List available firmware, SDKs, and tools for a device.
    Returns artifact metadata: filename, version, size, SHA-256 hash, download URL.
    Only artifacts that passed antivirus scan (status='clean') are listed."""
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
