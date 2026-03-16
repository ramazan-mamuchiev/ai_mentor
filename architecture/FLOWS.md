# IPCodex — Data Flows & Pipelines

> Part of [IPCodex Architecture](PLAN.md) | See also: [API Reference](API.md), [Database Schema](DATABASE.md)

---

## Ingestion Pipeline (Async via Celery, Multi-Format)

```
Client: POST /api/v1/documents/ingest
  { file: <upload>, device_name, firmware_version, manufacturer,
    format: "auto" }   // auto | markdown | swagger | postman | pdf | web
        │
        ▼
FastAPI: validate auth → detect format (auto or explicit)
         → calculate billable_units (1/2/5 by format)
         → check tier limits (documents count + storage)
         → save original file to S3 (native format)
         → create document(status='pending', format, billable_units)
         → enqueue Celery task
        │
        ▼
Celery Worker: ingest_document(document_id)
  1. Download original from S3
  2. Route to format-specific parser:
     ┌─────────────────────────────────────────────────────────────────┐
     │ FORMAT         │ PARSER                │ CHUNKING STRATEGY      │
     │────────────────┼───────────────────────┼────────────────────────│
     │ markdown       │ parsers/markdown.py   │ H1/H2/H3 headers      │
     │ swagger/openapi│ parsers/swagger.py    │ 1 chunk per endpoint   │
     │ postman        │ parsers/postman.py    │ 1 chunk per request    │
     │ pdf (text)     │ parsers/pdf.py        │ Page extract → headers │
     │ pdf (OCR)      │ parsers/ocr.py        │ EasyOCR → text → H1/2 │
     │ web (URL)      │ parsers/web.py        │ Scrape → clean → H1/2 │
     └─────────────────────────────────────────────────────────────────┘
  3. Common post-processing:
     - Split large sections (>1500 tokens) with 100-token overlap
     - Merge small sections (<100 tokens) with neighbor
     - Preserve heading_path hierarchy
  4. Embed all chunks in batch (embedder.py)
     - OpenAI: up to 2048 texts per request
     - Local: sentence-transformers, zero-pad to 1536 dims
  5. INSERT chunks + embeddings into pgvector
  6. UPDATE document SET status='ready', total_chunks=N
  7. Log usage (billable_units, tokens consumed, duration)
```

**Swagger/OpenAPI special handling:**
- Parse with `openapi-spec-validator` + custom endpoint extractor
- Each endpoint → 1 chunk containing: path, method, summary, parameters, request body schema, response schema, examples
- `heading_path` = endpoint path (e.g., `"POST /acs/v1/door/doControl"`)
- Enables exact path matching in `get_api_endpoint()` tool (not just vector similarity)

**PDF OCR detection:**
- First attempt text extraction (PyMuPDF)
- If extracted text < 100 chars per page → auto-switch to OCR pipeline
- Billable units upgraded from 2 to 5, client notified in job status

---

## Supported Document Formats

All formats are normalized to **chunks** in pgvector. The original file is preserved in S3 in its native format.

| Format | Extensions | Parser | Billable Units | Internal Cost | Notes |
|--------|-----------|--------|:-:|-----|-------|
| Markdown | `.md` | Direct H1/H2/H3 chunking | **1** | ~$0.001 | Cheapest, base format |
| Swagger / OpenAPI 2.0/3.x | `.json`, `.yaml` | Structural: 1 chunk per endpoint | **1** | ~$0.001 | Highest value — structured endpoints, exact match possible |
| Postman Collection v2.1 | `.json` | Convert requests → endpoint docs | **1** | ~$0.001 | Preserves request/response examples |
| PDF (text-based) | `.pdf` | PyMuPDF text extract → chunking | **2** | ~$0.005 | 2x cost — text extraction overhead |
| PDF (scanned / OCR) | `.pdf` | EasyOCR → text → chunking | **5** | ~$0.02 | 5x cost — GPU-intensive OCR, lowest quality |
| Web page | URL | httpx + BeautifulSoup → cleaning → chunking | **2** | ~$0.003 | 2x cost — scraping + HTML cleanup |

**Format auto-detection**: by file extension first, then by content inspection (JSON with `"openapi"` or `"swagger"` key → OpenAPI; JSON with `"info"."schema"` → Postman; PDF magic bytes; etc.). Client can override with explicit `format` parameter.

---

## End-to-End Flow: Developer Using Cursor

```
Developer in Cursor IDE:
  "Write a C# method to open a door via HikCentral API"
        │
        ▼
Cursor AI sees MCP tool `search_documentation` available
        │
        ▼
MCP call: search_documentation(
    query="open door API endpoint HikCentral",
    device="HikCentral Professional"
)
        │
        ▼
IPCodex server:
  1. Authenticate API Key (ipx_...) → resolve tenant_id
  2. check_and_meter: quota check → log to usage_log (action=search)
  3. Embed query → vector [0.023, -0.118, ...]
  4. pgvector search: WHERE tenant_id=$t ORDER BY embedding <=> $q LIMIT 5
  5. Return top 5 chunks (~3-5KB total)
        │
        ▼
Cursor AI receives relevant chunks:
  - "/acs/v1/door/doControl" endpoint details
  - Request format: { doorIndexCodes, controlType, controlDirection }
  - controlType values: 0=remain open, 1=close, 2=open, 3=remain closed
  - AK/SK authentication headers
        │
        ▼
Cursor AI generates accurate C# code with correct endpoint,
parameters, values, and authentication — based on actual documentation
```

---

## End-to-End Flow: Vendor Publishing Documentation

```
Vendor (e.g. Hikvision) publishes new firmware documentation:

  POST /vendor/v1/documents/publish
    Authorization: Bearer ipv_x1y2z3...
    { device: "DS-2CD2347G2-LU", firmware: "V5.7.21",
      files: [openapi_v5.7.21.md, user_guide_v5.7.21.md] }
        │
        ▼
  IPCodex server:
    1. Authenticate Vendor Key (ipv_...) → resolve vendor_id
    2. Check vendor tier limits (Basic: 20 devices, 50 docs)
    3. Create/update device record (link to vendor_id)
    4. Upload MD files to S3
    5. Enqueue Celery ingestion tasks for each file
    6. Return { job_ids: [...], status: "processing" }
        │
        ▼
  Celery Workers:
    1. Download MD from S3
    2. Chunk by headers → embed → store in pgvector
    3. Mark documents as "ready"
        │
        ▼
  Documentation is now searchable by ALL developers
  who have this device in their tenant catalog
        │
        ▼
  Next day (Celery Beat daily task):
    Aggregate search stats → vendor_analytics table
        │
        ▼
  Vendor checks analytics dashboard:
    GET /vendor/v1/analytics/searches?device=DS-2CD2347G2-LU
    → { searches_this_week: 342, top_queries: ["night vision API",
        "motion detection config", "stream URL format"],
        unique_developers: 28, trend: "+15% vs last week" }
```

---

## End-to-End Flow: Vendor Publishing Firmware + SDK

```
Vendor uploads new firmware + SDK for a device:

  POST /vendor/v1/artifacts/upload
    Authorization: Bearer ipv_x1y2z3...
    Content-Type: multipart/form-data
    {
      device: "DS-2CD2347G2-LU",
      firmware_version: "V5.7.21",
      artifacts: [
        { file: DS-2CD2347_V5.7.21.bin, type: "firmware" },
        { file: HikSDK_V5.7.21.zip,     type: "sdk" },
        { file: SADP_V3.0.exe,          type: "tool" }
      ],
      release_notes: "## V5.7.21 Changes\n- Added night vision API...",
      changelog_diff: "auto"   // auto-diff vs V5.7.20
    }
        │
        ▼
  IPCodex server:
    1. Authenticate Vendor Key → resolve vendor_id
    2. Check vendor tier storage quota (used + new files < limit)
    3. Generate SHA-256 checksum for each file
    4. Upload files to S3 (vendor artifacts path)
    5. Create vendor_artifacts records (scan_status='pending')
    6. Auto-index release_notes as searchable chunks
    7. Enqueue Celery tasks:
       - Antivirus scan for each binary (ClamAV)
       - Changelog diff generation (vs previous version)
       - Notification to subscribed developers
        │
        ▼
  Celery Workers:
    1. ClamAV scan each file → update scan_status
       - clean → artifact available for download
       - infected → quarantine, notify vendor
    2. Generate changelog diff (release notes V5.7.21 vs V5.7.20)
    3. Send email/webhook to developers subscribed to this device:
       "New firmware V5.7.21 available for DS-2CD2347G2-LU"
        │
        ▼
  Developer in Cursor:
    MCP call: get_firmware(device="DS-2CD2347G2-LU")
    → { firmware: "V5.7.21", sha256: "a1b2c3...",
        download_url: "https://...", sdk: "HikSDK_V5.7.21.zip",
        release_notes: "Added night vision API..." }
```
