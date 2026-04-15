# Lexiro — Monetization & Pricing

> Part of [Lexiro Architecture](PLAN.md)
>
> **Pricing rationale, market sizing, competitive analysis, and revenue projections**: see [Market Research & Competitive Analysis](MARKET_RESEARCH.md)
>
> **Infrastructure cost breakdown, unit economics, break-even analysis**: see [Infrastructure Cost Analysis](INFRASTRUCTURE_COSTS.md)

---

## Two-Sided Marketplace

Lexiro is a two-sided marketplace with a network effect (flywheel):

```
  SUPPLY (Vendors)                              DEMAND (Developers)
  ─────────────────                             ────────────────────
  Hikvision ──┐                                 ┌── Solo developers
  Dahua    ───┤    publish docs     search      ├── Integration companies
  Axis     ───┼──────────────► Lexiro ────────►├── Enterprise SI
  Bosch    ───┤    firmware,        via MCP      └── Device manufacturers
  100+ more ──┘    API specs        + REST API

  Flywheel:
    More vendors → more docs → more developers → more integrations
    → vendors see value → more vendors → ...
```

---

## Billing Unit

**Charge per incoming request.** Ingestion cost varies by format complexity. **AI Chat queries are billed per model (input + output)** — see [AI Model Tiers](#ai-model-tiers) below.

| Operation | Billable Units | Internal Cost | Reason |
|-----------|:-:|-----|--------|
| **Search (vector only, no LLM)** | | | |
| `search_documentation(query)` | 1 | ~$0.0003 | Core product value |
| `get_api_endpoint(path)` | 1 | ~$0.0003 | Vector search |
| **AI Chat (LLM-powered, per-model billing)** | | | |
| Chat query — Gemini Flash (input) | per model | ~$0.002 | RAG context + history |
| Chat query — Gemini Flash (output) | per model | ~$0.002 | Generated answer |
| Chat query — Opus 4.6 (input) | per model | ~$0.020 | RAG context + history |
| Chat query — Opus 4.6 (output) | per model | ~$0.025 | Generated answer |
| **Ingestion (format-dependent)** | | | |
| `ingest: markdown (.md)` | **1** | ~$0.001 | Direct chunking, cheapest |
| `ingest: swagger/openapi (.json/.yaml)` | **1** | ~$0.001 | Structural parsing |
| `ingest: postman collection (.json)` | **1** | ~$0.001 | Convert + chunk |
| `ingest: pdf (text-based)` | **2** | ~$0.005 | Text extraction overhead |
| `ingest: pdf (scanned / OCR)` | **5** | ~$0.02 | GPU OCR — 10-50x costlier |
| `ingest: web page (URL)` | **2** | ~$0.003 | Scraping + HTML cleanup |
| **Downloads** | | | |
| `download_document` | 1 | ~$0.001 | S3 presigned URL, tier-gated |
| **Free operations** | | | |
| `list_products()` | 0 | — | Simple SELECT, improves UX |
| Returned chunks (response) | 0 | — | Our delivery — maximize value |
| **Storage** | | | |
| S3 + pgvector storage | MB/mo | — | Ongoing infrastructure cost |

**Why per-model billing for AI Chat**: Opus 4.6 output tokens cost 10x more than Gemini Flash ($25 vs $2.50 per 1M). A flat rate would either overprice Flash users or subsidize Opus users at a loss. Per-model input+output billing keeps every query margin-positive.

**Why format-based pricing for ingestion**: OCR of a scanned 200-page PDF costs ~$0.02 in compute (GPU time + API calls), while parsing a Swagger JSON costs ~$0.001. Charging a flat rate would subsidize expensive formats at the expense of cheap ones.

---

## AI Model Tiers

Lexiro offers two LLM models for AI Chat. The model determines answer quality and cost. Different developer tiers get different default models.

### Model Pricing (user-facing)

**Per-token rates (implemented in `billing/pricing.py` as `MODEL_CHARGE`):**

| Model | Input (per 1M tokens) | Output (per 1M tokens) | Avg total per query | Quality |
|-------|:---------------------:|:----------------------:|:-------------------:|:-------:|
| **Gemini 2.5 Flash** | **$0.50** | **$4.00** | **~$0.005** | Good |
| **Gemini 2.5 Flash Lite** | $0.25 | $2.00 | ~$0.003 | Basic |
| **Gemini 2.5 Pro** | $2.50 | $20.00 | ~$0.030 | Very Good |
| **Claude Opus 4.6** | TBD | TBD | **~$0.045** | Excellent |

**COGS vs Charge (margin analysis):**

| Model | COGS Input/1M | COGS Output/1M | Charge Input/1M | Charge Output/1M | Margin |
|-------|:------------:|:--------------:|:---------------:|:----------------:|:------:|
| Gemini 2.5 Flash | $0.30 | $2.50 | $0.50 | $4.00 | ~60% |
| Gemini 2.5 Pro | $1.25 | $10.00 | $2.50 | $20.00 | ~100% |
| Claude Opus 4.6 | $5.00 | $25.00 | TBD | TBD | TBD |

> **Note**: COGS = actual LLM API price (what we pay the provider). Charge = user-facing price (what the client pays us). Both are recorded per-request in `usage_log` as `cogs_usd` and `charge_usd`. See [DATABASE.md](DATABASE.md#current-schema-implemented) for the full `usage_log` schema.

Actual billing is based on token count: input tokens (prompt + RAG context + history) and output tokens (generated answer) are metered separately and charged at the model's per-token rate. See [INFRASTRUCTURE_COSTS.md](INFRASTRUCTURE_COSTS.md#26-llm-api-for-rag-chat) for detailed cost analysis.

### Tier-to-Model Mapping

| Tier | Default Model | Opus 4.6 Access | Included AI Chat queries | Opus Overage |
|------|---------------|:---------------:|:------------------------:|:------------:|
| **Free** | Gemini Flash | No | 200/mo (Flash only) | blocked |
| **Pro** | Gemini Flash | Yes (option) | 10,000 Flash + 100 Opus/mo | $0.05/query |
| **Team** | **Opus 4.6** | Default | 100,000 (Opus) | $0.04/query |
| **Enterprise** | **Opus 4.6** | Default | unlimited | custom |

**How it works for Pro users**: Pro users get Gemini Flash by default. They can switch to Opus 4.6 for individual queries or sessions. 100 Opus queries/mo are included; beyond that, overage of $0.05/query applies. This lets them experience the quality difference and creates natural upsell to Team.

**How it works for Team/Enterprise**: Opus 4.6 is the default model. Gemini Flash is also available if the user prefers speed over quality. All queries within the included quota use whichever model the user selects.

### Opus 4.6 as Anchor Product

Opus 4.6 serves as a **premium anchor** — a high-quality product that makes the standard offering (Gemini Flash) look like a great deal, while creating aspiration to upgrade:

```
Developer psychology:

  Free tier:  "This AI search is pretty good for free"
              → sees "Upgrade to Pro for Opus 4.6 AI" badge
              → upgrades to Pro ($99/mo)

  Pro tier:   Uses 100 Opus queries, notices better code generation
              → runs out of Opus quota, falls back to Flash
              → "I want Opus all the time" → upgrades to Team ($399/mo)

  Team tier:  Opus by default, unlimited
              → shares with team, everyone productive
              → "We need this for the whole org" → Enterprise ($1,999/mo)
```

The anchor effect: even if most queries run on Flash, the *existence* of Opus as a premium option increases perceived value of all tiers and drives upgrades.

### Future Promotional Lever

**Planned promotion**: temporarily waive output charges on Gemini Flash queries.

```
Campaign: "Free AI Answers — pay only for questions!"

  Normal Flash query:  $0.002 (input) + $0.002 (output) = $0.004
  Promo Flash query:   $0.002 (input) + $0.000 (output) = $0.002  ← 50% off

  Effect:
    - Drives user acquisition (half-price AI chat)
    - Input charge still covers vector search cost
    - Users experience Flash quality, see Opus upgrade path
    - When promo ends, users are hooked → either stay on Flash or upgrade to Opus
```

This lever can be activated/deactivated via configuration without code changes — the billing system already tracks input and output separately.

### Billing Audit Trail (Implemented)

Every billable event writes an immutable record to the `usage_log` table (partitioned by month). This provides a complete audit trail for billing reconciliation, dispute resolution, and margin analysis.

**What is recorded per request:**

```
usage_log record:
  channel          = "chat" | "mcp"
  action           = "chat_completion" | "search_documentation" | "get_api_endpoint"
  request_id       = UUID v4 (for deduplication)

  LLM metrics (from API):
    prompt_tokens      = 4,550    ← exact, from LLM API response
    completion_tokens  = 800      ← exact, from LLM API response

  Prompt decomposition (for audit — sum ≈ prompt_tokens):
    query_tokens           =    50   ← user's question
    context_tokens         = 3,000   ← RAG documentation chunks
    history_tokens         = 1,000   ← chat history
    system_prompt_tokens   =   500   ← system prompt + RAG header

  Cost tracking:
    cogs_usd    = $0.0034   ← what we pay Google (Gemini API)
    charge_usd  = $0.0055   ← what the client pays us
    margin      = $0.0021   ← our profit per request (~38%)
```

**Why dual cost tracking matters:**
- `cogs_usd` — for P&L, margin analysis, infrastructure planning
- `charge_usd` — for invoicing, Stripe metered billing, spending alerts
- If pricing changes, historical `cogs_usd` and `charge_usd` remain accurate for that period
- Raw token counts (`prompt_tokens`, `completion_tokens`) allow retroactive recalculation

**Implementation:** `billing/pricing.py` (MODEL_COGS + MODEL_CHARGE), `billing/usage_writer.py` (async writer), `db/schema.sql` (partitioned table). See [DATABASE.md](DATABASE.md#current-schema-implemented) for full schema.

---

## A. Developer Tiers (Demand Side)

Hybrid model: subscription + overage.
See [Market Research](MARKET_RESEARCH.md) for pricing rationale and competitive analysis.

| Tier | Price | AI Model | AI Chat/mo | Searches/mo | Documents | Products | Downloads/mo | Storage | MCP | Overage |
|------|-------|----------|:----------:|-------------|-----------|----------|:------------:|---------|:---:|---------|
| Free | $0 | Flash | 200 | 200 | 5 | 5 | **0** | 50 MB | 1 | blocked |
| Pro | $99/mo | Flash + 100 Opus | 10,000 | 10,000 | 100 | 50 | **50** | 2 GB | 5 | see below |
| Team | $399/mo | **Opus default** | 100,000 | 100,000 | 1,000 | unlimited | **unlimited** | 20 GB | 30 | see below |
| Enterprise | from $1,999/mo | **Opus default** | unlimited | unlimited | unlimited | unlimited | **unlimited** | 200 GB+ | unlimited | custom |

**Overage rates (Pro/Team only — Free is hard-blocked):**

| Resource | Pro Overage | Team Overage |
|----------|------------|--------------|
| AI Chat — Flash (input+output) | per-model token rate | per-model token rate |
| AI Chat — Opus 4.6 | +$0.05/query | +$0.04/query |
| Search query (vector, no LLM) | +$0.005/query | +$0.003/query |
| Document ingest (1 billable unit) | +$0.15/unit | +$0.10/unit |
| Download | +$0.10/file | +$0.05/file |
| Storage | +$3/GB/mo | +$2/GB/mo |

> **Note on ingest overage**: the overage is per **billable unit**, not per file. A scanned PDF (5 units) costs 5 × $0.15 = $0.75 in overage, while a Swagger file (1 unit) costs $0.15.

**Overage protection:**
- Email alerts at 80% and 100% of included quota
- Optional hard cap on overage (e.g., max $20/mo — then blocked)
- Enterprise — fixed price, no overage

**Billing example (Pro, $99/mo):**

```
March 2026, client "Acme Integrations":

  AI Chat (Flash):  9,200 queries (10,000 included) → $0
  AI Chat (Opus):   130 queries (100 included)
                    30 overage × $0.05 = $1.50

  Searches:  2,400 vector searches (10,000 included) → $0

  Documents: 85 ingested, breakdown by format:
             70 × markdown (1 unit each)  = 70 units
             10 × swagger  (1 unit each)  = 10 units
              3 × pdf text (2 units each) =  6 units
              2 × pdf OCR  (5 units each) = 10 units
             Total: 96 billable units (100 included) → $0

  Downloads: 62 downloaded (50 included)
             12 overage × $0.10 = $1.20

  Storage:   1.5 GB (2 GB included) → $0

  Total: $99.00 + $1.50 + $1.20 = $101.70

  Note: the 30 Opus overage queries cost us ~$1.50 in LLM API
  and we charge $1.50 — break-even on overage, but the $99 base
  subscription covers all included queries with strong margin.
```

---

## B. Vendor Tiers (Supply Side)

Device manufacturers publish documentation so developers can integrate with their devices.
Motivation: more integrations = more device sales.

**Supported vendor upload formats**: Markdown, Swagger/OpenAPI 2.0/3.x, Postman Collections, PDF, web page URLs — same formats as tenant ingestion, same parsers.

**What is FREE for all vendors (including Basic):**
- Publishing documentation in **any supported format** (PDF, Markdown, Swagger/OpenAPI, Postman, web)
- Indexing and making documentation searchable by all developers
- Hosting documents in S3 storage (no storage fees for vendors)
- Basic device catalog listing
- Developer downloads of published documentation (default: `download_policy = public`)

Vendor documentation hosting is **free forever** — this is a strategic decision to fill the marketplace with content. More docs = more developers = stronger platform.

**What vendors PAY for (Pro / Enterprise / Platinum) — business tools on top of free hosting:**

| Feature | Basic ($0) | Pro ($499/mo) | Enterprise ($1,999/mo) | Platinum ($4,999/mo) |
|---------|:----------:|:-------------:|:----------------------:|:--------------------:|
| **Documentation & Indexing** | | | | |
| Publish standard docs (MD, Swagger, PDF) | Yes | Yes | Yes | Yes |
| Indexed & searchable by all devs | Yes | Yes | Yes | Yes |
| Document storage (S3) | Free | Free | Free | Free |
| Max devices | 20 | unlimited | unlimited | unlimited |
| Max documents | 50 | unlimited | unlimited | unlimited |
| New firmware indexing speed | Queue (1-24h) | Priority (< 1h) | SLA < 30 min | SLA < 15 min |
| **Firmware, SDK & Software Distribution** | | | | |
| Upload firmware binaries (.bin, .img, .hex) | Yes | Yes | Yes | Yes |
| Upload SDKs and tools (.zip, .exe, .msi) | Yes | Yes | Yes | Yes |
| SHA-256 integrity checksums (auto-generated) | Yes | Yes | Yes | Yes |
| Antivirus/malware scanning | Yes | Yes | Yes | Yes |
| Release notes (auto-indexed as searchable chunks) | Yes | Yes | Yes | Yes |
| Changelog diff vs previous version | — | Yes | Yes | Yes |
| New firmware notification to subscribed developers | — | Yes | Yes | Yes |
| SDK index (searchable library/API catalog) | — | — | Yes | Yes |
| Storage limit | **1 GB** | **50 GB** | **500 GB** | **unlimited** |
| **Custom Documentation Import** | | | | |
| Custom site scraper/importer development | — | — | — | **Included** |
| Auto-sync from vendor's doc portal | — | — | — | **Included** |
| Importer maintenance on site changes | — | — | — | **Included** |
| Dedicated integration engineer | — | — | — | **Yes** |
| Custom format support (CHM, Wiki, etc.) | — | — | — | **Yes** |
| **Download Control** | | | | |
| Download policy: `public` | Yes (default) | Yes | Yes | Yes |
| Download policy: `search_only` | — | Yes | Yes | Yes |
| Download policy: `pro_only` | — | Yes | Yes | Yes |
| Per-document download policy | — | Yes | Yes | Yes |
| **Visibility** | | | | |
| "Verified Vendor" badge | — | Yes | Yes | Yes |
| Highlighted in device catalog | — | Yes | Yes | Yes |
| "Featured Vendor" homepage placement | — | — | — | **Yes** |
| **Analytics** | | | | |
| Search volume per device | — | Yes | Yes | Yes |
| Most-searched API endpoints | — | Yes | Yes | Yes |
| Firmware version usage stats | — | Yes | Yes | Yes |
| Interest trend (growing/declining) | — | Yes | Yes | Yes |
| Competitive positioning (anonymized) | — | — | Yes | Yes |
| Geographic distribution (anonymized) | — | — | Yes | Yes |
| Documentation quality recommendations | — | — | Yes | Yes |
| Real-time analytics API | — | — | — | **Yes** |
| **Integrations** | | | | |
| Bulk upload API | — | Yes | Yes | Yes |
| New firmware notification API | — | Yes | Yes | Yes |
| Webhook: "new integration built" | — | — | Yes | Yes |
| CI/CD integration for auto-publish | — | — | Yes | Yes |
| Custom webhook events | — | — | — | **Yes** |
| **Support** | | | | |
| Community / self-service | Yes | Yes | Yes | Yes |
| Email support | — | Yes | Yes | Yes |
| Dedicated account manager | — | — | Yes | Yes |
| Co-marketing campaigns | — | — | Yes | Yes |
| Dedicated integration engineer | — | — | — | **Yes** |
| SLA for importer fixes | — | — | — | **24h response** |

---

## Custom Documentation Importer (Platinum)

Many device manufacturers publish API documentation on custom websites, proprietary portals, or non-standard formats (HTML tables, .chm files, custom wikis). Standard parsers cannot extract structured endpoint information from these sources.

With the Platinum tier, the Lexiro engineering team:
1. Analyzes the vendor's documentation portal structure
2. Develops a **custom scraper/parser** tailored to the vendor's site
3. Deploys it as a Celery task with **scheduled auto-sync** (daily/weekly)
4. Maintains the importer when the vendor's site structure changes
5. Provides a dedicated integration engineer for ongoing support

```
Example: Hikvision ISAPI Documentation

  Hikvision publishes ISAPI docs as HTML pages at doc.hikvision.com:
    /isapi/access-control/door-control.html
    /isapi/video/streaming.html
    ...each page has custom HTML tables with endpoints, parameters, examples

  Platinum service delivers:
    1. Custom scraper: crawl all /isapi/* pages
    2. Extract endpoints: path, method, params, response schema
    3. Generate structured chunks (same as Swagger parsing)
    4. Auto-sync every 24h → detect new/changed pages → re-index
    5. Notification: "12 new endpoints detected in latest update"

  Result: Hikvision's entire ISAPI documentation searchable via MCP
  within 1 week of signing Platinum contract
```

**Value proposition for Platinum ($4,999/mo):**

```
Vendor CTO reasoning:

"Our documentation portal is complex — 2,000+ pages, custom HTML format.
Converting to Swagger manually would cost $100,000+ in engineering time.

For $4,999/mo (~$60K/year) we get:
  - Full documentation indexed for AI code assistants (automatic)
  - Auto-sync: new firmware docs available to developers within 24h
  - No engineering effort on our side — Lexiro handles everything
  - Dedicated engineer who understands our doc structure
  - Featured placement in the developer catalog

This is 60% cheaper than doing it ourselves, and we don't need to
hire a team to maintain Swagger specs."
```

**Why a vendor would pay $499/mo (value proposition):**

```
Vendor marketing manager reasoning:

"We spend $50,000/mo on marketing to integrators.
For $499/mo with Lexiro we learn:
  - 342 developers searched our cameras this week
  - Top query: 'night vision API DS-2CD2347' → need to improve those docs
  - Firmware V5.6 still in 40% of searches → don't drop support yet
  - Interest grew 15% this month → our marketing is working
  - 'Verified' badge means developers trust our docs first

This costs less than a single $10,000 trade show booth."
```

**Vendor API (Pro/Enterprise):**

```
POST /vendor/v1/documents/publish     — bulk documentation upload
POST /vendor/v1/firmware/notify       — new firmware release notification
GET  /vendor/v1/analytics/searches    — search statistics per device
GET  /vendor/v1/analytics/trends      — usage trends over time
GET  /vendor/v1/analytics/top-queries — most searched queries for your devices
Webhook (Enterprise)                  — "new integration built" event
```

---

## Marketplace Launch Strategy

| Phase | Trigger | Vendor pricing |
|-------|---------|---------------|
| Phase 1 (launch) | 0-50 vendors | All vendors free (Basic) — fill the catalog |
| Phase 2 (traction) | 50+ vendors, 500+ developers | Launch Vendor Pro ($499/mo) |
| Phase 3 (scale) | 200+ vendors | Launch Vendor Enterprise ($1,999/mo) |
| Phase 4 (premium) | 5+ Enterprise vendors | Launch Vendor Platinum ($4,999/mo) — custom importers |

---

## Revenue Streams Summary

| Revenue Stream | Source | Model | Expected Share |
|----------------|--------|-------|---------------|
| Developer subscriptions (Pro/Team/Enterprise) | Integrators, developers | Hybrid (base + overage) | 40-50% |
| Developer overage (search, ingest, downloads) | Pro/Team exceeding limits | Per-unit charge | 10-15% |
| Vendor subscriptions (Pro/Enterprise) | Device manufacturers | Monthly subscription | 15-25% |
| Vendor Platinum (custom importers) | Large manufacturers | Premium subscription | 10-20% |
| Enterprise contracts (large SIs + vendors) | Annual agreements | Custom pricing | 10-15% |
