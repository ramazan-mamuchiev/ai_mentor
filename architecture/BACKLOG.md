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
