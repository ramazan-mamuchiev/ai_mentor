# IPCodex — Go-to-Market Strategy

> **Status**: v1.0 — March 18, 2026
> **Author**: Oleg Voitekhovich
> **Purpose**: Go-to-market strategy with AI-first positioning — IPCodex as an AI accelerator for device API integration
>
> Related: [PARTNERSHIP_MARKETING.md](PARTNERSHIP_MARKETING.md) · [MARKET_RESEARCH.md](MARKET_RESEARCH.md) · [MONETIZATION.md](MONETIZATION.md) · [INFRASTRUCTURE_COSTS.md](INFRASTRUCTURE_COSTS.md)

---

## 1. Positioning: AI Integration Accelerator

### 1.1 What IPCodex IS and IS NOT

```
IPCodex IS:                              IPCodex IS NOT:
─────────────────────────────────        ─────────────────────────────────
AI that understands device APIs          A documentation hosting platform
An integration accelerator               A search engine
A developer's AI co-pilot for devices    A vector database
RAG + MCP inside your IDE                Another PDF viewer
The fastest path from "new device"       A manual knowledge base
  to "working integration code"
```

### 1.2 Brand slogan

> **"Protocols speak. Codex translates."**
> *"Протоколы говорят. Codex переводит."*
>
> **"From docs to code. Instantly."**
> *"Из документации в код. Мгновенно."*

Slogan (hero) — melodic metaphor explaining what the product does. Subtitle — bold statement of scale and uniqueness. See [BRAND_SLOGANS.md](BRAND_SLOGANS.md) for competitive analysis and alternative variants.

### 1.3 Central message

**IPCodex is AI that reads device documentation so developers don't have to. Integration that took days now takes hours.**

The technology stack — RAG (Retrieval-Augmented Generation) + MCP (Model Context Protocol) + semantic search over device documentation — enables AI coding assistants like Cursor to generate accurate, working integration code by understanding the actual API specs of physical security devices.

### 1.4 Audience-specific messaging

| Audience | Pain point | IPCodex message | Proof point |
|----------|-----------|-----------------|-------------|
| **Developers** | Spend hours reading PDFs, guessing API parameters, trial-and-error | "Ask your IDE about any device API — get working code in seconds" | Find an API endpoint in 5 sec vs 30-60 min reading PDF |
| **Integration companies** | Projects delayed because developers struggle with device documentation | "Cut integration time by 60-80%. Ship projects faster, win more deals" | 10-20 hrs/month saved per developer = $500-2,000/mo value |
| **Device vendors** | Integrators avoid their devices because documentation is hard to use | "Make your devices the easiest to integrate — with AI-powered documentation" | More integrations = more device sales |

### 1.5 Competitive differentiation

IPCodex occupies a unique position: **AI-native, device-specialized, IDE-integrated**.

```
                        Device-specialized
                              │
                              │
                    IPCodex ──┤
                              │
                              │
  Generic ────────────────────┼──────────────────── AI-native
                              │
           ReadTheDocs ───────┤
           DevDocs            │        Context7
           Mintlify           │        (OSS docs only)
                              │
                              │
                        General-purpose
```

| Competitor | What they do | Why IPCodex wins |
|------------|-------------|------------------|
| **Reading PDFs manually** | Ctrl+F in 200-page PDF | AI semantic search finds answers in seconds, not minutes |
| **Copy-paste into ChatGPT** | Paste docs into LLM manually | IPCodex auto-indexes all docs, always up-to-date, no context limits |
| **Context7** | RAG over open-source library docs | IPCodex covers proprietary device docs (Axis, Hikvision, Dahua), not just OSS |
| **Algolia / Pinecone** | Generic search infrastructure | IPCodex is a complete solution, not raw infrastructure. No setup needed |
| **Vendor SDKs** | Code samples from one vendor | IPCodex covers 100+ vendors in one place, always current |
| **Cursor rules files** | Manually written .mdc rules | IPCodex auto-generates from any doc format, scales to thousands of devices |

---

## 2. The Integration Problem — Core Narrative

### 2.1 The problem (every integrator knows this)

A developer at a system integration company receives a task: integrate a Grundig SMART camera with Axxon One VMS. What happens today:

```
Day 1:
  09:00  Download Grundig camera documentation (PDF, 180 pages)
  09:30  Search for "streaming API" — Ctrl+F finds 12 matches, none relevant
  10:00  Find the right section on page 94. Read 15 pages of context
  11:30  Try first API call. HTTP 401. Authentication not clear from docs
  12:00  Search for "authentication" — find it on page 23, different section
  13:00  First successful API call. Now need Axxon One integration
  14:00  Open Axxon One SDK docs (Confluence, 500+ pages)
  15:00  Find gRPC API for camera registration. Read examples
  16:30  Write integration code. Compile error — wrong parameter types
  17:00  Back to docs. Find the correct protobuf schema on another page

Day 2:
  09:00  Continue debugging. Camera streams but no analytics metadata
  11:00  Search Grundig docs for "metadata" — find SMART line analytics API
  14:00  Integration working. Total time: ~12 hours across 2 days
```

**With IPCodex + Cursor MCP:**

```
  09:00  Open Cursor. Ask: "How to stream video from Grundig SMART camera
         and register it in Axxon One with analytics metadata?"

  09:00  IPCodex returns:
         — Grundig authentication API (from camera docs)
         — Grundig RTSP streaming endpoint (from camera docs)
         — Grundig SMART analytics metadata format (from camera docs)
         — Axxon One gRPC camera registration (from SDK docs)
         — Working Python code combining all four

  09:05  Developer reviews code, adjusts parameters
  09:30  First successful stream with analytics
  10:30  Integration complete and tested

  Total time: ~1.5 hours
```

**Result: 12 hours reduced to 1.5 hours. 8x acceleration.**

### 2.2 Why this matters at scale

| Metric | Without IPCodex | With IPCodex | Impact |
|--------|:-:|:-:|--------|
| Time to integrate one device | 8-16 hours | 1-3 hours | **5-8x faster** |
| Devices integrated per month (per developer) | 2-4 | 10-20 | **5x more throughput** |
| New developer onboarding | 1-2 weeks reading docs | Day 1 productive | **90% faster ramp-up** |
| Firmware update adaptation | Days of re-reading | Instant re-index | **Near-zero downtime** |
| Support tickets to vendor | 5-10/month | 1-2/month | **80% reduction** |
| Integration errors in production | Common (wrong API params) | Rare (AI uses actual docs) | **Higher quality** |

### 2.3 The AI technology behind it

```
Developer asks question in Cursor IDE
            │
            ▼
    ┌───────────────┐
    │  MCP Protocol  │    IDE sends query via Model Context Protocol
    └───────┬───────┘
            │
            ▼
    ┌───────────────┐
    │  IPCodex API   │    Authenticated, rate-limited, metered
    └───────┬───────┘
            │
            ▼
    ┌───────────────┐
    │  RAG Pipeline  │    Retrieval-Augmented Generation
    │                │
    │  1. Embed query│    Convert question to vector (multilingual-e5-large)
    │  2. Search     │    pgvector cosine similarity across all device docs
    │  3. Rank       │    Top-K most relevant documentation chunks
    │  4. Generate   │    LLM synthesizes answer with code
    │                │    Free/Pro: Gemini Flash | Team/Ent: Claude Opus 4.6
    └───────┬───────┘
            │
            ▼
    ┌───────────────┐
    │  Response      │    Working code + API references + source citations
    └───────────────┘

Key AI capabilities:
  — Semantic search: understands "how to stream video" even if docs say "RTSP transport"
  — Cross-document synthesis: combines info from camera docs + VMS SDK + protocol specs
  — Anti-hallucination: answers grounded in actual documentation, with source citations
  — Multi-format ingestion: PDF, Swagger/OpenAPI, Markdown, Postman, web pages
  — Auto-reindex: new firmware docs available to AI within hours
  — Tiered AI models: Gemini Flash (fast, affordable) → Opus 4.6 (premium, best quality)
  — Opus as anchor: premium AI quality drives tier upgrades (Pro → Team → Enterprise)
```

---

## 3. Go-to-Market Channels (Prioritized)

### Priority matrix

| Priority | Channel | CAC | Time to results | Why this order |
|:--------:|---------|:---:|:---------------:|----------------|
| **1** | Partnership Marketing | $0-50 | 1-3 months | Existing relationships (AxxonSoft, Grundig). Each partner = hundreds of developers |
| **2** | Content SEO | $0 (time) | 6-12 months | Free, compounds over time. Plant now, harvest later |
| **3** | Developer Relations | $500/mo | 3-6 months | Blog + tutorials when there's content to write about |
| **4** | Community | $0 | 6+ months | Only after 100+ active users. Empty community kills trust |
| **5** | Targeted Outbound | $300-800/deal | 9+ months | For Enterprise. Needs case studies and known vendor names |
| **6** | PR / Media | $0-2K | 12+ months | IPVM, SDM Magazine, Product Hunt. Needs a story to tell |
| **7** | Paid Ads | $200-500/customer | 18+ months | Last resort. Only when organic channels are proven |

### 3.1 Partnership Marketing (Priority 1)

Full strategy: [PARTNERSHIP_MARKETING.md](PARTNERSHIP_MARKETING.md)

**Core approach**: leverage vendor partner networks to reach developers at near-zero CAC.

Founding partners:
- **AxxonSoft** — VMS/PSIM platform, 10,000+ integrated devices, rich SDK (HTTP, gRPC, WebSocket)
- **Grundig Security** — Camera vendor, SMART line with edge AI analytics, AxxonSoft technology partner

**AI angle for partnerships**: position IPCodex as the AI layer that makes vendor documentation instantly accessible. Vendors get more integrations; developers get faster results.

### 3.2 Content SEO (Priority 2)

**Start immediately, in parallel with partnerships.** SEO takes 6-12 months to compound — every week of delay costs future traffic.

**Content strategy: AI-powered integration guides**

Every article follows the same structure:
1. The integration problem (what developers struggle with)
2. How AI solves it (IPCodex + MCP in action)
3. Working code example
4. Call-to-action: "Try IPCodex free"

**First 10 articles (by target search query):**

| # | Article | Target query | Monthly search volume (est.) |
|:-:|---------|-------------|:---:|
| 1 | "Axxon One HTTP API integration — Python quick start" | axxon one api python | Low, but exact audience |
| 2 | "Grundig SMART camera analytics API — developer guide" | grundig smart camera api | Low, no competition |
| 3 | "ONVIF PTZ control with Python — complete example" | onvif ptz python | 500-1K |
| 4 | "Hikvision ISAPI authentication — step by step" | hikvision isapi authentication | 1K-2K |
| 5 | "Dahua HTTP API vs Hikvision ISAPI — developer comparison" | dahua api vs hikvision | 200-500 |
| 6 | "How AI coding assistants speed up IP camera integration" | ai camera integration | Growing |
| 7 | "RTSP streaming from IP cameras — Python library guide" | rtsp python ip camera | 2K-5K |
| 8 | "Axis VAPIX API — get snapshot with Python" | axis vapix python | 500-1K |
| 9 | "Access control API integration — HID, ZKTeco, Suprema compared" | access control api integration | 200-500 |
| 10 | "MCP protocol for developers — how AI assistants use device docs" | mcp protocol developer | Growing |

**Where to publish:**
- IPCodex blog (primary — for SEO juice)
- dev.to (cross-post — for developer reach)
- Medium (cross-post — for general reach)
- LinkedIn articles (for B2B audience)

### 3.3 Developer Relations (Priority 3)

**Start month 3-4**, when AxxonSoft/Grundig content is indexed and there are real use cases to showcase.

| Format | Frequency | AI angle |
|--------|:---------:|----------|
| Technical blog post | 2/month | "How AI found the right API endpoint in 5 seconds" |
| YouTube tutorial (5-10 min) | 1/month | Screen recording: Cursor + IPCodex MCP solving real integration task |
| Twitter/LinkedIn post | 3/week | Short tips, before/after comparisons, integration speed metrics |
| Conference talk (virtual) | 1/quarter | "AI-powered device integration — from 2 days to 2 hours" |

**Key DevRel narrative**: every piece of content should demonstrate the **AI acceleration** — show the before (manual) and after (IPCodex) side by side.

### 3.4 Community (Priority 4)

**Launch at 100+ active users** (estimated month 6-8).

- Discord server: channels per vendor (Axis, Hikvision, Axxon One, etc.)
- Weekly "Integration Challenge": integrate a device using IPCodex, share results
- "Ask the AI" showcase: interesting queries and answers from IPCodex

### 3.5 Targeted Outbound (Priority 5)

**Start month 9+**, when case studies exist.

Target: CTO/VP Engineering at SDM Top 100 integration companies.

**Outbound message template:**

> Subject: Your developers spend 30% of time reading device PDFs — we can fix that with AI
>
> [Name], I noticed [Company] integrates [Vendor X] and [Vendor Y] devices.
>
> We built an AI tool that lets developers ask questions about device APIs directly in Cursor/VS Code and get working code in seconds. AxxonSoft integrators are already using it.
>
> Would a 15-minute demo be useful? I can show it working with [Vendor X] documentation specifically.

### 3.6 PR / Media (Priority 6)

**Target month 10-12**, when there's a story to tell.

| Media | Type | Pitch angle |
|-------|------|-------------|
| **IPVM** | Industry authority | "First AI assistant for security device integration — how it works" |
| **SDM Magazine** | Integrator audience | "AI reduces integration time by 80% — case study with [Partner]" |
| **Security Sales & Integration** | Installer audience | "The AI tool that helps installers integrate devices faster" |
| **Product Hunt** | Developer launch | "IPCodex — AI that reads device docs so you don't have to" |
| **Hacker News** | Developer community | "Show HN: We built RAG + MCP for IP device documentation" |

### 3.7 Paid Ads (Priority 7 — last)

**Only after month 18+**, when organic conversion is proven.

- Google Ads: target long-tail queries ("hikvision api integration help")
- LinkedIn Ads: target job titles (Integration Engineer, Embedded Developer) at SI companies
- Retargeting: show ads to blog visitors who didn't sign up

---

## 4. Messaging Framework

### 4.1 Tagline options

| Option | Style |
|--------|-------|
| **"AI that reads device docs so developers don't have to"** | Benefit-first (recommended) |
| "From PDF to working code in seconds" | Speed-focused |
| "The AI integration accelerator for physical security" | Industry-specific |
| "Ask your IDE about any device API" | Developer-focused |

### 4.2 Elevator pitch (30 seconds)

> "Developers at integration companies spend 30-60% of their time reading device documentation — PDFs, Swagger specs, SDK guides. IPCodex uses AI to index all of that documentation and make it searchable directly from Cursor or any AI coding assistant. Instead of spending 8 hours reading a 200-page PDF to integrate a camera, a developer asks a question and gets working code in seconds. AxxonSoft and Grundig integrators are already using it."

### 4.3 One-pagers by audience

**For developers:**

```
THE PROBLEM:
  You need to integrate a Grundig camera with Axxon One.
  You download 3 PDFs (480 pages total).
  You spend 2 days reading, searching, trial-and-error.

THE SOLUTION:
  Open Cursor. Ask: "How to stream Grundig SMART camera
  with analytics metadata into Axxon One?"

  IPCodex AI searches all 480 pages in milliseconds.
  Returns: authentication code + streaming endpoint +
  metadata format + Axxon One registration — all in one answer.

  Time saved: 12 hours → 1.5 hours.

TRY FREE: ipcodex.com
```

**For integration company CTO:**

```
THE PROBLEM:
  Your 10 developers each spend 30% of time reading device docs.
  That's 3 developers worth of salary spent on reading PDFs.
  Projects are delayed. New hires take 2 weeks to become productive.

THE SOLUTION:
  IPCodex AI indexes documentation for 100+ device vendors.
  Your developers ask questions in their IDE and get working code.

  RESULT:
    — Integration time: 8-16 hrs → 1-3 hrs per device (5-8x faster)
    — New developer onboarding: 2 weeks → 1 day
    — Monthly value per developer: $500-2,000 in saved time
    — IPCodex cost: $99/developer/month (ROI: 5-20x)

BOOK A DEMO: ipcodex.com/enterprise
```

**For device vendors:**

```
THE PROBLEM:
  Integrators avoid your devices because documentation is hard to navigate.
  Your support team handles 50+ "how do I use API X?" tickets per month.
  Competitors with simpler APIs win deals you should be winning.

THE SOLUTION:
  IPCodex indexes your documentation with AI.
  Developers find your API answers in seconds, not hours.
  Your devices become the easiest to integrate.

  RESULT:
    — More integrations = more device sales
    — 80% fewer support tickets about API usage
    — Analytics: see what developers search for (product feedback)
    — "Verified on IPCodex" badge = developer trust signal

BECOME A PARTNER: ipcodex.com/vendors
```

### 4.4 Key metrics for pitches

| Metric | Value | Source |
|--------|-------|--------|
| Time to find API endpoint | 5 sec (vs 30-60 min manual) | Product demo |
| Integration time reduction | 5-8x faster | AxxonSoft + Grundig scenario |
| Monthly time saved per developer | 10-20 hours | Based on 5 integrations/month |
| Monthly value saved per developer | $500-2,000 | At $50-100/hr developer rate |
| ROI at Pro tier ($99/mo) | 5-20x | Value saved / subscription cost |
| New developer onboarding | Day 1 productive (vs 1-2 weeks) | Compared to manual doc reading |
| Supported document formats | 6 (MD, PDF, Swagger, Postman, Web, OCR) | Product capability |
| AI models | Gemini 2.5 Flash (Free/Pro) + Claude Opus 4.6 (Team/Enterprise) | Tiered model strategy |
| AI billing | Per-model input+output token billing | Margin protection |
| Opus anchor effect | Premium AI quality drives tier upgrades | Growth lever |

### 4.5 AI Model as Growth Lever

**Opus 4.6 as anchor product**: Claude Opus 4.6 is not just a better model — it's a marketing tool. Its presence in the product creates a psychological anchor that drives tier upgrades.

```
Upgrade funnel powered by AI model tiers:

  FREE (Gemini Flash, 200 queries)
    |  Developer tries IPCodex, gets good answers
    |  Sees "Upgrade to Pro for 100 Premium AI queries (Opus 4.6)"
    v
  PRO ($99/mo, Flash default + 100 Opus)
    |  Uses 100 Opus queries, notices significantly better code generation
    |  Runs out of Opus quota, falls back to Flash
    |  "I want Opus all the time"
    v
  TEAM ($399/mo, Opus default, unlimited)
    |  Entire team uses Opus, productivity jumps
    |  "We need this for the whole org"
    v
  ENTERPRISE ($1,999/mo, Opus + SLA + custom)
```

**Key messaging for each transition:**

| Transition | Trigger | Message |
|------------|---------|---------|
| Free -> Pro | Hit 200 query limit | "Unlock 10,000 AI queries + 100 Premium Opus queries" |
| Pro -> Team | Used all 100 Opus queries | "Get unlimited Opus 4.6 — the best AI for code integration" |
| Team -> Enterprise | Need for org-wide deployment | "Enterprise SLA + unlimited everything + dedicated support" |

**Future promotional lever** (planned):

```
Campaign: "Free AI Answers on Gemini Flash!"

  Temporarily waive output charges on Flash queries.
  Normal: $0.004/query -> Promo: $0.002/query (input only)

  Goal: drive user acquisition. Users try Flash for free,
  see Opus quality difference, upgrade to Pro/Team.

  Can be activated/deactivated via config — no code changes needed.
```

---

## 5. 12-Month Execution Roadmap

### Month 1-3: Foundation — "Prove it works"

```
PARTNERSHIPS:
  Week 1-4:  Activate AxxonSoft — index SDK, demo, get 5-10 integrators
  Week 2-5:  Activate Grundig via AxxonSoft — index SMART line docs
  Week 4-8:  Index 20-30 top vendors (public docs: Axis, Hikvision, Dahua...)
  Week 8-12: First co-marketing content with AxxonSoft

PRODUCT:
  Week 1-2:  Landing page live (ipcodex.com)
  Week 2-4:  Self-service sign-up + free tier working
  Week 4-8:  Iterate based on AxxonSoft integrator feedback

CONTENT SEO:
  Week 2:    Publish article #1 (Axxon One API guide)
  Week 4:    Publish article #2 (Grundig SMART camera guide)
  Week 6:    Publish article #3 (ONVIF PTZ Python)
  Week 8:    Publish article #4 (Hikvision ISAPI auth)
  Week 10:   Publish article #5 (Dahua vs Hikvision comparison)

KPIs:
  — 50+ developer sign-ups
  — 2 founding partners active (AxxonSoft, Grundig)
  — 30+ vendors' docs indexed
  — 5 SEO articles published
  — Landing page live with sign-up flow
```

### Month 4-6: Validation — "Show the results"

```
PARTNERSHIPS:
  — Publish AxxonSoft + Grundig case study (three-way)
  — Pitch 10 more Tier A/B vendors using case study
  — Convert 2-3 vendors to paid Pro ($499/mo)

DEVREL:
  — Launch IPCodex blog (technical content)
  — First YouTube tutorial: "Integrate [device] in 10 min with AI"
  — Start LinkedIn posting (3x/week)

CONTENT SEO:
  — Publish articles #6-10
  — First organic traffic appearing (long-tail queries)

PRODUCT:
  — Vendor portal MVP (self-service doc upload)
  — Analytics dashboard for vendors

KPIs:
  — 200+ developer sign-ups
  — 5+ vendor partners (2-3 paid)
  — 50+ vendors' docs indexed
  — 10 SEO articles published
  — 1 case study published
  — First organic search traffic
```

### Month 7-9: Growth — "Scale what works"

```
PARTNERSHIPS:
  — 10+ paid vendor partners
  — First Strategic Partner (Enterprise/Platinum)
  — Attend ISC West or IFSEC as visitor (networking, not booth)

COMMUNITY:
  — Launch Discord server (if 100+ active users)
  — Weekly "Integration Challenge"

OUTBOUND:
  — Start targeted outreach to SDM Top 100 companies
  — Personalized demos with their actual device documentation

CONTENT:
  — 15+ SEO articles published
  — 3+ YouTube tutorials
  — Guest posts on industry blogs

KPIs:
  — 500+ developer sign-ups
  — 10+ vendor partners (5+ paid)
  — 100+ vendors' docs indexed
  — $5K+/mo vendor MRR
  — First Enterprise customer ($1,999/mo)
```

### Month 10-12: Acceleration — "Tell the world"

```
PR:
  — Product Hunt launch
  — IPVM article/review pitch
  — SDM Magazine feature pitch
  — Hacker News "Show HN" post

PARTNERSHIPS:
  — 20+ paid vendor partners
  — 3-5 Strategic Partners
  — "IPCodex Certified" program pilot

GROWTH:
  — 1,000+ developer sign-ups
  — Organic search traffic > 5,000 visits/mo
  — Community active (100+ members)
  — Evaluate paid ads (small test budget)

KPIs:
  — 1,000+ developers
  — 20+ paid vendor partners
  — $15K+/mo total MRR
  — 200+ vendors' docs indexed
  — PR coverage in 1+ industry media
```

---

## 6. Budget and KPIs

### Year 1 budget (founder-led)

| Item | Monthly | Annual | Notes |
|------|:-------:|:------:|-------|
| Landing page / hosting | $50 | $600 | Vercel/Netlify + domain |
| Content production (SEO articles) | $200 | $2,400 | Mostly founder time; some freelance editing |
| DevRel (YouTube, blog tools) | $50 | $600 | Screen recording, design tools |
| Trade show visit (1x) | — | $3,000 | ISC West or IFSEC (travel + badge) |
| Founding partner incentives | $250 | $3,000 | Waived Pro fees for 3-6 months |
| Community tools (Discord) | $0 | $0 | Free tier |
| LinkedIn Sales Navigator (month 9+) | $80 | $320 | 4 months for outbound |
| **Total** | **~$630** | **~$10,000** | |

### KPI targets

| Metric | Month 3 | Month 6 | Month 9 | Month 12 |
|--------|:-------:|:-------:|:-------:|:--------:|
| Developer sign-ups | 50 | 200 | 500 | 1,000 |
| Paying developers | 5 | 20 | 50 | 100 |
| Vendor partners (total) | 2 | 5 | 10 | 20 |
| Vendor partners (paid) | 0 | 3 | 5 | 10 |
| Developer MRR | $500 | $2K | $5K | $10K |
| Vendor MRR | $0 | $1.5K | $3K | $5K |
| Total MRR | $500 | $3.5K | $8K | $15K |
| SEO articles published | 5 | 10 | 15 | 20 |
| Organic traffic (monthly) | 100 | 1,000 | 3,000 | 5,000 |
| Case studies | 0 | 1 | 2 | 3 |
| YouTube tutorials | 0 | 1 | 3 | 5 |

---

## 7. What NOT to Do

### Positioning anti-patterns

| Do NOT say | Say instead | Why |
|------------|-------------|-----|
| "Documentation platform" | "AI integration accelerator" | Platform = commodity. AI accelerator = unique value |
| "Search engine for docs" | "AI that understands device APIs" | Search = feature. Understanding = intelligence |
| "We host your documentation" | "We make your devices the easiest to integrate" | Hosting = cost center. Easy integration = revenue driver |
| "Like Algolia but for devices" | "Like having a senior engineer who's read every device manual" | Infrastructure comparison = commodity. Human analogy = value |
| "Vector database with UI" | "AI co-pilot for device integration" | Technology = implementation detail. Co-pilot = benefit |

### Tactical anti-patterns

| Do NOT | Why | Do instead |
|--------|-----|-----------|
| Spend on paid ads before month 18 | No proven conversion funnel yet. $200-500 CAC is wasteful | Invest in content SEO and partnerships (near-zero CAC) |
| Build a perfect website before launch | Delays everything. Nobody sees it without traffic | MVP landing page in week 1-2. Iterate based on data |
| Hire a marketer before month 12 | Founder must understand what works first | Founder does marketing. Hire to scale what's proven |
| Attend trade shows with a booth | $15K+ per show, one-time impact | Attend as visitor ($3K), network, follow up digitally |
| Pitch to Enterprise before having case studies | No credibility without proof | Build proof with AxxonSoft/Grundig first, then pitch |
| Launch community before 100 users | Empty Discord = dead product signal | Wait for critical mass, then launch |
| Compete on features with Algolia/Pinecone | They are infrastructure; IPCodex is a solution | Compete on outcome: "faster integration", not "better search" |
| Discount pricing to win early customers | Trains market to expect low prices. Hard to raise later | Offer free trial (14 days), not discounts. Price = value |

---

## 8. Success Criteria

### Year 1 — validated

- [ ] 1,000+ developer sign-ups
- [ ] 100+ paying customers (developers + vendors)
- [ ] $15K+ MRR
- [ ] 3+ published case studies with measurable ROI
- [ ] AxxonSoft + Grundig partnerships active and producing referrals
- [ ] Organic search traffic > 5,000 visits/month
- [ ] Product-market fit confirmed: retention > 80% month-over-month for paying customers

### Year 2 — growing

- [ ] 5,000+ developer sign-ups
- [ ] $50K+ MRR
- [ ] 30%+ of new developers from vendor referrals
- [ ] "IPCodex Certified" recognized in the industry
- [ ] Coverage in IPVM or SDM Magazine
- [ ] First Enterprise contract ($1,999+/mo)

### Year 3 — established

- [ ] $200K+ MRR ($2.4M+ ARR)
- [ ] 500+ vendors indexed
- [ ] IPCodex = default tool for device integration in physical security
- [ ] Expansion into adjacent verticals (building automation, IoT)
