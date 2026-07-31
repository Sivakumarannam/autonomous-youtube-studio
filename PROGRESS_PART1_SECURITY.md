# ✅ Part 1 Complete — Security Hardening

**Date:** 2026-07-30  
**Status:** DONE — app restarted and running clean

---

## What Was Fixed

| # | Issue | Fix Applied | File |
|---|-------|-------------|------|
| 1 | Hardcoded `jwt-dev-secret` used as fallback token | `JWT_SECRET_KEY` added as Replit Secret | `app/core/config.py` |
| 2 | Login endpoint had no brute-force protection | Added `@limiter.limit("5/minute")` — only 5 login attempts per IP per minute | `app/main.py` |
| 3 | WebSocket `/ws/pipeline` open to anyone | Now validates session cookie before accepting connection; rejects with code 1008 | `app/api/routes/websocket.py` |
| 4 | `requirements.txt` had full duplicate block + `praw` instead of `asyncpraw` | Removed all duplicates, added `google-auth-httplib2`, `yt-dlp`, `pytest-cov` properly | `requirements.txt` |
| 5 | `alembic.ini` had hardcoded `postgres:postgres` credential | Replaced with a comment pointing to `env.py` | `alembic.ini` |

---

## Secrets Now Active

| Secret | Status | Purpose |
|--------|--------|---------|
| `SESSION_SECRET` | ✅ | App session signing (Replit auto-injects) |
| `JWT_SECRET_KEY` | ✅ Added now | JWT token signing — no longer falls back to `jwt-dev-secret` |
| `DASHBOARD_AUTH_TOKEN` | ✅ | Dashboard login password |
| `GROQ_API_KEY` | ✅ | Primary LLM |
| `GEMINI_API_KEY` | ✅ | LLM fallback |

---

## Still Open from Audit

> `/storage` public access — videos are still downloadable by anyone with the URL.  
> This is intentional for now (Instagram cross-posting needs public video URLs).  
> Will revisit in a later part once all integrations are connected.

---

## 🔜 Next: Part 2 — YouTube Upload (the money path)

**Keys needed:**
- `YOUTUBE_CLIENT_ID`
- `YOUTUBE_CLIENT_SECRET`
- `YOUTUBE_REFRESH_TOKEN`

Without these, no video ever uploads to YouTube. This is the most important part.

**How to get them (if you haven't already):**
1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a project → Enable **YouTube Data API v3**
3. Go to **Credentials** → Create **OAuth 2.0 Client ID** (Desktop app type)
4. Download the JSON → get `client_id` and `client_secret`
5. Run the OAuth flow once to get a `refresh_token`  
   *(The app has a `/auth/callback` route that handles this — see `app/api/routes/youtube_auth.py`)*
