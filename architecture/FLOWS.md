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
Celery Worker (×4, concurrency=4): ingest_document(document_id)
  0. **Progress: 0% — "converting"** (persisted to documents.progress_percent/progress_stage)
  1. Download original from S3
  2. Route to format-specific converter:
     ┌─────────────────────────────────────────────────────────────────────────────┐
     │ FORMAT         │ CONVERTER / PARSER          │ CHUNKING STRATEGY            │
     │────────────────┼─────────────────────────────┼──────────────────────────────│
     │ markdown       │ parsers/markdown.py         │ H1–H6 headers                │
     │ swagger/openapi│ converters/swagger.py       │ 1 chunk per endpoint         │
     │ pdf (text)     │ converters/pdf.py           │ pymupdf4llm → parallel → hdr │
     │ pdf (OCR)      │ converters/pdf.py + EasyOCR │ OCR → text → headers         │
     │ web (URL)      │ converters/web.py           │ Scrape → clean → H1–6        │
     │ protobuf       │ converters/proto.py         │ service/method/message        │
     └─────────────────────────────────────────────────────────────────────────────┘

     **PDF parallel conversion** (>10 pages):
     - Pages split into fixed-size chunks of 50 pages (`PAGES_PER_CHUNK=50`)
     - Processed in parallel via `ThreadPoolExecutor(max_workers=4)`
       (`ProcessPoolExecutor` not used — Celery workers are daemon processes)
     - Each chunk retried up to 2 times with linear backoff (`MAX_RETRIES=2`)
     - Progress callback reports conversion fraction (0→1) after each chunk completes
     - **Progress: 0%→25% — "converting"** (incremental for PDF, instant for other formats)

     **PDF OCR with auto language detection** (pass 2, if images detected):
     - After text extraction, language detected via Gemini (`generate_content`)
       using first ~3000 chars of extracted text
     - Gemini returns ISO 639-1 codes, mapped to EasyOCR codes (e.g. zh→ch_sim)
     - EasyOCR initialized with detected language(s), CPU-only PyTorch
     - Each image processed in try/except — failures don't break the pipeline
     - OCR metrics collected: total/success/empty/failed image counts
     - **Progress: 25%→40% — "ocr"** (incremental per image)
  3. Unicode normalization (NFKC) on raw text input
     - Collapses fullwidth Latin, ligatures, non-breaking spaces
     - Ensures byte-identical text for deduplication and embedding
  4. Code-block-aware heading extraction (markdown.py):
     - Regex finds H1–H6 headings (^#{1,6}\s+)
     - **Fenced code block protection**: pre-scan for ```...``` ranges;
       any heading match inside a code block is skipped
     - Prevents false section splits on shell comments (# comment),
       YAML comments, Python decorators, etc.
  5. Heading cleaning (text_cleaner.py):
     - Strip Markdown formatting from heading text (bold, italic, links, images, HTML)
     - Handles both single (`) and double (``) backtick inline code
     - Clean headings used in heading_path and embedding enrichment
  6. Common post-processing (chunker.py):
     a. Split into atomic blocks:
        - Code fences (```...```) and tables preserved as indivisible units
        - Remaining text split by paragraph boundaries (\n\n)
     b. Split large sections (>380 tokens, configurable) across block boundaries
        - Token count via real E5 tokenizer (XLM-RoBERTa) when available,
          fallback to word-based heuristic (len(words) * 1.3)
        - Token limit aligned with E5 model max_seq_length (514 tokens)
          minus room for heading_path prefix and "passage:" prefix
        - 2-paragraph overlap between consecutive pieces (configurable)
        - parent_content field stores full section text for context expansion
     c. Merge small sections (<30 tokens, configurable) with same-parent neighbor
        - heading_path of both chunks combined ("A + B") when different
        - token_count recalculated on merged text (not just summed)
        - parent_content preserved during merge
     d. Preserve heading_path hierarchy (e.g. "API > Doors > Open")
  7. **Document title enrichment** (pipeline.py):
     - Generic heading_paths "Document" and "Preamble" replaced with actual
       document title (from filename or metadata)
     - "Document" → "{title}", "Preamble" → "{title} > Preamble"
     - Ensures every chunk carries meaningful topic context for embedding
  8. Contextual enrichment for embedding (pipeline.py):
     a. Clean Markdown artifacts from content (text_cleaner.py):
        - Strip bold/italic/strikethrough formatting (line-scoped, no cross-line greed)
        - Convert links to plain text (keep anchor, drop URL)
        - Remove images entirely
        - Strip HTML tags, bare URLs, blockquote markers (>)
        - **Strip list markers** (-, *, +, 1., 2., etc.) preserving indentation
        - Handle both single and double backtick inline code
        - Preserve code blocks (contain valuable API details)
     b. Prepend "[heading_path]" to cleaned text (all heading paths enriched)
     c. **Truncation guard**: if enriched text exceeds 500 tokens (model limit),
        log warning and truncate **only the content part**, preserving the
        heading_path prefix intact
     d. Original Markdown content stored in DB unchanged (for display)
     e. Cleaned content also stored in `content_clean` column for BM25 indexing
  9. **Chunk quality logging** (pipeline.py):
     - After chunking, log min/max/avg/median token counts, parent_content stats
     - Enables production monitoring of chunk size distribution
     - **Progress: 40%→50% — "chunking"**
  10. Embed all enriched chunks in batches (embedder.py)
     - Gemini: gemini-embedding-2-preview (google-genai SDK), task_type=RETRIEVAL_DOCUMENT, Matryoshka dims
     - **Batch size**: 100 texts per API call (`BATCH_SIZE=100`, Gemini API limit)
     - **Incremental progress**: callback after each batch → `50% + (batch/total) * 40%`
     - **Progress: 50%→90% — "embedding"**
  11. **Progress: 92% — "storing"**
     INSERT chunks (content, content_clean, parent_content, embedding) into pgvector
     - `content_clean` — Markdown-stripped text for BM25 full-text indexing
     - PostgreSQL trigger builds tsvector from `COALESCE(content_clean, content)`
       with **'english' stemmer** (stemming + stop-word removal)
  12. UPDATE document SET status='ready', total_chunks=N, **progress_percent=100, progress_stage=''**
  13. Log usage (billable_units, tokens consumed, duration)
```

**Swagger/OpenAPI special handling:**
- Parse with `openapi-spec-validator` + custom endpoint extractor
- Each endpoint → 1 chunk containing: path, method, summary, parameters, request body schema, response schema, examples
- `heading_path` = endpoint path (e.g., `"POST /acs/v1/door/doControl"`)
- Enables exact path matching in `get_api_endpoint()` tool (not just vector similarity)

**PDF parallel conversion & fault tolerance** (`converters/pdf.py`):
- **Parallel threshold**: PDFs with >10 pages are processed in parallel
- **Chunk size**: fixed 50-page chunks (`PAGES_PER_CHUNK=50`) for granular progress
- **Workers**: `ThreadPoolExecutor(max_workers=4)` — uses threads (not processes) because Celery daemon workers cannot spawn child processes
- **Retry**: each 50-page chunk retried up to 2 times (`MAX_RETRIES=2`) with linear backoff (`time.sleep(attempt)`)
- **Progress callback**: `progress_callback(fraction, stage)` called after each chunk; fraction scaled by `convert_pdf` based on whether OCR will follow
- Small PDFs (≤10 pages): single `pymupdf4llm.to_markdown()` call with same retry logic

**PDF OCR pipeline** (two-pass, `converters/pdf.py`):
- **Pass 1**: `pymupdf4llm.to_markdown()` — text layer extraction (parallel for >10 pages)
- **Language detection**: Gemini `generate_content` on first ~3000 chars of extracted MD text
  - Model: `gemini-2.5-flash` (configurable via `ocr_lang_detect_model`)
  - Returns ISO 639-1 codes, mapped to EasyOCR codes (`_LANG_MAP`: zh→ch_sim, zh-tw→ch_tra, etc.)
  - Fallback: `["en"]` on any error (no Gemini API key, API failure, empty text)
  - Detected language saved to `documents.detected_language`
- **Pass 2**: `_enrich_markdown_with_ocr()` — OCR images with auto-detected language
  - EasyOCR initialized with detected language(s), CPU-only PyTorch
  - Each image processed in try/except — failures logged but don't break the pipeline
  - Images below `_OCR_IMAGE_MIN_AREA` (100K pixels) skipped
  - Progress callback: `ocr_progress_callback(processed / total_images)`
- **OCR metrics** saved to `documents` table:
  - `ocr_ms` — total OCR time
  - `ocr_images_total` / `ocr_images_success` / `ocr_images_empty` / `ocr_images_failed`
- **Dependencies**: `torch` (CPU-only), `torchvision`, `easyocr>=1.7.0`
- **Dockerfile**: `libgl1-mesa-glx`, `libglib2.0-0` added for OpenCV (EasyOCR dependency)

**Ingestion progress tracking** (`pipeline.py` → `documents` table):
- `progress_percent` (INT, 0–100) and `progress_stage` (TEXT) persisted to DB after each stage
- Frontend polls `GET /api/v1/documents/` and displays real-time progress bar with stage label
- Progress stages and percentages:

| Stage | Percent Range | Description |
|-------|:---:|---|
| `converting` | 0%→25% (with OCR) or 0%→40% (no OCR) | Format conversion (PDF: incremental per chunk, others: instant to 40%) |
| `ocr` | 25%→40% | OCR image recognition (PDF only, if images detected; includes language detection) |
| `chunking` | 40%→50% | Parse → section split → chunk → merge |
| `embedding` | 50%→90% | Gemini API batches (100 texts/batch), incremental per batch |
| `storing` | 92% | INSERT chunks + UPDATE document in PostgreSQL |
| *(complete)* | 100% | `status='ready'`, `progress_stage=''` |

- For non-PDF or PDF without images: `converting` jumps from 25% to 40% (no OCR stage)
- On error: `progress_percent=0`, `progress_stage=''`, `status='error'`
- UI: `StatusBadge` component shows animated progress bar + localized stage label
- Debug panel: `TimingBar` shows all 6 timing stages (Read, Convert, **OCR**, Parse, Embed, DB Write) with `MIN_PCT=3` minimum width even for 0ms stages
- Debug panel: separate **OCR section** shows image metrics (total/success/empty/failed) when `ocr_images_total` is not null
- Debug panel: **detected_language** shown in File section

---

## Supported Document Formats

All formats are normalized to **chunks** in pgvector. The original file is preserved in S3 in its native format.

| Format | Extensions | Parser | Billable Units | Internal Cost | Notes |
|--------|-----------|--------|:-:|-----|-------|
| Markdown | `.md` | H1–H6 header chunking, code/table protection | **1** | ~$0.001 | Cheapest, base format |
| Swagger / OpenAPI 2.0/3.x | `.json`, `.yaml` | Structural: 1 chunk per endpoint | **1** | ~$0.001 | Highest value — structured endpoints, exact match possible |
| Postman Collection v2.1 | `.json` | Convert requests → endpoint docs | **1** | ~$0.001 | Preserves request/response examples |
| PDF (text-based) | `.pdf` | PyMuPDF → parallel ThreadPoolExecutor (50-page chunks) → chunking | **2** | ~$0.005 | 2x cost — parallel conversion with retry |
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
     → word-boundary regex matching, longer names prioritised
  2. LLM Query Classification (parallel with rewrite):
     → lightweight call to Gemini 2.0 Flash (~100ms, ~20 output tokens)
     → classifies into: overview | technical | code | comparison | troubleshooting | chitchat
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
  4. Embed rewritten query → vector [0.023, -0.118, ...]
     → "query:" prefix for E5 models
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
  6. Cross-encoder re-ranking (reranker.py):
     → **multilingual cross-encoder** (mmarco-mMiniLMv2-L12-H384-v1, 100+ languages)
     → scores each (query, cleaned_enriched_text) pair
     → text cleaned from Markdown artifacts (same as embedding pipeline)
     → enriched with "[heading_path]\n{cleaned_content}" for topic-aware scoring
     → **similarity updated to sigmoid(rerank_score)** — normalized [0, 1]
     → raw `rerank_score` preserved for debugging; original dicts not mutated
     → top rag_top_k (default 10) results kept after re-ranking
     → configurable: rerank_enabled (default true)
  7. Similarity threshold filtering:
     → discard chunks with similarity < rag_min_similarity (default 0.35)
     → after re-ranking, uses the sigmoid-normalized cross-encoder score
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
      e. User query — with chunk count hint + anchor phrase
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
- **Hybrid retrieval (BM25 + vector)**: RRF fusion of semantic vector search and lexical BM25 full-text search; BM25 uses `'english'` stemmer on `content_clean` (Markdown-stripped) column; catches exact API paths and codes that bi-encoder may miss
- **Multilingual cross-encoder re-ranking**: bi-encoder+BM25 retrieve 20 candidates, multilingual cross-encoder (mmarco-mMiniLMv2-L12-H384-v1, 100+ languages) re-scores Markdown-cleaned enriched text; similarity updated to sigmoid(rerank_score) for accurate threshold filtering
- **Small-to-big context**: search by small chunks (precision), expand to full Markdown-cleaned section in LLM context (completeness); parent deduplication via SHA-256 hash; context_tokens based on actual formatted text
- **Document title enrichment**: generic headings ("Document", "Preamble") replaced with actual document title for meaningful embedding context
- **Contextual embeddings**: Markdown-cleaned content with heading_path prefix for topic-aware retrieval; all heading paths enriched (no skip for generic headings)
- **Code-block-aware parsing**: headings inside fenced code blocks (```...```) are ignored during section splitting, preventing false document structure from shell comments, YAML comments, etc.
- **Text cleaning pipeline**: Markdown artifacts (bold, links, images, HTML, blockquotes, list markers) stripped before embedding, BM25 indexing, cross-encoder scoring, AND LLM context; bold/italic/strikethrough regexes are line-scoped (no cross-line greed); both single and double backtick inline code handled; code blocks preserved
- **Enrichment truncation guard**: enriched text exceeding 500 tokens is truncated with a warning log; **heading_path prefix preserved intact** — only content is truncated
- **Smart chunk merging**: when small chunks are merged, heading_path combines both paths and token_count is recalculated on actual merged text (not just summed)
- **Chunk quality monitoring**: after chunking, min/max/avg/median token counts and parent_content statistics are logged for production quality tracking
- **Unicode normalization**: NFKC normalization at parser input ensures consistent matching
- **Token-safe chunking**: max_tokens=380 aligned with E5 max_seq_length=514; real E5 tokenizer used when available, preventing silent truncation
- **Similarity threshold filtering**: `rag_min_similarity` (default 0.35) applied after cross-encoder re-ranking using sigmoid-normalized score; removes low-relevance chunks before they reach the LLM
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
  │ /app/documents     │ DocumentsPage  │ Document management       │
  │ /app/products      │ ProductsPage   │ Product list + reingest   │
  │ /app/products/:id  │ ProductDetail  │ Product detail + docs     │
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
- `frontend/src/pages/ProductsPage.tsx` — product list with reindex, edit, delete, debug
- `frontend/src/pages/DocumentsPage.tsx` — document list with reingest, download, delete
- `frontend/src/pages/ProductDetailPage.tsx` — product detail with embedded documents list
- `frontend/src/styles/landing.css` — landing page styles (responsive)
- `frontend/nginx.conf` — `try_files` SPA fallback, `/api/` proxy to `api:8000`
