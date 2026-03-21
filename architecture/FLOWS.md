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
     │ FORMAT         │ CONVERTER / PARSER          │ CHUNKING STRATEGY      │
     │────────────────┼─────────────────────────────┼────────────────────────│
     │ markdown       │ parsers/markdown.py         │ H1/H2/H3 headers      │
     │ swagger/openapi│ converters/swagger.py       │ 1 chunk per endpoint   │
     │ pdf (text)     │ converters/pdf.py           │ pymupdf4llm → headers  │
     │ pdf (OCR)      │ converters/pdf.py + EasyOCR │ OCR → text → headers   │
     │ web (URL)      │ converters/web.py           │ Scrape → clean → H1/2  │
     │ protobuf       │ converters/proto.py         │ service/method/message  │
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
| Protobuf | `.proto` | proto-schema-parser → Markdown → chunking | **1** | ~$0.001 | Extracts services, methods, messages, enums |

**Format auto-detection**: by file extension first, then by content inspection (JSON with `"openapi"` or `"swagger"` key → OpenAPI; `.proto` extension → Protobuf; PDF magic bytes; etc.). Client can override with explicit `format` parameter.

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

---

## Archive Ingestion Flow

```
Client: POST /api/v1/documents/ingest-archive
  { file: <archive>, product_name, firmware_version, manufacturer }
        │
        ▼
FastAPI: validate file size (≤ MAX_ARCHIVE_SIZE_MB, default 350 MB)
         → detect archive type by extension
        │
        ▼
Extract archive in memory:
  ┌───────────────────────────────────────────────────┐
  │ EXTENSION          │ EXTRACTOR                     │
  │────────────────────┼───────────────────────────────│
  │ .zip               │ zipfile (stdlib)              │
  │ .7z                │ py7zr                         │
  │ .tar / .tar.gz     │ tarfile (stdlib)              │
  │ .tar.bz2 / .tar.xz│ tarfile (stdlib)              │
  │ .rar               │ rarfile                       │
  └───────────────────────────────────────────────────┘
        │
        ▼
For each file in archive:
  1. Check extension against allowed list:
     .md, .json, .yaml, .yml, .pdf, .proto, .txt, .wsdl, .xml
  2. Skip hidden files (._*, .DS_Store, __MACOSX/)
  3. Detect format → convert → parse → chunk → embed → store
  4. Each file becomes a separate Document record
        │
        ▼
Return: { total_files, ingested, skipped, errors[] }
```

---

## RAG Chat Flow

```
User sends message via Web UI:
  POST /api/v1/chat/sessions/{id}/messages
  { content: "How do I configure PTZ on Hikvision DS-2CD2347G2-LU?" }
        │
        ▼
Server: load session (product_filter, version_filter, history)
        │  history excludes the current user message (WHERE id != user_msg.id)
        ▼
RAG Pipeline (chat/rag.py):
  1. Auto-detect product from query (if no explicit filter)
     → scan products table for name match in query text
  2. LLM Query Rewrite (if history exists):
     → send last 3 user messages + current question to LLM
     → LLM reformulates follow-up into standalone query
     → uses Gemini with reasoning_effort=none, temperature=0
     → self-contained questions pass through unchanged
     → fallback to original query on any error
  3. Embed rewritten query → vector [0.023, -0.118, ...]
  4. Vector search: ORDER BY embedding <=> $q LIMIT rag_top_k (default 10)
     → optional product/version filter
  5. Similarity threshold filtering:
     → discard chunks with similarity < rag_min_similarity (default 0.35)
  6. Format context: each chunk as numbered source with metadata
     → wrapped in <documentation_context> XML tags
  7. Build LLM messages (5-part sequence for implicit caching):
     a. System message — SYSTEM_PROMPT with XML-tagged sections:
        <role>, <constraints> (9 rules), <instructions>, <output_format>
     b. User message — documentation context
     c. Assistant ack — "Understood. I will answer strictly based on..."
     d. History — last 6 messages, up to 8,000 tokens (trims oldest first)
     e. User query — with anchor phrase
        │
        ▼
LLM Streaming (llm/client.py):
  Provider: Gemini 2.5 Flash (default) or Ollama (fallback)
  → reasoning_effort=none (thinking disabled for speed)
  → Stream tokens via SSE to client
        │
        ▼
SSE Events to client:
  1. event: token    → { "token": "The PTZ..." }     (each generated token)
  2. event: sources  → { "sources": [...] }           (retrieved chunks with similarity)
  3. event: done     → { "duration_ms": 2340 }        (completion signal)
  4. event: error    → { "error": "..." }             (if LLM fails)
        │
        ▼
Server: save assistant message + sources to chat_messages table
        save analytics (rewrite_ms, rag timing, LLM params) to chat_message_analytics
```

**Anti-hallucination strategy:**
- **Structured grounding prompt**: 9 constraints in `<constraints>` XML section, following Google's recommendations for Gemini
- **Separate system/context/ack message pattern**: enables Gemini implicit caching of static instructions
- **Similarity threshold filtering**: `rag_min_similarity` (default 0.35) removes low-relevance chunks before they reach the LLM
- **Factual grounding**: API details (endpoints, params, URLs) must come from context only; code generation allowed using general programming knowledge based on documented API details
- **Language enforcement**: "CRITICAL: ALWAYS respond in the same language as the user's question" — top-level instruction
- Source attribution: each answer references numbered sources that the user can verify
- RAG debug info (search similarity, rewrite_ms, query rewrite result) available in response metadata

---

## Frontend Routing Flow

```
User opens http://82.38.66.177/ (or http://localhost/)
        │
        ▼
nginx: try_files $uri $uri/ /index.html (SPA fallback)
        │
        ▼
React app (main.tsx): BrowserRouter wraps <App />
        │
        ▼
App.tsx: react-router-dom <Routes> resolves path:
  ┌─────────────────────────────────────────────────────────────────┐
  │ PATH               │ COMPONENT      │ DESCRIPTION               │
  │────────────────────┼────────────────┼───────────────────────────│
  │ /                  │ LandingPage    │ Public marketing page     │
  │ /app               │ ChatApp        │ Chat application (Layout) │
  │ /app/documents     │ DocumentsPage  │ Document management (TBD) │
  │ /app/products      │ ProductsPage   │ Products (TBD)            │
  │ /app/analytics     │ AnalyticsPage  │ Analytics (TBD)           │
  │ /app/settings      │ SettingsPage   │ Settings (TBD)            │
  │ *                  │ Navigate to /  │ Fallback redirect         │
  └─────────────────────────────────────────────────────────────────┘
        │
        ▼
LandingPage (/):
  - Header with nav links (anchor scroll within page)
  - Hero section with logo, slogan, CTA → /app
  - Sections: Elevator Pitch, Why, Problems, Goals, How It Works
  - Footer with copyright + author link
  - i18n: all text via t('landing.*') keys
  - Responsive: hamburger menu on mobile
        │
        ▼
ChatApp (/app):
  - Layout component: sidebar (sessions, nav, footer) + main area
  - ChatWindow: messages, empty state with logo, SSE streaming
  - FileUpload modal: TUS resumable upload
  - Theme toggle (light/dark), language toggle (EN/RU)
```

**Key files:**
- `frontend/src/main.tsx` — `BrowserRouter` wrapper
- `frontend/src/App.tsx` — `Routes` definition
- `frontend/src/pages/LandingPage.tsx` — marketing landing page
- `frontend/src/pages/ChatApp.tsx` — chat application (extracted from original `App.tsx`)
- `frontend/src/styles/landing.css` — landing page styles (responsive)
- `frontend/nginx.conf` — `try_files` SPA fallback, `/api/` proxy to `api:8000`
