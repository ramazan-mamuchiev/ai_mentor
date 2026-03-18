# IPCodex — Infrastructure Cost Analysis

> **Status**: v1.1 — March 18, 2026 (added Gemini API LLM costs)
> **Author**: Oleg Voitekhovich
> **Purpose**: Detailed infrastructure cost breakdown by component, scenario-based projections, and cost-to-revenue analysis to validate pricing model

---

## 1. Cost Components Overview

```
                     IPCodex Infrastructure Cost Stack

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
 │  OpenAI API     │  Gemini API │  Stripe     │  SendGrid    │
 │  (embeddings)   │  (LLM)     │  (billing)  │  (email)     │
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

**Key cost driver**: pgvector index size. Each chunk = 1536 dims × 4 bytes = 6 KB for the vector alone. 1M chunks ≈ 6 GB just for vectors + overhead.

| Chunks in DB | Vector Storage | Total DB Size (est.) |
|:------------:|:--------------:|:--------------------:|
| 100K | 600 MB | ~2 GB |
| 500K | 3 GB | ~10 GB |
| 1M | 6 GB | ~20 GB |
| 5M | 30 GB | ~80 GB |

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

### 2.5 OpenAI Embedding API

Pricing: **$0.02 per 1M tokens** (text-embedding-3-small, as of March 2026)

| Operation | Avg Tokens | Cost per Call | Monthly Volume | Monthly Cost |
|-----------|:----------:|:-------------:|:--------------:|:------------:|
| Search query embedding | 50 tokens | $0.000001 | 100,000 queries | **$0.10** |
| Document ingestion (chunk) | 500 tokens | $0.00001 | 50,000 chunks | **$0.50** |
| Full doc ingestion (200 chunks) | 100K tokens | $0.002 | 500 documents | **$1.00** |

| Scale | Queries/mo | Ingests/mo | Monthly API Cost |
|-------|:----------:|:----------:|:----------------:|
| Small | 50K | 200 docs | **$1-3** |
| Medium | 300K | 1,000 docs | **$5-15** |
| Large | 2M | 5,000 docs | **$30-80** |

**Key insight**: OpenAI Embedding API is extremely cheap. Even at large scale, it's < $100/mo. This is NOT a cost concern.

**Alternative**: self-hosted `all-MiniLM-L6-v2` eliminates API cost entirely (GPU instance ~$100-200/mo, but also handles other tasks).

### 2.6 Gemini API (LLM for RAG Answers)

Every user chat query triggers an LLM call to generate the answer from retrieved documentation chunks. Since March 2026, IPCodex uses **Google Gemini 2.5 Flash** via the OpenAI-compatible API (Google AI Studio).

**Pricing** (Google AI Studio, as of March 2026):

| Parameter | Value |
|-----------|:-----:|
| Input tokens | **$0.15 per 1M tokens** |
| Output tokens | **$0.60 per 1M tokens** |
| Free tier | 15 RPM, limited daily quota |

**Per-query cost estimate:**

| Component | Tokens | Cost |
|-----------|:------:|:----:|
| System prompt + RAG context (8 chunks) | ~3,000–5,000 input | $0.00045–$0.00075 |
| Chat history (up to 10 messages) | ~1,000–2,000 input | $0.00015–$0.00030 |
| Generated answer | ~500–1,500 output | $0.00030–$0.00090 |
| **Total per query** | | **$0.0009–$0.002** |

**Monthly cost by scale:**

| Scale | Queries/mo | Input Tokens | Output Tokens | Monthly Cost |
|-------|:----------:|:------------:|:------------:|:------------:|
| Small (100 users) | 50K | 200M | 50M | **$60** |
| Medium (500 users) | 300K | 1.2B | 300M | **$360** |
| Large (2,000 users) | 2M | 8B | 2B | **$2,400** |

**Key insight**: Gemini Flash is significantly cheaper than GPT-4o (~10×) but still becomes a meaningful cost at scale. At Large scale, LLM API is a top-5 cost driver.

**Alternatives & fallbacks:**
- **Ollama (local)**: $0 API cost, already supported in codebase (`LLM_PROVIDER=ollama`). Requires GPU instance (~$200-400/mo) but handles unlimited queries
- **Claude Sonnet**: higher quality answers, ~$3/$15 per 1M tokens (5-10× more expensive than Gemini Flash)
- **Gemini Pro**: better quality than Flash, ~2× the cost

**Previous approach**: Before Gemini, IPCodex used **Ollama with Qwen 2.5 Coder 7B** (local, $0 API cost). The switch to Gemini improved answer quality significantly but introduced an external API dependency and per-query cost.

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
| OpenAI Embeddings | $3 |
| Gemini API (LLM) | $60 |
| Stripe fees | $100 |
| Monitoring | $50 |
| Email | $0 |
| Domain + SSL | $15 |
| **Total** | **$990/mo** |

**Revenue (Year 1)**: ~$3,500/mo (see MARKET_RESEARCH.md)
**Gross margin**: 72%

### Scenario B: Growth (Year 2) — 300 developers, 100 vendors

| Component | Monthly Cost |
|-----------|:------------:|
| Compute (API + workers) | $900 |
| PostgreSQL (with replica) | $1,000 |
| Redis | $80 |
| S3 storage (500 GB) | $12 |
| S3 egress | $120 |
| OpenAI Embeddings | $10 |
| Gemini API (LLM) | $360 |
| CDN (CloudFront) | $50 |
| Stripe fees | $1,200 |
| Monitoring | $150 |
| Email | $20 |
| Domain + SSL | $15 |
| **Total** | **$3,920/mo** |

**Revenue (Year 2)**: ~$40K/mo
**Gross margin**: 90%

### Scenario C: Scale (Year 3) — 1,000 developers, 300 vendors, 20 Platinum

| Component | Monthly Cost |
|-----------|:------------:|
| Compute (API servers ×3, workers ×4) | $2,500 |
| PostgreSQL (managed HA, pgvector + partitioning) | $2,500 |
| Redis (managed HA) | $250 |
| S3 storage (5 TB) | $115 |
| S3 egress + CDN | $600 |
| OpenAI Embeddings (or self-hosted) | $60 |
| Gemini API (LLM) | $2,400 |
| CDN (CloudFront) | $150 |
| Stripe fees | $3,200 |
| Monitoring (Datadog) | $400 |
| Email (SES) | $30 |
| Domain + SSL + WAF | $50 |
| **Total** | **$12,255/mo** |

**Revenue (Year 3)**: ~$110K/mo (conservative) + Platinum revenue ~$100K/mo (20 × $5K)
**Gross margin**: 94%

---

## 4. Cost per Operation (Unit Economics)

| Operation | Infrastructure Cost | Price Charged | Margin |
|-----------|:-------------------:|:-------------:|:------:|
| 1 chat query (search + LLM) | ~$0.0015 | $0.005 (overage) | 70% |
| 1 document ingest (MD) | ~$0.002 | $0.15 (overage) | 99% |
| 1 document ingest (PDF OCR) | ~$0.02 | $0.75 (5 units × $0.15) | 97% |
| 1 document download | ~$0.001 | $0.10 (overage) | 99% |
| 1 firmware download (200 MB) | ~$0.018 (egress) | Free (included in subscription) | — |
| 1 GB storage (monthly) | $0.023 | $3/GB (Pro overage) | 99% |

**Key insight**: per-unit margins are 94-99%. The business is extremely infrastructure-efficient. Main cost is people (development, support, sales), not servers.

---

## 5. Where the Money Goes (Top 5 Cost Drivers)

```
Year 3 breakdown ($12,255/mo):

  Stripe transaction fees .......... $3,200  (26%)  ← #1 (unavoidable, scales with revenue)
  PostgreSQL managed HA ............ $2,500  (20%)  ← #2 (pgvector + HASH partitioning)
  Compute (servers + workers) ...... $2,500  (20%)  ← #3
  Gemini API (LLM) ................. $2,400  (20%)  ← #4 (scales with query volume)
  S3 egress + CDN .................. $750   (6%)   ← #5 (firmware downloads)
  Monitoring ....................... $400   (3%)
  Everything else .................. $505   (4%)
```

**Optimization opportunities:**
1. **Gemini API**: switch to Ollama (local LLM) for $0 API cost — already supported in codebase, requires GPU instance (~$200-400/mo for unlimited queries vs $2,400/mo at scale)
2. **PostgreSQL**: move to self-managed on dedicated instances → save 40-60%
3. **S3 egress**: CDN caching for popular firmware → save 50-70%
4. **Compute**: spot/preemptible instances for Celery workers → save 30-50%
5. **Stripe**: negotiate volume discount at $1M+ ARR → reduce from 2.9% to 2.2%

---

## 6. Break-Even Analysis

| Scenario | Monthly Cost | Revenue Needed | Customers Needed |
|----------|:------------:|:--------------:|:----------------:|
| Launch | $990 | $990 | ~10 Pro ($99) customers |
| Growth | $3,920 | $3,920 | ~40 Pro or ~10 Team customers |
| Scale | $12,255 | $12,255 | ~124 Pro or ~31 Team customers |

**Break-even is reached very early** — even 10 paying Pro customers cover all infrastructure costs at launch. The pricing model has comfortable margins at every scale.

---

## 7. Comparison: IPCodex vs Typical SaaS Infrastructure

| Metric | IPCodex | Typical B2B SaaS | Notes |
|--------|:-------:|:----------------:|-------|
| Gross margin (Year 3) | 95%+ | 70-85% | IPCodex is extremely capital-efficient |
| Infra cost per customer | $3-10/mo | $10-50/mo | Low due to shared vector DB + S3 |
| Marginal cost per new customer | ~$0.50/mo | $5-20/mo | Adding a tenant is near-zero cost |
| Main cost driver | PostgreSQL + Compute | Compute + Storage | pgvector needs RAM for HNSW index |

---

## 8. Risk: What Could Make Costs Spike?

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Viral firmware download (one popular file, millions of downloads) | S3 egress bill spike | CDN caching + rate limiting on downloads |
| pgvector index doesn't fit in RAM | Search latency spikes, need bigger instance | HASH partitioning by tenant_id (Stage 2), increase shared_buffers |
| OpenAI price increase | Embedding costs increase | Switch to self-hosted model (already supported) |
| Gemini API price increase or quota limits | LLM cost spike or service degradation | Fallback to Ollama (local LLM, already supported: `LLM_PROVIDER=ollama`), or switch to another OpenAI-compatible provider |
| Google AI Studio free tier rate limits (15 RPM) | Users can't get answers during peak load | Upgrade to paid tier (Vertex AI) or hybrid: Ollama for overflow |
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

INFRASTRUCTURE:              $990/mo
  (incl. Gemini API: $60/mo)

MARGIN:                      $760/mo (43%)
BREAK-EVEN:                  10 Pro customers ($990 = $990)
```

**Status**: Tight margins, typical for Year 1. Cash-flow positive from ~10 paying customers.
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

INFRASTRUCTURE:               $3,920/mo
  (incl. Gemini API: $360/mo)

MARGIN:                      $38,205/mo (90%)
REVENUE-TO-INFRA RATIO:      10.7×
```

**Status**: Healthy SaaS economics. Revenue covers infrastructure 12x over.

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

INFRASTRUCTURE:                $12,255/mo
  (incl. Gemini API: $2,400/mo)

MARGIN:                       $205,505/mo (94%)
REVENUE-TO-INFRA RATIO:       17.8×
```

**Status**: Outstanding. Infrastructure is < 5% of revenue.

### Summary Table

| Year | Revenue/mo | Infra/mo | Gemini API | Margin | R/I Ratio | Verdict |
|:----:|:----------:|:--------:|:----------:|:------:|:---------:|---------|
| 1 | $1,750 | $990 | $60 | 43% | 1.8× | Break-even at ~10 Pro customers |
| 2 | $42,125 | $3,920 | $360 | 90% | 10.7× | Healthy, reinvest in growth |
| 3 | $217,760 | $12,255 | $2,400 | 94% | 17.8× | Excellent SaaS economics |

**Conclusion**: Current pricing model is validated. The addition of Gemini API (LLM) increases infrastructure costs by $60-$2,400/mo depending on scale, but margins remain strong (90%+ from Year 2). Fallback to local Ollama LLM is available if API costs become a concern. The main expense will be people (engineers, support, sales), not servers.

---

## Sources

- AWS S3 pricing: https://aws.amazon.com/s3/pricing/ (March 2026)
- AWS EC2 pricing: https://aws.amazon.com/ec2/pricing/ (March 2026)
- OpenAI Embeddings pricing: https://openai.com/pricing (March 2026)
- Google AI Studio / Gemini API pricing: https://ai.google.dev/pricing (March 2026)
- Stripe pricing: https://stripe.com/pricing (March 2026)
- AWS CloudFront pricing: https://aws.amazon.com/cloudfront/pricing/ (March 2026)
- ClamAV: https://www.clamav.net/ (open-source, free)
