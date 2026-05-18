# AI Mentor — Infrastructure Cost Analysis

> **Status**: v1.4 — March 19, 2026 (actual Gemini/Opus prices, tiered LLM billing, per-model input+output pricing)
> **Author**: Oleg Voitekhovich
> **Purpose**: Detailed infrastructure cost breakdown by component, scenario-based projections, and cost-to-revenue analysis to validate pricing model

---

## 1. Cost Components Overview

```
                     AI Mentor Infrastructure Cost Stack

 ┌─────────────────────────────────────────────────────────────┐
 │                      COMPUTE                                │
 │  FastAPI servers  │  Celery workers  │  Celery Beat         │
 │  (API + MCP)      │  (ingest + scan) │  (scheduler)         │
 └──────────┬────────┴────────┬─────────┴──────────────────────┘
            │                 │
 ┌──────────▼─────────────────▼────────────────────────────────┐
 │                      DATA STORES                            │
 │  PostgreSQL + pgvector  │  Redis  │  MinIO/S3               │
 │  (chunks, metadata)     │  (cache,│  (docs, firmware, SDK)  │
 │                         │  queue) │                         │
 └──────────┬──────────────┴────┬────┴─────────┬───────────────┘
            │                   │              │
 ┌──────────▼───────────────────▼──────────────▼───────────────┐
 │                   EXTERNAL SERVICES                         │
│  Gemini API     │  LLM API    │  Stripe     │  SendGrid    │
│  (embeddings)   │  (Gemini /  │  (billing)  │  (email)     │
 │                 │  Opus 4.6)  │             │              │
 │                 │             │             │              │
 │                 │  ClamAV     │             │              │
 │                 │  (antivirus)│             │              │
 └─────────────────┴─────────────┴─────────────┴──────────────┘
```

---

## 2. Per-Component Cost Breakdown

### 2.1 Compute (Application Servers)

| Component | Instances | Spec | Monthly Cost |
|-----------|:---------:|------|:------------:|
| FastAPI + MCP server | 2-3 | 2 vCPU, 4 GB RAM | $60-150/ea |
| Celery worker (ingest + embed) | 2-4 | 4 vCPU, 8 GB RAM | $120-240/ea |
| Celery worker (ClamAV scan) | 1 | 2 vCPU, 4 GB RAM | $60-120 |
| Celery Beat (scheduler) | 1 | 1 vCPU, 1 GB RAM | $15-30 |

| Scale | Total Compute |
|-------|:------------:|
| Small (100 users) | **$300-600/mo** |
| Medium (500 users) | **$700-1,500/mo** |
| Large (2,000 users) | **$1,500-3,000/mo** |

### 2.2 PostgreSQL + pgvector

| Scale | Configuration | Monthly Cost |
|-------|--------------|:------------:|
| Small | Single instance, 4 vCPU, 16 GB RAM, 100 GB SSD | $200-400 |
| Medium | Primary + read replica, 8 vCPU, 32 GB RAM, 500 GB | $800-1,500 |
| Large | Managed (RDS/Cloud SQL), HA, 16 vCPU, 64 GB RAM, 1 TB | $1,500-3,000 |

**Key cost driver**: pgvector index size. With `halfvec(768)`: each chunk = 768 dims × 2 bytes = 1.5 KB for the vector. 1M chunks ≈ 1.5 GB for vectors + overhead. This is **~3.5× smaller** than the previous `vector(1024)` layout (768×2 = 1,536 bytes vs 1024×4 = 4,096 bytes per vector).

| Chunks in DB | Vector Storage (halfvec 768) | Previous (vector 1024) | Savings |
|:------------:|:--------------:|:--------------:|:------:|
| 100K | 150 MB | 410 MB | 63% |
| 500K | 750 MB | 2 GB | 63% |
| 1M | 1.5 GB | 4 GB | 63% |
| 5M | 7.5 GB | 20 GB | 63% |

### 2.3 Redis

| Scale | Configuration | Monthly Cost |
|-------|--------------|:------------:|
| Small | Single instance, 1 GB | $15-30 |
| Medium | 2 GB, persistence | $50-100 |
| Large | Managed (ElastiCache), 4 GB, HA | $150-300 |

Redis usage is lightweight: rate limiting counters + Celery broker. Not a significant cost driver.

### 2.4 S3 / Object Storage

#### Storage Costs

| Content Type | Avg Size | Cost/GB/mo | Notes |
|-------------|:--------:|:----------:|-------|
| Documentation (MD, JSON, YAML) | 100 KB - 5 MB | $0.023 | Negligible |
| PDF documents | 1 - 50 MB | $0.023 | Small |
| Firmware binaries | 10 - 500 MB | $0.023 | **Main storage cost** |
| SDKs and tools | 5 - 200 MB | $0.023 | Moderate |
| Vendor logos and assets | < 1 MB | $0.023 | Negligible |

| Scale | Stored Data | Monthly Storage Cost |
|-------|:-----------:|:--------------------:|
| Small (100 vendors × 1 GB avg) | 100 GB | **$2.30** |
| Medium (300 vendors × 5 GB avg) | 1.5 TB | **$34.50** |
| Large (500 vendors × 10 GB avg) | 5 TB | **$115** |

#### Egress (Download) Costs — THE REAL EXPENSE

| Content | Avg Download Size | Downloads/mo | Egress | Cost ($0.09/GB) |
|---------|:-----------------:|:------------:|:------:|:---------------:|
| Documentation | 500 KB | 5,000 | 2.5 GB | $0.22 |
| Firmware | 200 MB | 2,000 | 400 GB | **$36** |
| SDK | 100 MB | 1,000 | 100 GB | **$9** |
| Tools | 50 MB | 500 | 25 GB | $2.25 |
| **Total** | | **8,500** | **527 GB** | **$47.50/mo** |

At scale (10x):

| Scale | Egress/mo | Cost |
|-------|:---------:|:----:|
| Small | 500 GB | $45 |
| Medium | 2 TB | $180 |
| Large | 10 TB | **$900** |

**Optimization**: CloudFront/CDN caching for popular firmware → reduces egress 50-70%.

### 2.5 Embedding API

**Production default: Gemini Embedding 2** — $0.20/1M tokens (gemini-embedding-2-preview)
**Offline: Local** — $0 (intfloat/multilingual-e5-large, CPU-only, ~5.5 sec/chunk)

| Operation | Avg Tokens | Cost per op | Monthly Volume | Monthly Cost |
|-----------|:----------:|:-----------:|:--------------:|:------------:|
| Search query embedding | 50 tokens | $0.00001 | 100,000 queries | **$1.00** |
| Document ingestion (chunk) | 500 tokens | $0.0001 | 50,000 chunks | **$5.00** |
| Full doc ingestion (200 chunks) | 100K tokens | $0.02 | 500 documents | **$10.00** |

| Scale | Queries/mo | Ingests/mo | Gemini Monthly |
|-------|:----------:|:----------:|:--------------:|
| Small | 50K | 200 docs | **$5-15** |
| Medium | 300K | 1,000 docs | **$30-80** |
| Large | 2M | 5,000 docs | **$200-500** |

**Why Gemini**: AI Mentor serves users in 100+ countries. Gemini Embedding 2 leads MTEB Multilingual benchmarks (68.3) and significantly outperforms alternatives on non-English retrieval (Russian, Chinese, Arabic, etc.). Even at large scale it's < $500/mo.

### 2.6 LLM API (for RAG Chat)

Every chat query triggers an LLM call to generate the answer from retrieved documentation chunks. **Billing is per-model, input + output separately** — this protects margins regardless of which model the user selects. See [MONETIZATION.md](MONETIZATION.md#ai-model-tiers) for tier-to-model mapping.

#### 2.6.1 Gemini 2.5 Flash (default for Free & Pro)

**Pricing** (Google AI Studio, actual March 2026):

| Parameter | Value |
|-----------|:-----:|
| Input tokens | **$0.30 per 1M tokens** |
| Output tokens | **$2.50 per 1M tokens** |
| Free tier | 15 RPM, limited daily quota |

**Per-query cost (Gemini Flash):**

| Component | Tokens | Cost |
|-----------|:------:|:----:|
| System prompt + RAG context (8 chunks) | ~3,000–5,000 input | $0.0009–$0.0015 |
| Chat history (up to 10 messages) | ~1,000–2,000 input | $0.0003–$0.0006 |
| Generated answer | ~500–1,500 output | $0.00125–$0.00375 |
| **Total per query** | | **$0.0025–$0.006** |

**Monthly cost by scale (Gemini Flash only):**

| Scale | Queries/mo | Input Tokens | Output Tokens | Monthly Cost |
|-------|:----------:|:------------:|:------------:|:------------:|
| Small (100 users) | 50K | 200M | 50M | **$185** |
| Medium (500 users) | 300K | 1.2B | 300M | **$1,110** |
| Large (2,000 users) | 2M | 8B | 2B | **$7,400** |

#### 2.6.2 Claude Opus 4.6 (default for Team & Enterprise)

**Pricing** (Anthropic API, actual March 2026):

| Parameter | Value |
|-----------|:-----:|
| Input tokens | **$5.00 per 1M tokens** |
| Output tokens | **$25.00 per 1M tokens** |
| Prompt caching (cache reads) | **$0.50 per 1M tokens** (90% savings on cached input) |
| Batch processing | 50% savings |

**Per-query cost (Opus 4.6):**

| Component | Tokens | Cost |
|-----------|:------:|:----:|
| System prompt + RAG context (8 chunks) | ~3,000–5,000 input | $0.015–$0.025 |
| Chat history (up to 10 messages) | ~1,000–2,000 input | $0.005–$0.010 |
| Generated answer | ~500–1,500 output | $0.0125–$0.0375 |
| **Total per query** | | **$0.03–$0.07** |

With prompt caching (system prompt cached across session):

| Component | Tokens | Cost |
|-----------|:------:|:----:|
| System prompt (cached) | ~2,000 | $0.001 |
| RAG context + history (fresh) | ~2,000–5,000 | $0.010–$0.025 |
| Generated answer | ~500–1,500 output | $0.0125–$0.0375 |
| **Total per query (cached)** | | **$0.02–$0.06** |

#### 2.6.3 Blended cost (tiered model strategy)

Most queries (Free + Pro) use Gemini Flash. Premium queries (Team + Enterprise + Pro Opus option) use Opus 4.6. The ratio shifts as the customer base matures.

**Query distribution by tier (Medium scale, 500 users):**

| Tier | Model | % of queries | Queries/mo |
|------|-------|:------------:|:----------:|
| Free | Gemini Flash | 30% | 90K |
| Pro | Gemini Flash | 45% | 135K |
| Pro (Opus option) | Opus 4.6 | 3% | 9K |
| Team | Opus 4.6 | 15% | 45K |
| Enterprise | Opus 4.6 | 7% | 21K |

**Blended monthly LLM cost (Medium, 500 users):**

| Model | Queries | Cost |
|-------|:-------:|:----:|
| Gemini Flash (Free + Pro) | 225K | **$830** |
| Opus 4.6 (Pro option + Team + Ent) | 75K | **$3,750** (~$2,600 with caching) |
| **Total blended** | 300K | **$3,430–$4,580** |

Compare: all-Gemini at this scale = $1,110. The premium tier adds ~$2,300–3,500/mo in LLM cost, but generates significantly more revenue from Team ($399/mo) and Enterprise ($1,999/mo) subscriptions. See section 9 for revenue cross-check.

#### 2.6.4 Model comparison

| Model | Input / Output (per 1M tokens) | Cost per query | Ratio vs Flash | Quality | Tier |
|-------|:------------------------------:|:--------------:|:--------------:|:-------:|------|
| Gemini 2.5 Flash | $0.30 / $2.50 | $0.003–0.006 | 1x | Good | Free, Pro (default) |
| Claude Opus 4.6 | $5.00 / $25.00 | $0.03–0.07 | ~13x | Excellent | Team, Enterprise, Pro (option) |
| Opus 4.6 (cached) | $0.50 / $25.00 | $0.02–0.06 | ~10x | Excellent | Same, optimized |
| Ollama (qwen2.5) | $0 (GPU ~$300/mo) | ~$0 | — | Acceptable | Development / fallback |

**Key insight**: The price gap between Flash and Opus is ~13x. With per-model billing (input + output charged separately), every query is margin-positive regardless of model. Opus 4.6 serves as a premium "anchor product" — its superior quality creates desire to upgrade tiers, while Flash handles the bulk of volume cost-efficiently.

**Future marketing lever**: temporarily waive output charges on Gemini Flash queries ("Free AI answers!") to drive user acquisition. Input charges still cover vector search cost. When users experience the quality difference with Opus, they upgrade. See [MONETIZATION.md](MONETIZATION.md#future-promotional-lever).

**Previous approach**: Before Gemini, AI Mentor used **Ollama with Qwen 2.5 Coder 7B** (local, $0 API cost). The switch to Gemini improved answer quality significantly but introduced an external API dependency and per-query cost.

### 2.7 ClamAV (Antivirus)

| Component | Cost |
|-----------|:----:|
| ClamAV Docker container (self-hosted) | $0 (open-source) |
| Compute for scan worker | Included in Celery worker |
| Virus definition updates | Free (ClamAV community DB) |
| **Total** | **$0** (compute already counted) |

ClamAV is open-source and runs as a sidecar container. Scanning ~500 MB firmware takes ~10-30 seconds. No additional cost beyond compute already provisioned.

### 2.8 Stripe

| Fee Type | Rate |
|----------|:----:|
| Transaction fee | 2.9% + $0.30 per charge |
| No monthly fee | $0 |

| Scale | Monthly Revenue | Stripe Fees |
|-------|:--------------:|:-----------:|
| Small ($5K/mo) | $5,000 | $175 |
| Medium ($40K/mo) | $40,000 | $1,190 |
| Large ($110K/mo) | $110,000 | $3,220 |

### 2.9 Email (SendGrid / SES)

| Volume | Service | Monthly Cost |
|--------|---------|:------------:|
| < 100 emails/day | SendGrid Free | $0 |
| 100-1K emails/day | SendGrid Essentials | $20 |
| 1K+ emails/day | AWS SES | $1 per 10K emails |

### 2.10 Monitoring & Observability

| Option | Monthly Cost |
|--------|:------------:|
| Self-hosted (Prometheus + Grafana) | $50-100 (compute) |
| Grafana Cloud (free tier → pro) | $0-250 |
| Datadog | $200-800 |

---

## 3. Total Cost by Scale Scenario

### Scenario A: Launch (Year 1) — 100 developers, 30 vendors

| Component | Monthly Cost |
|-----------|:------------:|
| Compute (API + workers) | $400 |
| PostgreSQL | $300 |
| Redis | $30 |
| S3 storage (50 GB) | $2 |
| S3 egress | $30 |
| Gemini Embeddings | $10 |
| LLM API (Gemini Flash) | $185 |
| Stripe fees | $100 |
| Monitoring | $50 |
| Email | $0 |
| Domain + SSL | $15 |
| **Total** | **$1,122/mo** |

**Revenue (Year 1)**: ~$3,500/mo (see MARKET_RESEARCH.md)
**Gross margin**: 68%

### Scenario B: Growth (Year 2) — 300 developers, 100 vendors

| Component | Monthly Cost |
|-----------|:------------:|
| Compute (API + workers) | $900 |
| PostgreSQL (with replica) | $1,000 |
| Redis | $80 |
| S3 storage (500 GB) | $12 |
| S3 egress | $120 |
| Gemini Embeddings | $50 |
| LLM API — Gemini Flash (225K queries) | $830 |
| LLM API — Opus 4.6 (75K queries) | $2,600 |
| CDN (CloudFront) | $50 |
| Stripe fees | $1,200 |
| Monitoring | $150 |
| Email | $20 |
| Domain + SSL | $15 |
| **Total** | **$6,227/mo** |

**Revenue (Year 2)**: ~$42K/mo
**Gross margin**: 85%

### Scenario C: Scale (Year 3) — 1,000 developers, 300 vendors, 20 Platinum

| Component | Monthly Cost |
|-----------|:------------:|
| Compute (API servers ×3, workers ×4) | $2,500 |
| PostgreSQL (managed HA, pgvector + partitioning) | $2,500 |
| Redis (managed HA) | $250 |
| S3 storage (5 TB) | $115 |
| S3 egress + CDN | $600 |
| Gemini Embeddings | $300 |
| LLM API — Gemini Flash (1.5M queries) | $5,550 |
| LLM API — Opus 4.6 (500K queries) | $17,500 |
| CDN (CloudFront) | $150 |
| Stripe fees | $3,200 |
| Monitoring (Datadog) | $400 |
| Email (SES) | $30 |
| Domain + SSL + WAF | $50 |
| **Total** | **$33,145/mo** |

**Revenue (Year 3)**: ~$218K/mo + Platinum revenue ~$100K/mo (20 x $5K)
**Gross margin**: 90%

---

## 4. Cost per Operation (Unit Economics)

Chat queries are billed per model (input + output separately). See [MONETIZATION.md](MONETIZATION.md#ai-model-tiers) for user-facing prices.

| Operation | Infrastructure Cost | Price Charged | Margin |
|-----------|:-------------------:|:-------------:|:------:|
| 1 chat query — Gemini Flash | ~$0.004 | input + output per model (see MONETIZATION) | ~50-70% |
| 1 chat query — Opus 4.6 | ~$0.05 | input + output per model (see MONETIZATION) | ~50-70% |
| 1 chat query — Opus 4.6 (cached) | ~$0.04 | input + output per model (see MONETIZATION) | ~55-75% |
| 1 search query (no LLM) | ~$0.0003 | 1 billable unit | 99% |
| 1 document ingest (MD) | ~$0.002 | $0.15 (overage) | 99% |
| 1 document ingest (PDF OCR) | ~$0.02 | $0.75 (5 units x $0.15) | 97% |
| 1 document download | ~$0.001 | $0.10 (overage) | 99% |
| 1 firmware download (200 MB) | ~$0.018 (egress) | Free (included in subscription) | — |
| 1 GB storage (monthly) | $0.023 | $3/GB (Pro overage) | 99% |

**Key insight**: per-model billing ensures every query is margin-positive regardless of which LLM the user selects. Non-LLM operations maintain 94-99% margins. The business is extremely infrastructure-efficient.

---

## 5. Where the Money Goes (Top 5 Cost Drivers)

```
Year 3 breakdown ($32,695/mo):

  LLM API — Opus 4.6 .............. $17,500 (54%)  ← #1 (premium tier queries)
  LLM API — Gemini Flash .......... $5,550  (17%)  ← #2 (Free + Pro queries)
  Stripe transaction fees .......... $3,200  (10%)  ← #3 (unavoidable, scales with revenue)
  PostgreSQL managed HA ............ $2,500  (8%)   ← #4 (pgvector + HASH partitioning)
  Compute (servers + workers) ...... $2,500  (8%)   ← #5
  S3 egress + CDN .................. $750   (2%)
  Monitoring ....................... $400   (1%)
  Everything else .................. $295   (<1%)
```

**LLM is now the #1 cost driver** at scale (71% of infrastructure). This is by design — premium LLM cost is offset by premium tier revenue ($399-$1,999/mo subscriptions).

**Optimization opportunities:**
1. **Opus prompt caching**: cache system prompt across sessions → save ~25% on Opus input cost
2. **Opus batch processing**: non-realtime queries (MCP tool calls) → 50% savings
3. **Flash output promo**: temporarily waive Flash output charges to drive acquisition (see MONETIZATION.md)
4. **PostgreSQL**: move to self-managed on dedicated instances → save 40-60%
5. **S3 egress**: CDN caching for popular firmware → save 50-70%
6. **Stripe**: negotiate volume discount at $1M+ ARR → reduce from 2.9% to 2.2%

---

## 6. Break-Even Analysis

| Scenario | Monthly Cost | Revenue Needed | Customers Needed |
|----------|:------------:|:--------------:|:----------------:|
| Launch | $1,115 | $1,115 | ~12 Pro ($99) customers |
| Growth | $6,190 | $6,190 | ~16 Team ($399) customers |
| Scale | $32,695 | $32,695 | ~17 Enterprise ($1,999) or ~82 Team customers |

**Break-even is reached early** — 12 paying Pro customers cover all infrastructure costs at launch. At scale, LLM costs are higher but premium tier revenue ($399-$1,999/mo) covers them with strong margins.

---

## 7. Comparison: AI Mentor vs Typical SaaS Infrastructure

| Metric | AI Mentor | Typical B2B SaaS | Notes |
|--------|:-------:|:----------------:|-------|
| Gross margin (Year 3) | 95%+ | 70-85% | AI Mentor is extremely capital-efficient |
| Infra cost per customer | $3-10/mo | $10-50/mo | Low due to shared vector DB + S3 |
| Marginal cost per new customer | ~$0.50/mo | $5-20/mo | Adding a tenant is near-zero cost |
| Main cost driver | PostgreSQL + Compute | Compute + Storage | pgvector needs RAM for HNSW index |

---

## 8. Risk: What Could Make Costs Spike?

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Viral firmware download (one popular file, millions of downloads) | S3 egress bill spike | CDN caching + rate limiting on downloads |
| pgvector index doesn't fit in RAM | Search latency spikes, need bigger instance | HASH partitioning by tenant_id (Stage 2), increase shared_buffers |
| Gemini Embedding price increase | Embedding costs increase | Switch to local E5 model (already supported: `EMBEDDING_PROVIDER=local`) |
| Gemini API price increase or quota limits | LLM cost spike or service degradation | Fallback to Ollama (local LLM, already supported: `LLM_PROVIDER=ollama`), or switch to another OpenAI-compatible provider |
| Google AI Studio free tier rate limits (15 RPM) | Users can't get answers during peak load | Upgrade to paid tier (Vertex AI) or hybrid: Ollama for overflow |
| Opus 4.6 query volume exceeds projections | LLM cost spike if many Pro users opt into Opus | Per-model billing absorbs cost; adjust Pro Opus quota (100 queries/mo) or overage price |
| Massive OCR ingestion spike | GPU compute costs | Queue-based throttling, OCR worker autoscaling |
| DDoS on public endpoints | Compute overload | WAF + rate limiting + CloudFlare |
| ClamAV false positive quarantines good firmware | Vendor frustration | Manual review process, vendor appeal mechanism |

---

## 9. Revenue vs Infrastructure Cross-Check

Detailed validation that subscription pricing covers infrastructure at every stage.

### Year 1 — Launch (50 developers, 10 vendors)

```
REVENUE:
  40 Free  × $0      =      $0
   8 Pro   × $99     =    $792
   2 Team  × $399    =    $798
  Overage            =    $160
  Vendors (Basic)    =      $0
  ────────────────────────────
  Total revenue:       $1,750/mo

INFRASTRUCTURE:              $1,115/mo
  (incl. LLM API: $185/mo — Flash only at launch)

MARGIN:                      $635/mo (36%)
BREAK-EVEN:                  12 Pro customers
```

**Status**: Tight margins, typical for Year 1. Cash-flow positive from ~12 paying customers.
Year 1 primary risk: customer acquisition, not infrastructure cost.

### Year 2 — Growth (300 developers, 30 vendors)

```
REVENUE:
  210 Free × $0              =      $0
   60 Pro  × $99             =  $5,940
   24 Team × $399            =  $9,576
    6 Enterprise × $1,999    = $11,994
   Overage (~15%)            =  $4,127
    9 Vendor Pro × $499      =  $4,491
    3 Vendor Ent × $1,999    =  $5,997
  ────────────────────────────────────
  Total revenue:              $42,125/mo

INFRASTRUCTURE:               $6,190/mo
  (incl. LLM API: $3,430/mo — Flash $830 + Opus $2,600)

MARGIN:                      $35,935/mo (85%)
REVENUE-TO-INFRA RATIO:      6.8×
```

**Status**: Healthy SaaS economics. LLM cost is higher due to Opus premium tier, but revenue covers infrastructure 7x over. Per-model billing ensures margin protection.

### Year 3 — Scale (1,000 developers, 60 vendors)

```
REVENUE:
  600 Free × $0              =       $0
  250 Pro  × $99             =  $24,750
  100 Team × $399            =  $39,900
   50 Enterprise × $1,999    =  $99,950
  Overage (~15%)             =  $24,690
   21 Vendor Pro × $499      =  $10,479
    9 Vendor Ent × $1,999    =  $17,991
  ────────────────────────────────────────
  Total revenue:              $217,760/mo
  (+ Platinum vendors: $5K × N extra)

INFRASTRUCTURE:                $32,695/mo
  (incl. LLM API: $23,050/mo — Flash $5,550 + Opus $17,500)

MARGIN:                       $185,065/mo (85%)
REVENUE-TO-INFRA RATIO:       6.7×
```

**Status**: Strong. LLM is the dominant cost (71%), but premium tier revenue ($399-$1,999/mo) absorbs it. Per-model billing ensures every query is margin-positive.

### Summary Table

| Year | Revenue/mo | Infra/mo | LLM cost (blended) | Margin | R/I Ratio | Verdict |
|:----:|:----------:|:--------:|:------------------:|:------:|:---------:|---------|
| 1 | $1,750 | $1,115 | $185 (Flash only) | 36% | 1.6x | Break-even at ~12 Pro customers |
| 2 | $42,125 | $6,190 | $3,430 (Flash+Opus) | 85% | 6.8x | Healthy, LLM is top cost |
| 3 | $217,760 | $32,695 | $23,050 (Flash+Opus) | 85% | 6.7x | Strong, per-model billing protects margin |

**Tiered model strategy impact:**

| Year | All-Flash cost | Blended (Flash+Opus) | Opus premium cost | Covered by premium tier revenue |
|:----:|:--------------:|:--------------------:|:------------------:|:-------------------------------:|
| 1 | $185 | $185 | $0 (no Opus users yet) | — |
| 2 | $1,110 | $3,430 | +$2,320 | Team+Ent revenue: $17,571/mo |
| 3 | $7,400 | $23,050 | +$15,650 | Team+Ent revenue: $139,850/mo |

> The incremental Opus cost ($2,300-$15,600/mo) is a fraction of the premium tier revenue it generates ($17K-$140K/mo). Per-model input+output billing ensures every query is margin-positive regardless of model.

**Conclusion**: The tiered LLM model with per-model billing is validated. Gemini Flash handles bulk volume cost-efficiently (Free + Pro). Opus 4.6 serves as a premium anchor product — its superior quality drives tier upgrades while per-model pricing protects margins. Future promotional lever: temporarily waive Flash output charges to drive user acquisition. Fallback to local Ollama LLM is available if API costs become a concern.

---

## Sources

- AWS S3 pricing: https://aws.amazon.com/s3/pricing/ (March 2026)
- AWS EC2 pricing: https://aws.amazon.com/ec2/pricing/ (March 2026)
- Google AI Studio / Gemini API pricing: https://ai.google.dev/pricing (March 2026)
- Anthropic Claude pricing: https://www.anthropic.com/pricing (March 2026)
- Stripe pricing: https://stripe.com/pricing (March 2026)
- AWS CloudFront pricing: https://aws.amazon.com/cloudfront/pricing/ (March 2026)
- ClamAV: https://www.clamav.net/ (open-source, free)
