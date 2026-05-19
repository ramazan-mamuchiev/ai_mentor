# AI Mentor — Backlog

> Tasks planned for future implementation. Each item includes problem statement, proposed solution, and complexity estimate.
>
> Items 1–9 are the original backlog. Items 10–32 were added from a platform maturity audit (March 31, 2026).

---

## 1. Email Verification Flow

| | |
|---|---|
| **Priority** | High |
| **Status** | Not started |
| **Complexity** | Medium (~4-6 hours) |
| **Dependencies** | Resend API key configured on VPS |

### Problem

When a user registers via email/password, `email_verified` is set to `false` but no verification email is sent. Anyone can register with someone else's email. The function `send_email_verification()` exists in `backend/app/email/service.py` but is never called. There is no backend endpoint to handle the verification link, and no frontend page to display the result.

### What already exists

- `Tenant.email_verified` field in the database (default `false`)
- `send_email_verification(to, token)` in `backend/app/email/service.py` — sends email via Resend with a verification link
- `send_welcome_email(to, slug)` — welcome email template
- Resend SDK installed (`resend` in `requirements.txt`)
- Config fields: `resend_api_key`, `email_from`, `app_base_url` in `backend/app/config.py`

### Implementation plan

**Backend:**

1. **Generate verification token** — create a JWT with `sub=tenant_id`, `purpose=email_verify`, `exp=24h` in `backend/app/auth/service.py`
2. **Send verification email on registration** — call `send_email_verification(email, token)` in `backend/app/auth/router.py` after `register_tenant()` returns
3. **New endpoint `GET /api/v1/verify-email?token=...`** in `backend/app/auth/router.py`:
   - Decode JWT, validate `purpose=email_verify`
   - Find tenant by `sub`, set `email_verified=True`
   - Redirect to frontend `/app` with success flash or return JSON
4. **Optional: resend verification** — `POST /api/v1/resend-verification` for users who didn't receive the email
5. **Configure Resend API key** on VPS (add `RESEND_API_KEY` to `.env`)

**Frontend:**

1. **Page `/verify-email`** — reads `?token=` from URL, calls backend endpoint, shows success/error/expired message
2. **Add route** in React Router for `/verify-email` → `VerifyEmailPage` component
3. **Banner for unverified users** — show a dismissible notice in the app layout when `user.email_verified === false`: "Please verify your email. Check your inbox or resend."
4. **Resend link** in the banner that calls `POST /api/v1/resend-verification`

### Notes

- OAuth users (Google, GitHub) already have `email_verified=true` set in `find_or_create_oauth_tenant()`
- Do NOT block unverified users from using the app initially — soft reminder only
- Consider rate-limiting the resend endpoint (max 3 per hour)

---

## 2. Landing Page: Interactive Demo / Video

| | |
|---|---|
| **Priority** | Medium |
| **Status** | Not started |
| **Complexity** | High (~8-12 hours) |
| **Dependencies** | Decision: screencast vs public sandbox |

### Problem

The landing page hero section has a static CSS mockup of the chat interface. Best-in-class SaaS landings (Cursor, Vercel, Mintlify) show live demos, interactive playgrounds, or embedded video walkthroughs. A static mockup shows what the product looks like, but doesn't convey the experience.

### Options

**Option A: Embedded screencast (quick win)**
- Record a 30-60s GIF/WebM of a real chat session (question → streaming response → code block → sources)
- Embed as `<video autoplay muted loop>` inside the hero mockup frame
- Pros: fast to implement, realistic; Cons: not interactive, gets stale

**Option B: Public sandbox / guest mode**
- Allow unauthenticated users to try the chat with a limited set of pre-indexed docs (e.g. 1-2 products)
- CTA button changes from "Get Started" → "Try it now" and leads to `/demo` with a guest session
- Requires: guest tenant, rate limiting, read-only mode, session TTL
- Pros: highest conversion impact; Cons: complex, security considerations

**Option C: Typed animation in mockup**
- Animate the mockup: typing effect for the question, streaming text for the answer, code block fading in
- Pure CSS/JS, no backend changes
- Pros: medium effort, engaging; Cons: still not real interaction

### Recommendation

Start with **Option C** (animated mockup) as a quick improvement, then invest in **Option B** (public sandbox) as a larger feature.

---

## 3. Landing Page: CTA Leads to Login, Not Demo

| | |
|---|---|
| **Priority** | Medium |
| **Status** | Not started |
| **Complexity** | Medium (~4-6 hours) |
| **Dependencies** | Item 2 (demo/sandbox decision) |

### Problem

The "Get Started" / "Начать" button leads to `/app`, which requires authentication. This is a high barrier for a first-time visitor who hasn't yet decided to commit. Best practice: offer a frictionless first experience — a live demo, a video, or at least a product tour — before asking for signup.

### Implementation plan

- If public sandbox (Item 2, Option B) is implemented, change primary CTA to link to `/demo`
- If not, add a secondary CTA "Watch demo" linking to an embedded video or a scroll-to-mockup anchor
- Keep "Get Started" as a secondary button for users ready to sign up

---

## 5. Landing Page: Technical/Business View Toggle for "How It Works"

| | |
|---|---|
| **Priority** | Low |
| **Status** | Not started |
| **Complexity** | Medium (~3-4 hours) |
| **Dependencies** | Localization keys for business descriptions |

### Problem

The "How It Works" section shows code blocks at every step — great for developers, but may alienate managers, CTOs, or business stakeholders. Competitive landing pages often offer dual perspectives.

### Implementation plan

1. Add a toggle switch at the top of the section: "Developer" / "Business" (default: Developer)
2. In "Business" mode, replace code blocks with benefit-oriented bullet points (e.g. "Documents are automatically parsed and indexed — no manual tagging needed")
3. Store preference in localStorage
4. Add localization keys for business-mode descriptions

---

## 6. RAG Evaluation: Golden Set (Etalon Q&A)

| | |
|---|---|
| **Priority** | Medium |
| **Status** | Not started |
| **Complexity** | High (~8-12 hours) |
| **Dependencies** | RAG Evaluation page (Phase 1+2) must be implemented first |

### Problem

LLM-as-judge metrics (Context Precision, Faithfulness) are industry-standard but inherently imperfect: an LLM evaluates another LLM, introducing bias and lacking ground truth. For maximum client confidence, the system needs a curated set of reference question-answer pairs with known correct source documents. This enables true Recall@K, Precision@K, and NDCG — metrics that are objective and reproducible.

### Implementation plan

**Backend:**

1. New model `GoldenSetItem` — table `golden_set_items` with fields: `id`, `question`, `expected_answer`, `expected_chunk_ids` (array), `expected_document_ids` (array), `product_id`, `tags`, `created_at`, `updated_at`
2. CRUD endpoints under `/api/v1/admin/golden-set` — create, list, update, delete items
3. Import/export as CSV/JSON for batch management
4. Extend `run_rag_evaluation` Celery task: when golden set items exist, run retrieval against each item and compute true Recall@K, Precision@K, NDCG by comparing retrieved chunks with `expected_chunk_ids`

**Frontend:**

1. New sub-tab "Golden Set" in the RAG Evaluation page — table of Q&A pairs with inline editing
2. "Import from CSV" and "Export" buttons
3. Display golden set metrics alongside LLM-as-judge metrics in eval results, clearly labeled as "Ground Truth Metrics"

### Notes

- Start with 30-50 manually curated pairs covering main products and edge cases
- Golden set items should be versioned or timestamped — when documents are re-indexed, `expected_chunk_ids` may shift
- Consider auto-suggesting golden set candidates from high-confidence chat sessions (thumbs-up + high similarity)

---

## 7. RAG Evaluation: A/B Config Comparison

| | |
|---|---|
| **Priority** | Low |
| **Status** | Not started |
| **Complexity** | High (~10-14 hours) |
| **Dependencies** | RAG Evaluation page + Golden Set or fixed query snapshots |

### Problem

When tuning RAG parameters (ef_search, reranker threshold, embedding model, hybrid weights), ML engineers need to compare results of two configurations on the **same set of queries**. Currently each eval run samples random queries, making apples-to-apples comparison impossible.

### Implementation plan

1. **Query snapshots** — ability to save a set of N queries from a previous eval run as a named snapshot
2. **"Compare" mode** — run evaluation on a fixed snapshot with current config, then compare side-by-side with a previous run on the same snapshot
3. **Diff view** — per-query comparison: which queries improved, which degraded, which chunks changed
4. **Config capture** — each eval run records the active RAG config (ef_search, rerank_enabled, hybrid weights, embedding model) for reproducibility

---

## 8. RAG Evaluation: Regression Alerts

| | |
|---|---|
| **Priority** | Medium |
| **Status** | Not started |
| **Complexity** | Medium (~4-6 hours) |
| **Dependencies** | RAG Evaluation page (Phase 1+2) |

### Problem

Without automatic alerts, quality degradation goes unnoticed until a client complains. ML engineers must manually compare numbers between eval runs.

### Implementation plan

1. **Threshold config** — admin sets warning/critical thresholds for key metrics (e.g. faithfulness < 0.85 = warning, < 0.70 = critical)
2. **Auto-compare** — after each eval run completes, compare with previous run; flag metrics that dropped beyond threshold
3. **Visual indicators** — in the eval runs table, mark runs with regression as "Warning" badge; in detail view, highlight degraded metrics in red
4. **Optional: email/webhook notification** — send alert to admin when regression detected (reuse existing Resend email infrastructure)

---

## 9. RAG Evaluation: Retrieval-Only Mode

| | |
|---|---|
| **Priority** | Low |
| **Status** | Not started |
| **Complexity** | Medium (~6-8 hours) |
| **Dependencies** | RAG Evaluation page + Golden Set |

### Problem

Current eval evaluates retrieval + generation together. ML engineers need to isolate retrieval quality: "Are we finding the right chunks?" without the noise of LLM generation quality. This is cheaper, faster, and more precise for tuning search parameters.

### Implementation plan

1. **New eval mode** — "Retrieval Only" option when launching eval run
2. **Re-run retrieval** — for each sample query, call `search_documents()` directly (not the full RAG pipeline) and compare results with golden set expected chunks
3. **Pure retrieval metrics** — Recall@K, Precision@K, NDCG, MRR based on ground truth, not LLM-as-judge
4. **Speed** — no LLM calls needed, runs in seconds even for 100+ samples

---

# Platform Maturity Audit — March 31, 2026

> The following items (10–32) were identified during a comprehensive platform maturity analysis. They cover gaps in backend robustness, RAG pipeline quality, frontend reliability, DevOps, and business features required for a production-grade SaaS RAG platform.

## Priority Legend

| Tag | Meaning |
|-----|---------|
| **P0** | Blocking production-readiness — must fix before scaling |
| **P1** | Important for reliability and user trust |
| **P2** | Valuable for operational maturity and enterprise readiness |
| **P3** | Nice-to-have, long-term competitive advantage |

---

## 10. API Rate Limiting

| | |
|---|---|
| **Priority** | P0 — Critical |
| **Status** | Not started |
| **Complexity** | Medium (~6-8 hours) |
| **Dependencies** | Redis (already available) |
| **Area** | Backend |

### Problem

No rate limiting exists on any API endpoint. Any authenticated user (or leaked API key) can send unlimited requests, exhausting LLM quotas, database connections, and Celery workers. For a SaaS with tiered plans, rate limiting is non-negotiable.

### What already exists

- Redis is available as Celery broker — can be reused for rate limit counters
- `uploads/quota.py` has a comment mentioning "Rate limiting per user" as a future extension
- Per-tier permission limits exist in `auth/permissions.py` (`get_limit`) but are not enforced as rate limits

### Implementation plan

1. **Add `slowapi` or custom Redis-based middleware** — sliding window counters per `(tenant_id, endpoint_group)`
2. **Define rate limit tiers** in the role/permissions system: e.g. Free = 20 chat/min, Pro = 100 chat/min
3. **Per-endpoint groups**: `/chat/messages` (expensive — LLM calls), `/search` (moderate), `/uploads` (heavy I/O), `/documents/ingest` (Celery queue)
4. **Return `429 Too Many Requests`** with `Retry-After` header
5. **Admin dashboard**: show rate limit hits per tenant in analytics

---

## 12. Sentry Integration

| | |
|---|---|
| **Priority** | P0 — Critical |
| **Status** | Not started |
| **Complexity** | Low (~1-2 hours) |
| **Dependencies** | Sentry DSN (already in config) |
| **Area** | Backend |

### Problem

`sentry-sdk[fastapi]` is in `requirements.txt` and `sentry_dsn` field exists in `config.py`, but `sentry_sdk.init()` is never called. Errors in production are invisible unless someone checks Loki logs manually.

### Implementation plan

1. **Call `sentry_sdk.init()`** in `main.py` lifespan with `dsn=settings.sentry_dsn`, `traces_sample_rate`, `environment=settings.app_env`
2. **Set `send_default_pii=False`** for GDPR
3. **Tag requests** with `tenant_id`, `request_id` via Sentry scope
4. **Celery integration** — `sentry_sdk.integrations.celery.CeleryIntegration()` to capture worker errors
5. **Skip init when DSN is empty** (dev environment)

---

## 13. CORS Middleware

| | |
|---|---|
| **Priority** | P1 — Important |
| **Status** | Not started |
| **Complexity** | Low (~1 hour) |
| **Dependencies** | None |
| **Area** | Backend |

### Problem

No `CORSMiddleware` is configured in FastAPI. Currently works because nginx proxies everything through one origin. However, third-party API consumers (Cursor IDE, external integrations using API keys) will face CORS errors when calling the API directly from browser contexts.

### Implementation plan

1. **Add `CORSMiddleware`** to `main.py` with configurable `allowed_origins` from `.env`
2. **Production**: allow `https://ai-mentor.ru`, `https://www.ai-mentor.ru`
3. **Development**: allow `http://localhost:*`
4. **API key requests**: consider allowing `*` origin for `/mcp` and API-key-authenticated endpoints (no cookies involved)

---

## 14. CI/CD Pipeline

| | |
|---|---|
| **Priority** | P0 — Critical |
| **Status** | Not started |
| **Complexity** | High (~8-12 hours) |
| **Dependencies** | GitHub Actions or equivalent |
| **Area** | DevOps |

### Problem

No CI/CD pipeline exists. Deploy is manual via SSH. No automated testing on PR, no lint checks, no build verification. This is the single biggest gap for team scalability and code quality.

### Implementation plan

1. **GitHub Actions workflow** (`.github/workflows/ci.yml`):
   - On PR to `main`: run `ruff check` + `ruff format --check`, `pytest` (unit + integration via testcontainers), `mypy` (optional, incremental adoption)
   - Frontend: `npm ci`, `npm run build`, `npx tsc --noEmit`, `npm test`
2. **CD workflow** (`.github/workflows/deploy.yml`):
   - On push to `main`: SSH to VPS, enable maintenance mode, pull, build, restart, health check, disable maintenance
   - Reuse existing deploy steps from `.cursor/rules/deploy-vps.mdc`
3. **Docker image caching** — use GitHub Actions cache for Docker layers
4. **Status badges** in README

---

## 15. Test Coverage Measurement

| | |
|---|---|
| **Priority** | P1 — Important |
| **Status** | Not started |
| **Complexity** | Low (~2 hours) |
| **Dependencies** | None |
| **Area** | Testing |

### Problem

57 test files exist but `pytest-cov` is not installed and coverage is never measured. It is impossible to know which modules have zero test coverage, making it easy to introduce regressions in untested code.

### Implementation plan

1. **Add `pytest-cov`** to `requirements-dev.txt`
2. **Configure in `pyproject.toml`**: `--cov=app --cov-report=term-missing --cov-report=html`
3. **Set a baseline threshold** (e.g. `--cov-fail-under=50`) and raise it over time
4. **CI integration** — publish coverage report as PR comment or artifact
5. **Identify gaps** — prioritize writing tests for uncovered critical paths (auth, billing, ingestion)

---

## 16. Guardrails / Safety Layer

| | |
|---|---|
| **Priority** | P1 — Important |
| **Status** | Not started |
| **Complexity** | High (~10-14 hours) |
| **Dependencies** | None |
| **Area** | RAG Pipeline |

### Problem

No protection against prompt injection, jailbreak attempts, or toxic content. For a B2B SaaS where users enter arbitrary queries, a safety layer is essential to prevent misuse and protect reputation.

### What to implement

1. **Input filter** — lightweight classifier (Gemini Flash or regex heuristics) to detect prompt injection attempts before they reach the RAG pipeline
2. **Output filter** — post-generation check for PII leakage, hallucinated URLs, or off-topic content
3. **Blocklist** — configurable list of forbidden topics/patterns per tenant
4. **Logging** — log all blocked queries with reason for audit
5. **Graceful response** — return a polite refusal message instead of silently failing

### Notes

- Start with heuristic rules (known injection patterns) and upgrade to a dedicated classifier later
- Gemini models have built-in safety filters; configure `safety_settings` in the API call as a first line of defense
- Consider open-source tools like `rebuff` or `LLM Guard` for battle-tested patterns

---

## 17. Document Versioning and Change Tracking

| | |
|---|---|
| **Priority** | P2 — Valuable |
| **Status** | Not started |
| **Complexity** | High (~12-16 hours) |
| **Dependencies** | None |
| **Area** | RAG Pipeline |

### Problem

Documents can be re-ingested (`reingest`), but there is no version history, no diff between versions, no tracking of what changed, and no notification when a source document is updated by the vendor. Stale chunks from a previous version may coexist with new ones during reindex.

### Implementation plan

1. **`document_versions` table** — `id`, `document_id`, `version`, `ingested_at`, `chunk_count`, `checksum`, `metadata_snapshot`
2. **On reingest** — create a new version record, soft-delete old chunks, ingest new ones; keep the last N versions
3. **Diff endpoint** — `GET /api/v1/documents/{id}/diff?v1=3&v2=4` returns added/removed/changed sections
4. **Change detection for URLs** — periodic Celery task that checks `Last-Modified` / `ETag` for URL-sourced documents and flags those that changed
5. **Admin notification** — show "N documents have newer versions available" in the admin dashboard

---

## 18. Feedback Loop for Continuous Improvement

| | |
|---|---|
| **Priority** | P2 — Valuable |
| **Status** | Not started |
| **Complexity** | Medium (~6-8 hours) |
| **Dependencies** | Feedback already stored in `ChatMessage.feedback` |
| **Area** | RAG Pipeline |

### Problem

Thumbs up/down feedback is collected and stored but never used to improve retrieval or generation quality. There is no analytics view for "problem queries" and no mechanism to surface documentation gaps.

### Implementation plan

1. **Feedback analytics dashboard** — show queries with negative feedback grouped by topic, product, query type
2. **"Unanswerable queries" report** — queries where retrieval returned zero chunks or similarity below threshold; group by topic to identify documentation gaps
3. **Golden set auto-suggestions** — queries with positive feedback + high similarity → suggest as golden set candidates (see Item 6)
4. **Admin recommendations** — "Add documentation about X — 15 unanswered queries this week"
5. **Future: embedding fine-tuning** — use feedback pairs to fine-tune embedding model or adjust boost weights

---

## 19. React Error Boundary

| | |
|---|---|
| **Priority** | P0 — Critical |
| **Status** | Not started |
| **Complexity** | Low (~2 hours) |
| **Dependencies** | None |
| **Area** | Frontend |

### Problem

No React Error Boundary exists in the frontend. A crash in any component (e.g. a malformed API response causing a render error) takes down the entire application with a white screen. Users lose their session context.

### Implementation plan

1. **Install `react-error-boundary`** (or write a simple class component)
2. **Wrap `<App />` in `<ErrorBoundary>`** with a fallback UI: "Something went wrong. Reload the page."
3. **Add granular boundaries** around high-risk areas: `ChatWindow`, `DocumentsPage`, `AdminApp`
4. **Report errors to Sentry** from the boundary's `onError` callback
5. **"Try again" button** that resets the boundary state

---

## 20. Global Toast / Notification System

| | |
|---|---|
| **Priority** | P1 — Important |
| **Status** | Not started |
| **Complexity** | Low (~3-4 hours) |
| **Dependencies** | None |
| **Area** | Frontend |

### Problem

No global notification system exists. API errors are often silently caught (`catch { /* ignore */ }`). Users get no feedback when operations succeed or fail. The only "toast" is a hardcoded CSS element in `ChatInput.tsx`.

### Implementation plan

1. **Install `sonner` or `react-hot-toast`** — lightweight, accessible toast library
2. **Create a `notify` utility** wrapping the toast API: `notify.success(msg)`, `notify.error(msg)`, `notify.info(msg)`
3. **Integrate with `apiFetch`** in `api/client.ts` — show error toast on non-2xx responses (unless explicitly suppressed)
4. **Add success toasts** for key actions: document uploaded, product created, settings saved, API key created/revoked
5. **i18n support** — toast messages should use `t()` for localization

---

## 21. Data Fetching Layer (React Query / SWR)

| | |
|---|---|
| **Priority** | P1 — Important |
| **Status** | Not started |
| **Complexity** | High (~12-16 hours, incremental migration) |
| **Dependencies** | None |
| **Area** | Frontend |

### Problem

Every page manually manages `fetch` + `useState` + `useEffect` + loading/error states. There is no client-side caching, no automatic refetch, no optimistic updates. Navigating between pages causes full data reload every time.

### Implementation plan

1. **Install `@tanstack/react-query`** and add `QueryClientProvider` in `main.tsx`
2. **Migrate incrementally** — start with read-heavy pages: `DocumentsPage`, `ProductsPage`, `AnalyticsPage`
3. **Key benefits**: automatic caching, background refetch, deduplication, retry, optimistic mutations
4. **Custom hooks**: `useDocuments()`, `useProducts()`, `useChatSessions()` wrapping `useQuery` / `useMutation`
5. **Devtools** — add `ReactQueryDevtools` in development for debugging

---

## 22. E2E Tests (Playwright)

| | |
|---|---|
| **Priority** | P2 — Valuable |
| **Status** | Not started |
| **Complexity** | High (~10-14 hours for initial setup + core flows) |
| **Dependencies** | Docker Compose dev environment |
| **Area** | Testing |

### Problem

No end-to-end tests exist. The chat interface with SSE streaming, file uploads via TUS, and OAuth flows are complex interactions that unit tests cannot verify. Regressions in the frontend-backend integration go undetected.

### Implementation plan

1. **Install Playwright** in `frontend/`
2. **Docker-based test environment** — `docker-compose.test.yml` with postgres, redis, minio, api (seeded with test data)
3. **Core test scenarios**: login flow, send chat message + verify streaming response, upload document + verify processing status, admin operations
4. **CI integration** — run E2E tests on PR (after unit tests pass)
5. **Screenshot regression** — capture screenshots for visual regression testing

---

## 23. Alembic Database Migrations

| | |
|---|---|
| **Priority** | P2 — Valuable |
| **Status** | Not started |
| **Complexity** | High (~8-10 hours for initial setup + migration of existing schema) |
| **Dependencies** | None |
| **Area** | Backend |

### Problem

Database migrations are hand-written SQL files applied via a custom `_apply_schema()` / `_apply_auth_schema()` mechanism. There is no rollback capability, no auto-generation from model changes, and no consistency verification. This becomes increasingly risky as the schema grows.

### Implementation plan

1. **Initialize Alembic** in `backend/` with async support (`alembic init -t async`)
2. **Generate initial migration** from current `models.py` — mark as "baseline" (no actual changes)
3. **Migrate existing SQL files** — convert `db/migrations/*.sql` to Alembic revisions with `upgrade` and `downgrade`
4. **Replace `_apply_schema()`** in `main.py` with `alembic upgrade head` at startup (or as a pre-deploy step)
5. **CI check** — verify no pending migrations in the test pipeline

### Notes

- Keep existing `schema.sql` as documentation but remove it from the startup path
- Migration from custom system to Alembic requires careful handling of `schema_migrations` table state

---

## 24. Audit Log

| | |
|---|---|
| **Priority** | P2 — Valuable |
| **Status** | Not started |
| **Complexity** | Medium (~6-8 hours) |
| **Dependencies** | None |
| **Area** | Backend |

### Problem

Request logging and MCP audit exist, but there is no structured audit trail for data mutations: who created/updated/deleted a document, product, role, or tenant, and when. For enterprise customers, audit logs are often a compliance requirement.

### Implementation plan

1. **`audit_log` table** — `id`, `timestamp`, `tenant_id`, `action` (create/update/delete), `resource_type`, `resource_id`, `changes` (JSONB diff), `ip_address`, `request_id`
2. **Middleware or decorator** — `@audit("document.delete")` on router endpoints that automatically captures before/after state
3. **Immutable** — audit log entries are append-only, never updated or deleted
4. **Admin UI** — searchable audit log page with filters by tenant, resource type, action, date range
5. **Export** — CSV/JSON export for compliance teams

---

## 25. Webhook Notifications

| | |
|---|---|
| **Priority** | P2 — Valuable |
| **Status** | Not started |
| **Complexity** | Medium (~6-8 hours) |
| **Dependencies** | None |
| **Area** | Backend |

### Problem

No webhook system exists. Vendor integrations and third-party consumers cannot be notified when events occur (document ingested, ingestion failed, product updated). They must poll the API to detect changes.

### Implementation plan

1. **`webhooks` table** — `id`, `tenant_id`, `url`, `events` (array), `secret` (for HMAC signing), `active`, `created_at`
2. **CRUD endpoints** — `POST/GET/DELETE /api/v1/webhooks`
3. **Event emission** — after key operations (document.ingested, document.failed, product.created), enqueue a Celery task that POSTs JSON payload to registered webhook URLs
4. **HMAC signing** — sign payloads with `X-AI Mentor-Signature` header for verification
5. **Retry logic** — retry failed deliveries with exponential backoff (3 attempts)
6. **Delivery log** — store last N delivery attempts with status codes for debugging

---

## 26. Billing / Payment Integration

| | |
|---|---|
| **Priority** | P2 — Valuable |
| **Status** | Not started |
| **Complexity** | Very High (~20-30 hours) |
| **Dependencies** | Stripe/Paddle account, pricing model finalized |
| **Area** | Business |

### Problem

`billing/usage_writer.py` and `pricing.py` track usage and define pricing tiers, but there is no integration with a payment processor. No invoices, no payment collection, no hard enforcement of quotas when limits are exceeded.

### Implementation plan

1. **Choose provider** — Stripe (most mature) or Paddle (simpler VAT handling for SaaS)
2. **Subscription management** — sync tier changes with the payment provider; map AI Mentor roles to Stripe price IDs
3. **Usage-based billing** — report metered usage (LLM tokens, storage GB, API calls) to Stripe at end of billing period
4. **Hard limits** — when quota is exceeded, return `402 Payment Required` with upgrade CTA
5. **Customer portal** — billing history, invoices, payment method management (can use Stripe's hosted portal)
6. **Webhook receiver** — handle Stripe webhooks for payment success/failure, subscription changes

---

## 27. API Versioning Strategy

| | |
|---|---|
| **Priority** | P2 — Valuable |
| **Status** | Not started |
| **Complexity** | Medium (~4-6 hours for the strategy; ongoing for implementation) |
| **Dependencies** | None |
| **Area** | Backend |

### Problem

All endpoints are under `/api/v1`. There is no plan for introducing `/v2` when breaking changes are needed. External consumers (IDE plugins, vendor integrations) need stability guarantees.

### Implementation plan

1. **Deprecation header** — when a v1 endpoint will be removed, return `Sunset: <date>` and `Deprecation: true` headers
2. **Changelog** — public API changelog at `/api/v1/changelog` or in documentation
3. **Versioning policy** — document: "v1 will be supported for 12 months after v2 launch; breaking changes only in new major versions"
4. **Router structure** — prepare `api/v2/` router mount point in `main.py` for future use
5. **SDK versioning** — if/when a Python/JS SDK is published, pin it to API version

---

## 28. Database Backups

| | |
|---|---|
| **Priority** | P1 — Important |
| **Status** | Not started |
| **Complexity** | Medium (~4-6 hours) |
| **Dependencies** | VPS storage or external backup target |
| **Area** | Infrastructure |

### Problem

No automated database backup exists. A single `DROP TABLE` or disk failure would cause total data loss. MinIO objects have no backup either.

### Implementation plan

1. **`pg_dump` cron job** — daily compressed backup of the PostgreSQL database, stored locally and/or in an external S3 bucket
2. **MinIO replication** — configure MinIO bucket versioning or mirror to external S3
3. **Retention policy** — keep 7 daily + 4 weekly + 3 monthly backups
4. **Restore testing** — monthly test restore to a staging database to verify backup integrity
5. **Monitoring** — alert if backup job fails (integrate with Grafana alerting)

---

## 29. Multi-Modal RAG

| | |
|---|---|
| **Priority** | P3 — Nice-to-have |
| **Status** | Not started |
| **Complexity** | Very High (~20-30 hours) |
| **Dependencies** | Vision-capable LLM model |
| **Area** | RAG Pipeline |

### Problem

The platform processes only text (plus OCR for scanned PDFs). Technical documentation for hardware products often includes wiring diagrams, UI screenshots, architecture diagrams, and configuration tables in complex PDF layouts. These are either lost or poorly converted to text.

### Implementation plan

1. **Image extraction** — during PDF conversion, extract embedded images and store separately in MinIO
2. **Vision-based description** — use a vision model (Gemini Pro Vision) to generate text descriptions of diagrams and screenshots
3. **Store image descriptions as chunks** — link them to the parent document section; include in retrieval
4. **Table-aware PDF parsing** — use a structure-aware parser (e.g. `unstructured`, `camelot`, or Gemini vision) for complex tables
5. **Chat responses with images** — when a retrieved chunk references a diagram, include the image URL in the response sources

---

## 30. Cross-Language Retrieval

| | |
|---|---|
| **Priority** | P3 — Nice-to-have |
| **Status** | **Phase 1 done** (language-aware BM25 shipped in `1a199dd`) |
| **Complexity** | Remaining: ~8-10 hours |
| **Dependencies** | None (Phase 1 complete) |
| **Area** | RAG Pipeline |

### Problem

Documents may be in Russian or English, and users may query in either language. Current embeddings (Gemini embedding) have some multilingual capability, but there is no explicit cross-language support: no query translation, no language-aware boosting.

### What was shipped (Phase 1 — March 31, 2026)

- **Language detection at ingestion** — `lingua-language-detector` detects document language (en/ru/other) and stores it in `Document.detected_language` and `Chunk.language`
- **Language-aware BM25** — new `tsv_lang` tsvector column with language-specific stemming (`'russian'`, `'english'`, `'simple'` fallback); trigger updated; BM25 search uses combined tsquery (`simple || english || russian`)
- **Feature flag** — `MULTILANG_BM25_ENABLED` (default: true)
- **Backfill task** — `backfill_chunk_languages` Celery task for existing documents
- **Migration** — `018_multilang_bm25.sql`

### Remaining (Phase 2)

1. **Query language detection in classifier** — add `"language"` field to `_classify_query` response; pass to `search_documents`
2. **Cross-language query expansion** — translate query via Gemini Flash when query language differs from document language; dual BM25 search + RRF fusion
3. **Evaluation** — add cross-language test cases to the golden set

---

## 31. Horizontal Scaling / High Availability

| | |
|---|---|
| **Priority** | P3 — Nice-to-have |
| **Status** | Not started |
| **Complexity** | Very High (~30-40 hours) |
| **Dependencies** | Infrastructure budget, load balancer |
| **Area** | Infrastructure |

### Problem

Single VPS with one instance of each service. No redundancy — any service failure causes downtime. Celery workers cannot be scaled independently. Database has no read replicas.

### Implementation plan

1. **PostgreSQL read replica** — offload search queries to a read replica
2. **Redis Sentinel** — failover for Redis broker
3. **Multiple Celery workers** — scale worker instances by queue (ingestion vs monitoring)
4. **Load balancer** — nginx or cloud LB in front of multiple API instances
5. **Stateless API** — verify no in-memory state that would break with multiple instances (sessions are JWT-based, so this should be fine)
6. **Health check integration** — LB health checks against `/ready` endpoint
7. **Consider Kubernetes** — for automated scaling; evaluate cost vs complexity tradeoff

---

## 32. Input Sanitization Layer

| | |
|---|---|
| **Priority** | P1 — Important |
| **Status** | Not started |
| **Complexity** | Medium (~4-6 hours) |
| **Dependencies** | None |
| **Area** | Backend |

### Problem

Input validation relies on Pydantic schemas for type checking, but there is no explicit HTML/XSS sanitization for user-supplied text fields (product names, document titles, chat messages). While the React frontend escapes output by default, API consumers rendering AI Mentor data in other contexts may be vulnerable.

### Implementation plan

1. **Sanitization utility** — `bleach` or custom function to strip HTML/script tags from text inputs
2. **Apply to user-facing text fields**: product name/description, document title, chat message content, tenant name
3. **Pydantic validators** — add `@field_validator` to schemas that accept free-text input
4. **Content-Security-Policy header** — add CSP to API responses as defense-in-depth
5. **Test** — add unit tests with XSS payloads to verify sanitization

---

## Summary Table

| # | Item | Priority | Area | Complexity |
|---|------|----------|------|------------|
| 1 | Email Verification Flow | High | Backend | Medium |
| 2 | Landing: Interactive Demo | Medium | Frontend | High |
| 3 | Landing: CTA to Demo | Medium | Frontend | Medium |
| 5 | Landing: Tech/Business Toggle | Low | Frontend | Medium |
| 6 | RAG Eval: Golden Set | Medium | RAG | High |
| 7 | RAG Eval: A/B Comparison | Low | RAG | High |
| 8 | RAG Eval: Regression Alerts | Medium | RAG | Medium |
| 9 | RAG Eval: Retrieval-Only | Low | RAG | Medium |
| 10 | API Rate Limiting | **P0** | Backend | Medium |
| 12 | Sentry Integration | **P0** | Backend | Low |
| 13 | CORS Middleware | P1 | Backend | Low |
| 14 | CI/CD Pipeline | **P0** | DevOps | High |
| 15 | Test Coverage Measurement | P1 | Testing | Low |
| 16 | Guardrails / Safety Layer | P1 | RAG | High |
| 17 | Document Versioning | P2 | RAG | High |
| 18 | Feedback Loop | P2 | RAG | Medium |
| 19 | React Error Boundary | **P0** | Frontend | Low |
| 20 | Global Toast System | P1 | Frontend | Low |
| 21 | Data Fetching Layer | P1 | Frontend | High |
| 22 | E2E Tests (Playwright) | P2 | Testing | High |
| 23 | Alembic Migrations | P2 | Backend | High |
| 24 | Audit Log | P2 | Backend | Medium |
| 25 | Webhook Notifications | P2 | Backend | Medium |
| 26 | Billing Integration | P2 | Business | Very High |
| 27 | API Versioning Strategy | P2 | Backend | Medium |
| 28 | Database Backups | P1 | Infra | Medium |
| 29 | Multi-Modal RAG | P3 | RAG | Very High |
| 30 | Cross-Language Retrieval | P3 | RAG | **Phase 1 done** |
| 31 | Horizontal Scaling / HA | P3 | Infra | Very High |
| 32 | Input Sanitization | P1 | Backend | Medium |
