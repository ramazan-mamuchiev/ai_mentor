# AI Mentor — Data Flows & Pipelines

> Part of [AI Mentor Architecture](PLAN.md) | See also: [API Reference](API.md), [Database Schema](DATABASE.md)

---

## Ingestion Pipeline (Async via Celery, Multi-Format)

### Visual Overview

```
  ┌─────────────────────────────────────────────────────────────────────────────────────┐
  │  CLIENT                                                                             │
  │  POST /api/v1/documents/ingest  { file, product_name, firmware_version, format }    │
  └────────────────────────────────────┬────────────────────────────────────────────────┘
                                       │
                                       ▼
  ┌─────────────────────────────────────────────────────────────────────────────────────┐
  │  FASTAPI                                                                            │
  │  auth → detect format → billable_units → save to S3 → create Document → Celery task │
  └────────────────────────────────────┬────────────────────────────────────────────────┘
                                       │
           ┌───────────────────────────┘
           │  Celery Worker
           ▼
  ┌─────────────────────────────────────────────────────────────────────────────────────┐
  │                                                                                     │
  │  ┌───────────────┐     ┌───────────────────────────────────────────────────────┐    │
  │  │ 1. DOWNLOAD   │     │  Format Converters (all output → Markdown)            │    │
  │  │    from S3    │────▶│  ┌──────────┬──────────┬────────┬───────┬──────────┐  │    │
  │  │    [5%]       │     │  │ Markdown │ Swagger  │  PDF   │ Proto │   Web    │  │    │
  │  └───────────────┘     │  │ (pass-   │ (1 chunk │ pymu-  │ proto │ httpx +  │  │    │
  │                        │  │  through)│  /endpt) │ pdf4llm│ parser│ BS4      │  │    │
  │                        │  └──────────┴──────────┴───┬────┴───────┴──────────┘  │    │
  │                        │                            │                          │    │
  │                        │        ┌───────────────────┘                          │    │
  │                        │        │ PDF only, if images detected                 │    │
  │                        │        ▼                                              │    │
  │                        │  ┌─────────────────────────────────────────────┐      │    │
  │                        │  │  TWO-PASS OCR (Gemini Vision)              │      │    │
  │                        │  │  Pass 1: pymupdf4llm text extraction       │      │    │
  │                        │  │  Lang:   Gemini Flash → ISO 639-1 codes    │◄╌╌╌╌╌╌╌╌╌╌╌╌╌┐
  │                        │  │  Pass 2: Gemini Vision per image           │◄╌╌╌╌╌╌╌╌╌╌╌╌╌┤
  │                        │  │  Metrics: images total/ok/empty/fail       │      │    │  ┆
  │                        │  └─────────────────────────────────────────────┘      │    │  ┆
  │                        └──────────────────────────┬────────────────────────────┘    │  ┆
  │                                                   │                                │  ┆
  │  2. CONVERT [5%→45%]                              │                                │  ┆
  │  ─────────────────────────────────────────────────┘                                │  ┆
  │                        │                                                           │  ┆
  │                        ▼                                                           │  ┆
  │  ┌─────────────────────────────────────────────────────────────────────────┐       │  ┆
  │  │ 3. NORMALIZE (NFKC)                                                    │       │  ┆
  │  │    Collapses fullwidth Latin, ligatures, non-breaking spaces            │       │  ┆
  │  └────────────────────────────────────┬────────────────────────────────────┘       │  ┆
  │                                       │                                            │  ┆
  │                                       ▼                                            │  ┆
  │  ┌─────────────────────────────────────────────────────────────────────────┐       │  ┆
  │  │ 4. PARSE → SECTIONS  [45%]                                             │       │  ┆
  │  │    H1-H6 heading extraction with code-block protection                  │       │  ┆
  │  │    Heading cleaning: strip bold/italic/links/images/HTML                │       │  ┆
  │  │    Generic "Document"/"Preamble" → actual document title                │       │  ┆
  │  └────────────────────────────────────┬────────────────────────────────────┘       │  ┆
  │                                       │                                            │  ┆
  │                                       ▼                                            │  ┆
  │  ┌─────────────────────────────────────────────────────────────────────────┐       │  ┆
  │  │ 5. CHUNK  [45%→50%]                                                    │       │  ┆
  │  │    a. Atomic blocks: code fences + tables never split                   │       │  ┆
  │  │    b. Split large: >512 tokens → pieces with 2-block overlap            │       │  ┆
  │  │       parent_content stored in chunk_parents table (deduplicated)        │       │  ┆
  │  │    b'. Semantic split: flat sections >1500 tokens split by embedding     │       │  ┆
  │  │        similarity (configurable, disabled by default)                    │       │  ┆
  │  │    c. Merge small: <50 tokens → join neighbors (same parent heading)    │       │  ┆
  │  │    d. Token count: tiktoken cl100k_base (fallback: words × 1.3)         │       │  ┆
  │  │    e. Quality log: min/max/avg/median token counts                      │       │  ┆
  │  └────────────────────────────────────┬────────────────────────────────────┘       │  ┆
  │                                       │                                            │  ┆
  │                                       ▼                                    Gemini  │  ┆
  │  ┌─────────────────────────────────────────────────────────────────────────┐  2.5  │  ┆
  │  │ 6. LLM METADATA EXTRACTION  [50%→55%]                                  │ Flash │  ┆
  │  │    Gemini Flash extracts per chunk (batches of 5):                      │◄╌╌╌╌╌╌╌╌╌┤
  │  │    ├─ doc_type: api_reference | user_guide | configuration | ...        │       │  ┆
  │  │    └─ entities: { api_endpoints[], config_params[], error_codes[],      │       │  ┆
  │  │                    protocols[], keywords[] }                             │       │  ┆
  │  │    First 1500 chars/chunk → JSON response → validated & cleaned         │       │  ┆
  │  └────────────────────────────────────┬────────────────────────────────────┘       │  ┆
  │                                       │                                            │  ┆
  │                                       ▼                                            │  ┆
  │  ┌─────────────────────────────────────────────────────────────────────────┐       │  ┆
  │  │ 7. ENRICH FOR EMBEDDING  [55%]                                         │       │  ┆
  │  │    Clean: strip bold/links/images/HTML/list-markers (keep code blocks)  │       │  ┆
  │  │    Prefix:  [heading_path]                                              │       │  ┆
  │  │             [type: api_reference]                                        │       │  ┆
  │  │             [entities: POST /api/door, ONVIF, ...]                       │       │  ┆
  │  │    Truncation guard: >500 tokens → trim content, keep prefix            │       │  ┆
  │  └────────────────────────────────────┬────────────────────────────────────┘       │  ┆
  │                                       │                                            │  ┆
  │                                       ▼                                    Gemini  │  ┆
  │  ┌─────────────────────────────────────────────────────────────────────────┐ Emb.  │  ┆
  │  │ 8. EMBED  [55%→92%]                                                    │  2    │  ┆
  │  │    Model: gemini-embedding-2-preview (768 dims, halfvec)                │◄╌╌╌╌╌╌╌╌╌┘
  │  │    task_type = RETRIEVAL_DOCUMENT                                       │       │
  │  │    Batch: 100 texts/request, L2-normalized                              │       │
  │  │    Storage: halfvec(768) — 2× compression vs float32                    │       │
  │  │    Retry: 5× exponential backoff (2ˢ base, 120s cap) on 429/503        │       │
  │  └────────────────────────────────────┬────────────────────────────────────┘       │
  │                                       │                                            │
  │                                       ▼                                            │
  │  ┌─────────────────────────────────────────────────────────────────────────┐       │
  │  │ 9. STORE IN POSTGRESQL  [92%→100%]                                     │       │
  │  │    INSERT chunks: content, content_clean, parent_id, embedding,         │       │
  │  │                   doc_type, entities, language                           │       │
  │  │    parent_content deduplicated via chunk_parents table (SHA-256 hash)    │       │
  │  │    tsvector trigger: language-aware stemmer on content_clean (BM25)      │       │
  │  │    UPDATE document: status='ready', indexed_at, timing metrics           │       │
  │  └────────────────────────────────────┬────────────────────────────────────┘       │
  │                                       │                                            │
  └───────────────────────────────────────┼────────────────────────────────────────────┘
                                          │
                                          ▼
                                  ┌───────────────┐
                                  │   DOCUMENT     │
                                  │   INDEXED      │
                                  │  status=ready  │
                                  │  progress=100% │
                                  └───────────────┘
```

### Step-by-Step Pipeline

```
Client: POST /api/v1/documents/ingest
  { file: <upload>, product_name, firmware_version, manufacturer,
    format: "auto" }   // auto | markdown | swagger | postman | pdf | web | proto
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
Celery Worker (×4, concurrency=4): ingest_document(document_id)
  1. Download original from S3
     → **Progress: 5% — "converting"**
  2. Route to format-specific converter:
     ┌──────────────────────────────────────────────────────────────────────────────────┐
     │ FORMAT          │ CONVERTER / PARSER                │ CHUNKING STRATEGY           │
     │─────────────────┼───────────────────────────────────┼─────────────────────────────│
     │ markdown        │ parsers/markdown.py               │ H1–H6 headers               │
     │ swagger/openapi │ converters/swagger.py             │ 1 chunk per endpoint        │
     │ postman         │ converters/postman.py             │ 1 chunk per request         │
     │ pdf (text)      │ converters/pdf.py (pymupdf4llm)   │ parallel 50pp → hdr split   │
     │ pdf (OCR)       │ converters/pdf.py + Gemini Vision │ OCR → text → headers        │
     │ web (URL)       │ converters/web.py                 │ Scrape → clean → H1–6       │
     │ protobuf        │ converters/proto.py               │ service/method/message      │
     │ confluence      │ converters/confluence.py          │ Space crawl → pages → H1–6  │
     └──────────────────────────────────────────────────────────────────────────────────┘

     **PDF parallel conversion** (>10 pages):
     - Pages split into 50-page chunks (`PAGES_PER_CHUNK=50`)
     - `ThreadPoolExecutor(max_workers=4)` — threads, not processes (Celery daemon constraint)
     - Each chunk retried up to 2 times with linear backoff (`MAX_RETRIES=2`)
     - Progress: `5% + fraction * 40%` — "converting" (incremental per 50-page chunk)

     **PDF OCR via Gemini** (two-pass, if images detected):
     - Pass 1: `pymupdf4llm.to_markdown()` — text layer extraction
     - Language detection: Gemini Flash (`ocr_lang_detect_model`) on first ~3000 chars
       → returns ISO 639-1 codes (en, ru, zh), fallback: `["en"]`
     - Pass 2: **Gemini Vision** (`ocr_vision_model: gemini-2.5-flash`) — each image
       → text extraction with detected language prompt
       → each image in try/except — failures don't break pipeline
       → images < 100K pixels skipped
     - OCR metrics: `ocr_ms`, images total/success/empty/failed, token usage

     For PDF/Swagger/Postman/Proto: converted Markdown saved to S3 (`converted.md`)

  3. **Unicode normalization** (NFKC) on raw text (in markdown parser)
     - Collapses fullwidth Latin, ligatures, non-breaking spaces
     - Ensures byte-identical text for deduplication and embedding

  4. **Code-block-aware heading extraction** (parsers/markdown.py):
     - Regex: `^#{1,6}\s+(.+)$` finds H1–H6 headings
     - **Fenced code block protection**: pre-scan ``` ranges; skip headings inside code
     - Prevents false section splits on `# shell comments`, YAML keys, etc.
     - Headings cleaned via `clean_heading()`: strip bold/italic/links/images/HTML

     → **Progress: 45% — "chunking"**

  5. **Chunking** (chunker.py) — split large, merge small:
     a. Split text into **atomic blocks**:
        - Code fences (```...```) and Markdown tables: never split
        - Remaining text: split by `\n\n` paragraph boundaries
     b. **Split large sections** (>`chunk_max_tokens=512`, configurable):
        - Token count via `tiktoken` cl100k_base (fallback: `len(words) * 1.3`)
        - `chunk_overlap_paragraphs=2` trailing blocks from previous piece overlap into next
        - `parent_content` deduplicated via `chunk_parents` table (SHA-256 hash → `parent_id` FK)
        - `heading_path` suffixed with ` (part N)`
     b'. **Semantic chunking fallback** (disabled by default, `semantic_chunking_enabled`):
        - For "flat" sections (no headings) exceeding `semantic_chunk_threshold` (1500 tokens)
        - Splits by embedding similarity: computes embeddings per paragraph, finds boundaries
          where similarity drops below `semantic_similarity_percentile` (25th percentile)
        - Falls back to token-based split if embedding API fails
     c. **Merge small sections** (<`chunk_min_tokens=50`, configurable):
        - Only merges neighbors sharing same parent heading
        - Combined tokens must fit within `max_tokens`
        - `heading_path` joined: `"A + B"` when headings differ
        - `token_count` recalculated on actual merged text
     d. **Document title enrichment**: generic "Document"/"Preamble" headings replaced
        with actual title from filename

     → **Chunk quality logging**: min/max/avg/median token counts, parent_content stats

  6. **LLM Metadata Extraction** (metadata_extractor.py) — NEW:
     - Gemini Flash (`metadata_extraction_model: gemini-2.5-flash`) extracts structured metadata
     - Batch size: **5 chunks per LLM call** (`metadata_extraction_batch_size`)
     - Each chunk: first 1500 chars as context
     - Extracted per chunk:
       a. `doc_type`: one of `api_reference | user_guide | configuration | changelog |
          release_notes | troubleshooting | protocol | model_schema | overview | other`
       b. `entities`: `{ api_endpoints[], config_params[], error_codes[], protocols[], keywords[] }`
     - Configurable: `metadata_extraction_enabled` (default true)
     - Failures: default metadata (doc_type="other") per batch, pipeline continues
     - Token usage tracked: `extract_prompt_tokens`, `extract_completion_tokens`, `extract_ms`

     → **Progress: 50% — "extracting_metadata"**

  7. **Contextual enrichment for embedding** (pipeline.py → `enrich_for_embedding`):
     a. Clean Markdown artifacts (text_cleaner.py — `clean_for_embedding`):
        - Strip bold/italic/strikethrough (line-scoped regexes)
        - Convert links → plain text (keep anchor, drop URL)
        - Remove images, HTML tags, bare URLs, blockquote markers
        - Strip list markers (-, *, +, 1.) preserving indentation
        - **Preserve code blocks** (contain API details)
     b. Build enrichment prefix:
        - `[heading_path]`
        - `[type: api_reference]` (from metadata extraction)
        - `[entities: POST /api/door, ONVIF, ...]` (up to 20 entities)
     c. **Truncation guard**: if enriched text > 500 tokens (`MAX_EMBEDDING_TOKENS`),
        truncate content only, preserve heading_path prefix
     d. Original Markdown stored in DB unchanged (for display)
     e. Cleaned text stored in `content_clean` column for BM25 indexing

     → **Progress: 55% — "embedding"**

  8. **Embed** all enriched chunks in batches (embedder.py):
     - Model: `gemini-embedding-2-preview` (google-genai SDK)
     - `task_type=RETRIEVAL_DOCUMENT`, `output_dimensionality=768` (reduced from 1024 via Matryoshka)
     - Stored as **`halfvec(768)`** (16-bit float) — ~3.5× storage reduction vs `vector(1024)`
     - Batch size: **100 texts** per API call (`BATCH_SIZE=100`, Gemini limit)
     - Retry: 5 attempts with exponential backoff (2^n × 2s, cap 120s) on 429/503
     - Vectors **L2-normalized** post-API
     - Progress: `55% + fraction * 37%` — "embedding" (incremental per batch)

     → **Progress: 92% — "storing"**

  9. **Store** chunks in PostgreSQL + pgvector:
     - INSERT: `content`, `content_clean`, `parent_id`, `embedding` (halfvec), `doc_type`, `entities`, `language`
     - `parent_content` deduplicated via `chunk_parents` table (SHA-256 content hash → `parent_id` FK)
       — in-memory cache avoids redundant DB lookups within a single ingestion
     - PostgreSQL trigger builds `tsvector` with **language-aware stemmer** (russian/english/simple)
       using both `tsv` (simple, exact) and `tsv_lang` (language-specific stemming) columns
     - UPDATE document: `status='ready'`, timing metrics, embedding metadata

     → **Progress: 100%** — `status='ready'`, `progress_stage=''`, `indexed_at=NOW()`

  10. Log usage: billable_units, tokens, duration, timing breakdown per stage
```

**Swagger/OpenAPI special handling:**
- Parse with `openapi-spec-validator` + custom endpoint extractor
- Each endpoint → 1 chunk: path, method, summary, parameters, request/response schema, examples
- `heading_path` = endpoint path (e.g., `"POST /acs/v1/door/doControl"`)
- Enables exact path matching in `get_api_endpoint()` MCP tool

**PDF parallel conversion & fault tolerance** (`converters/pdf.py`):
- **Parallel threshold**: >10 pages processed in parallel, ≤10 pages single call
- **Chunk size**: 50 pages (`PAGES_PER_CHUNK=50`)
- **Workers**: `ThreadPoolExecutor(max_workers=4)` — threads (Celery daemons cannot fork)
- **Retry**: 2 attempts per chunk with linear backoff
- **Progress callback**: `progress_callback(fraction, stage)` per chunk

**PDF OCR pipeline** (two-pass via Gemini, `converters/pdf.py` + `converters/ocr.py`):
- **Pass 1**: `pymupdf4llm.to_markdown()` — text layer (parallel for >10 pages)
- **Language detection**: Gemini Flash (`ocr_lang_detect_model`) on first ~3000 chars
  - Returns ISO 639-1 codes (en, ru, zh), saved to `documents.detected_language`
  - Fallback: `["en"]` on error
- **Pass 2**: **Gemini Vision** (`ocr_vision_model: gemini-2.5-flash`) for each image
  - Images < 100K pixels (`_OCR_IMAGE_MIN_AREA`) skipped
  - Each image in try/except — failures logged, pipeline continues
- **Metrics**: `ocr_ms`, `ocr_images_total/success/empty/failed`, `ocr_prompt_tokens`, `ocr_completion_tokens`, `ocr_model`
- **Cost**: tracked via `billing/pricing.py`

**Ingestion progress tracking** (`pipeline.py` → `documents` table):
- `progress_percent` (INT, 0–100) and `progress_stage` (TEXT) persisted to DB
- Throttled to at most 1 DB commit/sec (`_ProgressThrottle`), unless stage changes
- Cancellation checks between stages: if `status='cancelled'`, raises `IngestionCancelled`
- Frontend polls `GET /api/v1/documents/` and displays real-time progress bar

| Stage | Percent Range | Description |
|-------|:---:|---|
| `converting` | 5%→45% | Format conversion (PDF: `5 + frac*40` incremental, others: instant) |
| `chunking` | 45%→50% | Parse → heading extract → split → merge |
| `extracting_metadata` | 50%→55% | LLM metadata extraction (Gemini Flash, batches of 5) |
| `embedding` | 55%→92% | Gemini Embedding API (batches of 100), `55 + frac*37` incremental |
| `storing` | 92% | INSERT chunks + UPDATE document in PostgreSQL |
| *(complete)* | 100% | `status='ready'`, `progress_stage=''`, `indexed_at=NOW()` |

- On error: `progress_percent=0`, `progress_stage=''`, `status='error'`
- UI: `StatusBadge` shows animated progress bar + localized stage label
- Debug panel: `TimingBar` shows 7 timing stages (Read, Convert, OCR, Parse, Extract, Embed, DB) with `MIN_PCT=3%`
- Debug panel: OCR section (image metrics), File section (detected_language)
- Stale protection: documents in 'processing' > `document_stale_timeout_sec` (3600s) auto-reset by Celery Beat

---

## Supported Document Formats

All formats are normalized to **chunks** in pgvector. The original file is preserved in S3 in its native format.

| Format | Extensions | Parser | Billable Units | Internal Cost | Notes |
|--------|-----------|--------|:-:|-----|-------|
| Markdown | `.md` | H1–H6 header chunking, code/table protection | **1** | ~$0.001 | Cheapest, base format |
| Swagger / OpenAPI 2.0/3.x | `.json`, `.yaml` | Structural: 1 chunk per endpoint | **1** | ~$0.001 | Highest value — structured endpoints, exact match possible |
| Postman Collection v2.1 | `.json` | Convert requests → endpoint docs | **1** | ~$0.001 | Preserves request/response examples |
| PDF (text-based) | `.pdf` | PyMuPDF → parallel ThreadPoolExecutor (50-page chunks) → chunking | **2** | ~$0.005 | 2x cost — parallel conversion with retry |
| PDF (scanned / OCR) | `.pdf` | Gemini Vision OCR → text → chunking | **5** | ~$0.02 | 5x cost — Vision API OCR, lowest quality |
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
AI Mentor server:
  1. Authenticate API Key (ipx_...) → resolve tenant_id
  2. check_and_meter: quota check → log to usage_log (action=search)
  3. Query classification (if mcp_classify_enabled): detect query_type + product
     → passes query_type to search for doc-type boosting
  4. Embed query → halfvec [0.023, -0.118, ...] (768 dims)
  5. Hybrid search (vector + BM25 + RRF) + reranking + doc-type boosting
  6. Return top 5 chunks (~3-5KB total)
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
  AI Mentor server:
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
  AI Mentor server:
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
     → word-boundary regex matching, longer names prioritised
  2. LLM Query Classification (parallel with rewrite):
     → lightweight call to Gemini 2.5 Flash (~100ms, ~20 output tokens)
     → classifies into: overview | technical | code | comparison | troubleshooting | chitchat | decompose
     → categories auto-discovered from prompts/*.md files (<classifier_hint> tags)
     → selects per-type system prompt: base.md + {query_type}.md
     → token usage tracked separately (action="query_classify" in usage_log)
     → fallback to "overview" on error
     → see architecture/PROMPT_ROUTING.md for details
  3. LLM Query Rewrite (if history exists):
     → send last 3 user messages + current question to LLM
     → LLM reformulates follow-up into standalone query
     → uses Gemini with reasoning_effort=none, temperature=0
     → self-contained questions pass through unchanged
     → fallback to original query on any error
  3b. Query Decomposition (if comparison or troubleshooting type):
      → LLM splits complex query into 2-4 sub-queries
      → each sub-query searched in parallel
      → results interleaved and deduplicated
      → configurable: decompose_enabled (default true), decompose_model (gemini-2.5-flash)
  4. **HyDE** (Hypothetical Document Embedding, disabled by default):
     → for code/technical/troubleshooting query types (`hyde_query_types`)
     → Gemini Flash generates a hypothetical document answering the query (~200 tokens)
     → the hypothetical document is embedded instead of the raw query
     → improves recall for conceptual queries where user phrasing differs from doc language
     → configurable: `hyde_enabled` (default false), `hyde_model` (gemini-2.5-flash)
  4b. Embed rewritten query (or HyDE text) → halfvec [0.023, -0.118, ...]
     → task_type=RETRIEVAL_QUERY for Gemini embeddings, 768 dims
  5. Hybrid search (two parallel retrieval paths):
     a. Vector search: ORDER BY embedding <=> $q LIMIT rerank_candidates (default 20)
     b. BM25 full-text: tsv @@ plainto_tsquery('english', $q) ORDER BY ts_rank_cd
        → uses PostgreSQL tsvector/GIN index on (heading_path + content_clean)
        → **'english' stemmer**: doors→door, connecting→connect + stop-word removal
        → `content_clean` column: Markdown-stripped text (no bold/links/list markers)
        → catches exact term matches that bi-encoder may miss (API paths, codes)
     c. RRF fusion: score = w_vec/(k+rank_vec) + w_bm25/(k+rank_bm25)
        → default weights: vector=0.7, bm25=0.3, k=60
        → configurable: hybrid_search_enabled (default true)
     → optional product/version filter on both paths
     → deduplication by (heading_path, SHA-256(content)) — full content hash
  6. Re-ranking (reranker.py):
     → **Two providers**: `rerank_provider="llm"` (default) or `"vertex_rank"` (Google Vertex AI Ranking API)
     → **LLM reranker**: Gemini Flash with `response_format: json_object` for stable output;
       parses both `{"scores": [...]}` and legacy `[...]` formats; regex fallback for robustness
     → **Vertex AI Ranking API**: `google-cloud-discoveryengine` SDK, `semantic-ranker-default@latest`;
       cross-encoder model, no LLM token cost; falls back to LLM reranker on import/API error
     → text cleaned from Markdown artifacts, enriched with "[heading_path]\n{cleaned_content}"
     → raw `rerank_score` preserved for debugging; original dicts not mutated
     → top rag_top_k (default 10) results kept after re-ranking
     → configurable: rerank_enabled (default true), rerank_provider, rerank_model
  7. Similarity threshold filtering:
     → discard chunks with similarity < rag_min_similarity (default 0.35)
     → after re-ranking, uses the normalized Gemini reranker score
  8. Small-to-big context expansion:
     → if chunk has parent_content (was split from larger section),
       use full section text in LLM context instead of chunk fragment
     → deduplicate when multiple child chunks from same section are retrieved
  9. Format context: each source as **Markdown-cleaned** numbered block with metadata
     → parent_content and chunk content cleaned via clean_for_embedding()
     → strips bold, links, images, list markers — saves LLM tokens
     → code blocks and tables preserved
     → context_tokens calculated on actual formatted text (not sum of chunk sizes)
     → wrapped in <documentation_context> XML tags
  10. Build LLM messages (5-part sequence for implicit caching):
      a. System message — per-type prompt (base.md + {query_type}.md):
         <role>, <constraints> (10 rules), <format_rules>, <task_type>, <instructions>
      b. User message — documentation context
      c. Assistant ack — "Understood. I will use the documentation context..."
      d. History — last 6 messages, up to 8,000 tokens (trims oldest first)
         - Long conversation history summarized via LLM (summary_model: gemini-2.5-flash) when messages exceed summary_threshold (default 8)
      e. User query — with chunk count hint + anchor phrase
        │
        ▼
LLM Streaming (llm/client.py):
  Provider: Gemini 2.5 Pro (main chat), configurable via openai_llm_model
  → reasoning_effort configurable (default "low")
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

**Web Search augmentation** (if configured):
- For queries where documentation context is insufficient
- Gemini generates search queries, fetches web results
- Web context added to LLM prompt alongside documentation
- Configurable: `web_search_enabled` (default true), `web_search_model` (gemini-2.5-flash)

**Anti-hallucination strategy:**
- **Structured grounding prompt**: 9 constraints in `<constraints>` XML section, following Google's recommendations for Gemini
- **Separate system/context/ack message pattern**: enables Gemini implicit caching of static instructions
- **Hybrid retrieval (BM25 + vector)**: RRF fusion of semantic vector search and lexical BM25 full-text search; BM25 uses `'english'` stemmer on `content_clean` (Markdown-stripped) column; catches exact API paths and codes that bi-encoder may miss
- **Configurable re-ranking**: bi-encoder+BM25 retrieve 20 candidates; two providers: LLM reranker (Gemini Flash, structured JSON output) or Vertex AI Ranking API (cross-encoder); LLM relevance scores normalized to [0, 1] for accurate threshold filtering
- **HyDE (Hypothetical Document Embedding)**: for code/technical/troubleshooting queries, generates a hypothetical answer and embeds it instead of the raw query — bridges vocabulary gap between user questions and documentation
- **Small-to-big context**: search by small chunks (precision), expand to full section in LLM context (completeness); parent content deduplicated via `chunk_parents` table (SHA-256 hash → `parent_id` FK); context_tokens based on actual formatted text
- **Document title enrichment**: generic headings ("Document", "Preamble") replaced with actual document title for meaningful embedding context
- **LLM metadata enrichment**: Gemini Flash extracts `doc_type` and `entities` per chunk; embedding prefix includes `[type: api_reference]` and `[entities: ...]` for semantically richer vectors
- **Contextual embeddings**: Markdown-cleaned content with `[heading_path] + [type] + [entities]` prefix for topic-aware retrieval
- **Code-block-aware parsing**: headings inside fenced code blocks (```...```) are ignored during section splitting, preventing false document structure from shell comments, YAML comments, etc.
- **Text cleaning pipeline**: Markdown artifacts (bold, links, images, HTML, blockquotes, list markers) stripped before embedding, BM25 indexing, reranker scoring, AND LLM context; bold/italic/strikethrough regexes are line-scoped (no cross-line greed); both single and double backtick inline code handled; code blocks preserved
- **Enrichment truncation guard**: enriched text exceeding 500 tokens is truncated with a warning log; **heading_path prefix preserved intact** — only content is truncated
- **Smart chunk merging**: when small chunks are merged, heading_path combines both paths and token_count is recalculated on actual merged text (not just summed)
- **Chunk quality monitoring**: after chunking, min/max/avg/median token counts and parent_content statistics are logged for production quality tracking
- **Unicode normalization**: NFKC normalization at parser input ensures consistent matching
- **Token-safe chunking**: `chunk_max_tokens=512`, `chunk_min_tokens=50`; accurate token counting via `tiktoken` cl100k_base (fallback: `len(words) * 1.3`); 2-block overlap at split boundaries
- **Semantic chunking** (optional): flat sections without headings can be split by embedding similarity boundaries; disabled by default (`semantic_chunking_enabled=false`); threshold: 1500 tokens, percentile: 25th
- **Similarity threshold filtering**: `rag_min_similarity` (default 0.35) applied after Gemini re-ranking using normalized score; removes low-relevance chunks before they reach the LLM
- **Factual grounding**: API details (endpoints, params, URLs) must come from context only; code generation allowed using general programming knowledge based on documented API details
- **Language enforcement**: "CRITICAL: ALWAYS respond in the same language as the user's question" — top-level instruction
- Source attribution: each answer references numbered sources that the user can verify
- RAG debug info (search similarity, rewrite_ms, rerank_ms, query rewrite result) available in response metadata

---

## Reindex / Reingest Flow

```
Trigger: User clicks "Reindex" button on ProductsPage
  → ConfirmDialog → POST /api/v1/products/{id}/reingest
        │
        ▼
Server (products/router.py):
  1. Load all documents for product
  2. For each document:
     - If status = "ready" or "error":
       → delete existing chunks
       → reset status to "pending", clear error_message
     - If status = "pending" (stuck/lost task):
       → keep as-is (re-queue only)
     - If status = "processing":
       → re-queue (worker will handle dedup)
  3. Commit DB changes
  4. For EVERY document: ingest_document_task.delay(doc.id)
     → re-queues stuck pending + re-processes ready/error
        │
        ▼
Celery Worker: normal ingestion pipeline
  (download S3 → convert → chunk → embed → store)
        │
        ▼
Frontend: polls product list (5s interval when pending/processing)
  → status badge updates in real-time
```

**Single document reingest** (`POST /documents/{id}/reingest`):
- Same logic but for one document
- Clears chunks, resets to pending, queues Celery task
- Works for any status (ready, error, pending, processing)

**Requeue pending** (`POST /documents/requeue-pending`):
- Re-queues ALL documents with status "pending" globally
- Use when Celery tasks were lost (e.g. worker crash/restart)
- Does NOT reset status or clear chunks — only re-dispatches tasks

**Reindex jobs** (`POST /reindex/jobs`):
- Async background job for bulk reindex operations
- Two modes: `reingest` (full re-processing) or `reembed` (only re-generate embeddings)
- Optional filters: product_name, format_filter
- Progress tracking via heartbeat, stale detection via Celery Beat

---

## Frontend Routing Flow

```
User opens https://ai-mentor.ru/ (or http://localhost/)
        │
        ▼
nginx: try_files $uri $uri/ /index.html (SPA fallback)
        │
        ▼
React app (main.tsx): BrowserRouter wraps <App />
        │
        ▼
App.tsx: react-router-dom <Routes> resolves path:
  ┌──────────────────────────────────────────────────────────────────────────────────┐
  │ PATH                                    │ COMPONENT          │ DESCRIPTION               │
  │─────────────────────────────────────────┼────────────────────┼───────────────────────────│
  │ /                                       │ LandingPage        │ Public marketing page     │
  │ /login                                  │ LoginPage          │ Login (guest only)        │
  │ /register                               │ RegisterPage       │ Registration (guest only) │
  │ /s/:token                               │ SharedView         │ Public shared view        │
  │ /app                                    │ ChatApp            │ Chat application (Layout) │
  │ /app/documents                          │ DocumentsPage      │ Document management       │
  │ /app/products                           │ ProductsPage       │ Product list + reingest   │
  │ /app/products/:manufacturer/:product    │ ProductDetailPage  │ Product detail + docs     │
  │ /app/analytics                          │ AnalyticsPage      │ User analytics dashboard  │
  │ /app/settings                           │ SettingsPage       │ Account settings          │
  │ /app/admin/*                            │ AdminApp           │ Admin panel (role-based)  │
  │ *                                       │ Navigate to /      │ Fallback redirect         │
  └──────────────────────────────────────────────────────────────────────────────────┘
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

AdminApp (/app/admin):
  - Dashboard, Tenants, Documents, Chat audit, Roles, Prompts, Logs, Stats
  - Requires admin permission (role-based access)
```

**Key files:**
- `frontend/src/main.tsx` — `BrowserRouter` wrapper
- `frontend/src/App.tsx` — `Routes` definition
- `frontend/src/pages/LandingPage.tsx` — marketing landing page
- `frontend/src/pages/ChatApp.tsx` — chat application (extracted from original `App.tsx`)
- `frontend/src/pages/ProductsPage.tsx` — product list with reindex, edit, delete, debug
- `frontend/src/pages/DocumentsPage.tsx` — document list with reingest, download, delete
- `frontend/src/pages/ProductDetailPage.tsx` — product detail with embedded documents list
- `frontend/src/styles/landing.css` — landing page styles (responsive)
- `frontend/nginx.conf` — `try_files` SPA fallback, `/api/` proxy to `api:8000`
