# 🎬 Autonomous YouTube Studio — Full Project Audit

> **Purpose:** Pre-deployment review — every known issue, risk, and improvement opportunity in one place.
> Last updated: 2026-07-30

---

## 📊 Quick Summary

| Area | Status | Priority |
|------|--------|----------|
| Core pipeline (script → video) | ✅ Working | — |
| LLM (Groq + Gemini fallback) | ✅ Working | — |
| TTS (Kokoro + gTTS fallback) | ✅ Working | — |
| Database + migrations | ✅ Working | — |
| Dashboard auth | ✅ Working | — |
| YouTube upload | ⚠️ OAuth creds needed | HIGH |
| Security hardening | ⚠️ Several gaps | HIGH |
| Free API rate limits | ⚠️ Know your limits | MEDIUM |
| Retry / resilience | ⚠️ Gaps exist | MEDIUM |
| Test coverage | ⚠️ Not measured | LOW |
| Video quality for monetization | ⚠️ Needs tuning | HIGH |

---

## 🔴 CRITICAL — Fix Before Deploying

### 1. Default dev secrets are unsafe in production
**Files:** `app/core/config.py` lines 53–58, 428–439

The app ships with hardcoded fallback secrets:
- `APP_SECRET_KEY` defaults to `"dev-secret-key"`
- `JWT_SECRET_KEY` defaults to `"jwt-dev-secret"`

If `SESSION_SECRET` / `JWT_SECRET_KEY` are not set as Replit Secrets, sessions can be forged.

**Fix:** Add both as Replit Secrets with long random values (32+ chars). Already done for `SESSION_SECRET` — also add `JWT_SECRET_KEY`.

---

### 2. Dashboard is fully open when `DASHBOARD_AUTH_TOKEN` is empty in dev mode
**File:** `app/web/auth.py` lines 62–69

When `APP_ENV=development` and no `DASHBOARD_AUTH_TOKEN` is set, the dashboard skips auth entirely — anyone who reaches the URL can control the pipeline.

**Fix:** Always set `DASHBOARD_AUTH_TOKEN` regardless of environment. ✅ Done (you added it), but worth noting for future redeploys.

---

### 3. Login endpoint has no brute-force protection
**File:** `app/main.py` lines 399–422

The global rate limiter is 200 req/min across all routes. The `/login` POST is not tightened to e.g. 5 attempts/minute per IP, so someone can brute-force the dashboard token.

**Fix:** Add a per-route `@limiter.limit("5/minute")` decorator to the login POST handler.

---

### 4. WebSocket `/ws/pipeline` is unauthenticated
**Files:** `app/main.py` lines 531–535, `app/websocket/manager.py`

Anyone who knows your app URL can connect to the WebSocket and receive live pipeline events (video titles, upload statuses, channel names). It also opens resource-exhaustion potential.

**Fix:** Check for a valid session cookie (or a token query param) in the WebSocket handshake before upgrading the connection.

---

### 5. `/storage` directory is publicly accessible
**File:** `app/main.py` lines 446–450

Generated videos, thumbnails, audio, and scripts are mounted at `/storage` and served to anyone — no auth. This means anyone can download your generated videos before they even hit YouTube.

**Fix:** Either remove the static mount and serve media only through authenticated endpoints, or restrict it to dashboard-authenticated requests.

---

### 6. YouTube OAuth credentials not connected
**Env vars needed:** `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`

Without these, the upload agent silently skips. `AUTO_UPLOAD=true` does nothing and all pipeline runs end in "scheduled" forever. **This is the core money-making path — it must work.**

**Fix:** See Task #3 already proposed. Steps:
1. Go to [Google Cloud Console](https://console.cloud.google.com) → Create project → Enable YouTube Data API v3
2. Create OAuth 2.0 credentials (Desktop app type)
3. Run the OAuth flow once locally to get a refresh token
4. Add all three as Replit Secrets

---

## 🟡 IMPORTANT — Fix Soon After Deploying

### 7. Video quality preset is `draft` — not good enough for monetization
**File:** `app/core/config.py` env var `VIDEO_QUALITY_PRESET=draft`

YouTube monetization (YouTube Partner Program) requires:
- Minimum 1000 subscribers + 4000 watch hours OR 1000 subscribers + 10M Shorts views
- Videos must be **original, high-quality content** — not AI spam
- Draft quality renders will look low-effort

**Fix:** Set `VIDEO_QUALITY_PRESET=high` after confirming render times are acceptable. Also consider:
- Adding proper intro/outro branding
- Making scripts longer and more engaging (8+ minutes for ad revenue)
- Adding real B-roll images (Pexels key helps here)

---

### 8. No stock photo key = lower quality thumbnails and B-roll
**Env vars:** `PEXELS_API_KEY` (free at pexels.com/api), `PIXABAY_API_KEY` (free at pixabay.com/api)

Without these, the pipeline falls back to Pollinations AI for all images. Real stock photos look more professional and get better click-through rates on YouTube.

**Fix:** Register free accounts and add the API keys. Pexels gives 200 req/hour free.

---

### 9. No background music = less engaging videos
**Env var:** `JAMENDO_CLIENT_ID` (free at devportal.jamendo.com) OR add MP3s to `storage/music/`

Background music increases watch time (a key monetization metric).

**Fix:** Either get a free Jamendo key or download a few royalty-free tracks and drop them in `storage/music/electronic.mp3`, `storage/music/ambient.mp3`, etc.

---

### 10. Instagram cross-post retries forever with no cap
**File:** `app/scheduler/instagram_scheduler.py` lines ~97–177

Failed Instagram cross-posts retry on every scheduler tick indefinitely, with no backoff and no attempt limit. Orphan containers can accumulate on the Instagram API side.

**Fix:** Add a max attempt counter (e.g. 3 tries) and a `failed_at` timestamp on the upload record, then stop retrying after the cap.

---

### 11. Duplicate packages in `requirements.txt`
**File:** `requirements.txt`

The file has two full package lists — the original and a copy that was appended. Causes resolver noise and confusion.

Also: `praw` is listed but the code uses `asyncpraw`. `asyncpraw` should be explicit.

**Fix:** Deduplicate the file, remove `praw`, keep `asyncpraw`.

---

### 12. alembic.ini contains a hardcoded sample credential
**File:** `alembic.ini` line 37

Contains `postgres:postgres` as a sample connection string. While `env.py` overrides it at runtime, it creates confusion and could be accidentally used.

**Fix:** Replace the hardcoded string with a comment: `# Set via DATABASE_URL env var — see env.py`.

---

## 🟠 RESILIENCE — Gaps That Can Break Overnight Runs

### 13. YouTube upload has no idempotency guard on chunk failure
**File:** `app/agents/upload_agent/`

If a video is mid-upload and the container restarts, the pipeline might not detect it was already submitted to YouTube. The scheduler checks `youtube_video_id` and `PUBLISHED` status, but if neither was persisted before the crash, a duplicate upload is possible.

**Fix:** After a successful YouTube API call, immediately write `youtube_video_id` before any further processing.

---

### 14. Pipeline runs stuck in RUNNING on container restart
**File:** `app/main.py` startup lifespan — already has orphan recovery logic

This is already partially handled (orphaned RUNNING runs are reset on startup). Confirm this covers all edge cases by testing a kill-and-restart scenario.

---

### 15. No TTS retry or provider fallback on transient failures
**File:** `app/agents/voice_agent/`

If Kokoro fails (memory, model load error), gTTS is the fallback — but network errors in gTTS (it calls Google's servers) are not retried. A temporary network blip fails the whole voice stage.

**Fix:** Wrap gTTS calls in a small retry loop (3 attempts, 5s backoff).

---

### 16. Automation scheduler can permanently lose a channel to a crash
**File:** `app/scheduler/automation_scheduler.py` lines ~350–380

A DB failure mid-automation can leave a channel in RUNNING state permanently (no timeout to auto-reset). The pipeline would never run for that channel again without manual intervention.

**Fix:** Add a `last_run_started_at` column and a watchdog that resets RUNNING channels older than 2 hours.

---

## 💰 YouTube Monetization Reality Check

### Can this project earn money?

**Yes, but with conditions:**

| Requirement | Status |
|-------------|--------|
| Original content (not re-uploaded) | ✅ Pipeline generates original scripts |
| Consistent upload schedule | ✅ Automation scheduler handles this |
| 1000 subscribers | ⏳ Takes time — promote on Reddit/social |
| 4000 watch hours (or 10M Shorts views) | ⏳ Long-form videos help most |
| Not "spam" content per YouTube policy | ⚠️ AI-only content is monitored — add human review |
| YouTube Partner Program approval | Manual Google review process |

### Free API Limits (know these!)

| Service | Free Tier | Risk |
|---------|-----------|------|
| **Groq** | ~14,400 req/day on free tier | Pipeline uses ~5–10 calls per video |
| **Gemini** (fallback) | 1,500 req/day free | Backup if Groq quota hit |
| **YouTube Data API v3** | 10,000 units/day | Upload = 1,600 units; ~6 uploads/day max on free |
| **Pexels** | 200 req/hour, 20,000/month | Fine for 1–2 videos/day |
| **Pollinations AI** | Unlimited (public) | No guarantees; can be slow |
| **Jamendo** | Varies by plan | Check license terms for YouTube monetization |
| **gTTS** | Unlimited (Google Translate) | Against ToS for commercial use at scale |
| **Kokoro ONNX** | Free, runs locally | ✅ Best for commercial — no API limits |

### ⚠️ Important: gTTS License Risk

gTTS uses Google Translate's TTS, which is **against Google's ToS for commercial/automated use**. Kokoro (your primary TTS) is fine — it runs locally with an open model. Keep `VOICE_PROVIDER=auto` so Kokoro is always tried first.

---

## 🔵 FUTURE IMPROVEMENTS (After Going Live)

### Content Quality
- [ ] **Human review gate** — add a "approve before upload" step where you watch the generated video in the dashboard before it goes live. Prevents low-quality videos from hurting your channel.
- [ ] **A/B test thumbnails** — generate 2 thumbnail variants, pick winner after 48h by CTR
- [ ] **Chapter markers** — add timestamps to video descriptions (boosts SEO)
- [ ] **End screens / cards** — add subscribe prompts at end of video (requires post-processing)

### Growth & Distribution
- [ ] **Reddit auto-post** — post video link to relevant subreddits after upload (PRAW integration already exists)
- [ ] **Twitter/X cross-post** — share clips when video goes live
- [ ] **Email digest** — weekly summary of views, revenue, top video

### Technical
- [ ] **Measure test coverage** — add `pytest-cov` and run `pytest --cov=app`; target 70%+
- [ ] **Per-IP rate limiting on login** — 5 attempts/minute
- [ ] **WebSocket auth** — check session cookie on upgrade
- [ ] **Pinned dependency versions** — pin all packages in requirements.txt to prevent breakage on redeploy (`pip freeze > requirements.txt`)
- [ ] **Storage auth** — serve generated media only to authenticated users
- [ ] **Celery/Redis workers** — if you scale to 10+ videos/day, move rendering to background workers
- [ ] **Video deduplication** — check if a topic was already covered before generating a new script

### Monitoring
- [ ] **Slack or Discord webhook** — get pinged when a video uploads or a pipeline fails (already supported, just needs a webhook URL secret)
- [ ] **Analytics dashboard** — track views/subscribers/revenue over time (analytics_agent already writes to DB)
- [ ] **Uptime alerting** — use UptimeRobot (free) to ping `/health` and alert if the app goes down

---

## ✅ Pre-Deploy Checklist

Before hitting "Deploy" in Replit:

- [ ] `JWT_SECRET_KEY` secret added (long random string)
- [ ] `DASHBOARD_AUTH_TOKEN` secret set ✅
- [ ] `GROQ_API_KEY` set ✅
- [ ] `VIDEO_QUALITY_PRESET` changed from `draft` to `high`
- [ ] YouTube OAuth credentials set (`YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`)
- [ ] `PEXELS_API_KEY` added (free, improves video quality)
- [ ] `JAMENDO_CLIENT_ID` added OR MP3s in `storage/music/` (check music license for YouTube monetization)
- [ ] Test a full pipeline run: trigger from dashboard → confirm video file renders → confirm upload to YouTube
- [ ] Watch the generated video — does it look good enough to publish?
- [ ] Set up Slack or Discord webhook for failure alerts
- [ ] Enable `APP_ENV=production` ✅ (already set)
- [ ] Disable `APP_DEBUG=false` ✅ (already set)
- [ ] Confirm `/storage` route is acceptable or lock it down

---

## 📁 Key Files Reference

| File | What it does |
|------|-------------|
| `app/core/config.py` | All settings — start here for any config change |
| `app/main.py` | App startup, middleware, route registration |
| `app/agents/pipeline_agent/service.py` | Full pipeline orchestration |
| `app/scheduler/scheduler.py` | Publish scheduler (upload timing) |
| `app/scheduler/automation_scheduler.py` | Daily automation per channel |
| `app/web/auth.py` | Dashboard login/session logic |
| `app/templates/dashboard/` | All dashboard HTML templates |
| `app/integrations/kokoro_tts.py` | Primary TTS engine |
| `replit.md` | Full env var / secrets reference |
| `QUICK_START_GUIDE.md` | How to use the dashboard |

---

*Generated by full automated project scan — 2026-07-30*
