# Lexiro — Backlog

> Tasks planned for future implementation. Each item includes problem statement, proposed solution, and complexity estimate.

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

## 4. Product Deletion: Progress Bar for Large Products

| | |
|---|---|
| **Priority** | High |
| **Status** | Not started |
| **Complexity** | Medium (~4-6 hours) |
| **Dependencies** | None |

### Problem

When deleting a product that contains a large number of documents (~15 000), the confirmation dialog freezes for over a minute with no feedback. The user sees a "dead" modal with no indication of progress, which looks like the app has crashed. This is a poor UX for any bulk-destructive operation.

### Implementation plan

**Backend:**

1. **Convert product deletion to an async Celery task** — instead of deleting all documents synchronously in the request handler, enqueue a `delete_product` task that:
   - Deletes documents in batches (e.g. 500 at a time)
   - Reports progress after each batch via a task state update (`meta={'deleted': N, 'total': M}`)
   - Removes the product record after all documents are deleted
2. **New endpoint `GET /api/v1/products/{product_id}/delete-status`** — returns current deletion progress (`deleted`, `total`, `state`) by querying the Celery task result backend

**Frontend:**

1. **Close the confirmation dialog immediately** after the delete request is accepted (HTTP 202)
2. **Show a progress bar** — either inline in the products table (replacing the deleted row) or as a toast/notification with a progress indicator
3. **Poll the delete-status endpoint** every 1-2 seconds until the task completes, updating the progress bar
4. **Handle completion** — remove the product from the list and show a success message
5. **Handle errors** — if the task fails mid-way, show an error with the count of documents deleted so far

### Notes

- The same pattern can be reused for other bulk operations (e.g. bulk document deletion)
- Consider using SSE (Server-Sent Events) instead of polling if real-time updates are preferred — the project already supports SSE via nginx config
- Mark the product as "deleting" in the DB to prevent concurrent edits while deletion is in progress

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
