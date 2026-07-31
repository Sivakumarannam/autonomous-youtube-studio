# Autonomous YouTube Studio — Full Improvement Plan

> **Status:** Approved — implementation in progress.
> **Last updated:** 2026-07-18 (corrections applied per user review)
> **Goal:** Maximize YouTube earnings (views, likes, subscribers, watch-time hours) with Shorts (25–28 s) and long videos (6–8 min), auto-cross-post to Instagram 24 h after YouTube upload, and notify you on every upload event across Email, Discord, Telegram, Slack, and WhatsApp — all using free APIs only.

---

## Table of Contents
1. [Current State Audit](#1-current-state-audit)
2. [YouTube Monetization Improvements](#2-youtube-monetization-improvements)
3. [Instagram Auto-Upload (24 h delay)](#3-instagram-auto-upload-24-h-delay)
4. [Notification System Improvements](#4-notification-system-improvements)
5. [API Keys Needed](#5-api-keys-needed)
6. [Implementation Order](#6-implementation-order)
7. [What Is Already Working](#7-what-is-already-working)
8. [Risks & Notes](#8-risks--notes)

---

## 1. Current State Audit

### ✅ What Already Works Well
| Feature | Status | Notes |
|---|---|---|
| Short scripts (25–28 s) | ✅ Working | 65–75 words enforced (verified in prompts.py line 92) |
| Quality gate (7-dimension scoring, min 70) | ✅ Working | Separate threshold 55 for shorts |
| Hook overlay (0–1.5 s visual) | ✅ Working | Baked into renderer |
| Ken Burns zoom/pan on images | ✅ Working | Visual interest |
| Karaoke captions | ✅ Working | Word-by-word animations |
| SEO metadata agent | ✅ Working | Titles, descriptions, tags |
| YouTube OAuth upload | ✅ Working | Resumable upload |
| Email notifications | ✅ Exists | Needs wiring verification |
| Discord webhook notifications | ✅ Exists | Needs wiring verification |
| Telegram bot notifications | ✅ Exists | Needs wiring verification |
| Slack webhook notifications | ✅ Exists | Needs wiring verification |
| Instagram cross-post skeleton | ⚠️ Partial | 24-h delay not enforced; Reels flow incomplete |
| WhatsApp notifications | ❌ Missing | Needs adding (CallMeBot) |
| Long scripts (6–8 min) | ⚠️ Bug present | Known duplication bug — see below |
| Chapter markers (long videos) | ❌ Missing | Critical for watch-time |
| YouTube Shorts `#Shorts` tag auto-add | ⚠️ Needs verification | Required for Shorts shelf |
| Thumbnail A/B variant generation | ❌ Missing | Big CTR impact |
| Pinned comment | ❌ Not possible via API | Posting a comment IS possible; pinning is manual only |
| AI Presenter/Avatar (PiP) | 🚫 Deliberately OFF | Left disabled — free-tier GPU reliability issues confirmed |

### 🐛 Known Bugs to Fix

#### Long-Script Duplication Bug (root cause confirmed)
**Symptom:** The opening hook/intro sentence is experienced twice — once as a visual text overlay, once spoken in the narration audio.

**Root cause (3 locations):**
1. `app/agents/long_script_agent/agent.py` lines 223–231 — `full_script` already contains `introduction` text verbatim
2. `app/agents/video_agent/service.py` line 426 — `output.title` (derived from `script.hook`) is passed as `hook_text`
3. `app/agents/video_agent/renderer.py` lines 152 & 606 — `hook_text` is rendered as a visual overlay while the narration audio simultaneously reads the same words from `full_script`

**Fix:** The hook overlay should display a *visual-only* summary label (e.g. the SEO title or a 2–3 word teaser), **not** the spoken opening sentence. The spoken hook lives in `full_script`/audio — the overlay should complement it visually, not duplicate it verbally.

---

## 2. YouTube Monetization Improvements

### 2A. Shorts (25–28 seconds)

| # | Improvement | How |
|---|---|---|
| S1 | Enforce `#Shorts` in every short's title | SEO agent prompt update |
| S2 | Loop-able endings — last scene connects back to first | Short script prompt update |
| S3 | On-screen text every 3–5 s (pattern interrupt) | Script prompt + renderer validation |
| S4 | First-frame hook image must show a number or question | Storyboard agent prompt |
| S5 | Verify audio is exactly 25–28 s (trim/extend if off) | Voice agent post-processing |
| S6 | Captions: large, centered, high-contrast (yellow/white with black stroke) | Renderer config update |
| S7 | Auto-post a comment after upload ("🔥 Watch this 3x — it gets better!") | Upload agent: `commentThreads.insert` via YouTube API. **Note: pinning the comment is NOT possible via API — must be done manually in YouTube Studio.** |

---

### 2B. Long Videos (6–8 Minutes)

| # | Improvement | How |
|---|---|---|
| L1 | Fix duplication bug (intro text heard + shown simultaneously) | `video_agent/service.py` line 426 — use SEO title as `hook_text`, not spoken hook sentence |
| L2 | Add chapter timestamps to YouTube description (00:00 Intro, …) | Upload agent: auto-generate from script sections list |
| L3 | Add teaser line every 90 s: "Coming up at X minutes…" | Long script prompt update |
| L4 | End screen metadata | **NOT possible via YouTube Data API** (no `videoEndScreens.insert` endpoint exists — confirmed missing per Google Issue Tracker #387277988). Must be set manually in YouTube Studio after upload. Dashboard will display a reminder checklist for manual actions. |
| L5 | Pattern interrupt validation in quality gate (count minimum 3) | Quality agent: count interrupts |
| L6 | Auto-post a comment after upload ("⏱ Chapter list in description — jump to what you need!") | Upload agent: `commentThreads.insert` via YouTube API. **Note: pinning is manual — do it in YouTube Studio.** |
| L7 | Outro CTA spoken + on-screen: "Subscribe — next video is [topic hint]" | Long script prompt + storyboard prompt |
| L8 | Consider bumping target to 8 min 5 s to unlock mid-roll ads | Long script prompt: target 1600–2100 words — **requires your approval before implementing** |

---

### 2C. Thumbnails & Titles

| # | Improvement | How |
|---|---|---|
| T1 | Thumbnail: max 3 bold words + 1 number or emoji (no clutter) | Thumbnail agent prompt rewrite |
| T2 | Thumbnail: high-contrast background (red/yellow/blue) | Thumbnail agent: Pollinations/HF image prompt |
| T3 | Title: use power words (Secret, Banned, Nobody Tells You, Finally) | SEO agent title prompt rules |
| T4 | Title: include the year (2025 or 2026) for freshness signal | SEO agent: append year to title |
| T5 | Generate 2 thumbnail variants (A and B) — dashboard shows both for manual pick | Thumbnail agent: 2 calls with different prompts |
| T6 | Description: first 2 lines must be hook text (shown before "Show more") | SEO agent: description format rule |

---

### 2D. SEO & Metadata

| # | Improvement | How |
|---|---|---|
| M1 | Tags: exactly 15–20 tags (YouTube ignores >20) | SEO agent: enforce tag count |
| M2 | First tag = exact match of title keyword | SEO agent prompt |
| M3 | Hashtags: add 3–5 `#hashtags` at end of description | SEO agent prompt |
| M4 | Category: auto-set correct YouTube category ID | Upload agent: map topic → category |
| M5 | Default language + captions language set in upload | Upload agent: `defaultLanguage: "en"` |

---

### 2E. Engagement Signals (First-Hour Push)

| # | Improvement | How |
|---|---|---|
| E1 | Auto-post comment after upload (not pinned — manual pin in YouTube Studio) | YouTube `commentThreads.insert` API call in upload agent |
| E2 | Dashboard shows manual-action reminder after every upload (pin comment, add end screen in Studio, share link) | New dashboard notification banner |
| E3 | Notify you (all channels) immediately on upload so you can share it | Notification system (see Section 4) |

---

## 3. Instagram Auto-Upload (24-Hour Delay)

### How It Will Work

```
YouTube Upload Completes
        │
        ▼
  Save upload record in DB
  with: youtube_url, title, description, thumbnail_path,
        script_type (short/long), published_at timestamp
        │
        ▼
  Scheduler checks every 15 minutes:
  "Are there uploaded videos where
   published_at + 24h < NOW and instagram_posted = False?"
        │
        ▼
  If YES → Post to Instagram
     - Shorts → Instagram Reels (9:16 already)
     - Long videos → Instagram Video post (first 60 s clip)
        │
        ▼
  Mark instagram_posted = True in DB
  Send notification: "✅ Posted to Instagram: [title]"
```

### Instagram Posting Method (Free — Instagram Graph API)
- Requires a **Facebook Page** linked to an **Instagram Business/Creator account**
- Credentials needed: `INSTAGRAM_ACCESS_TOKEN` + `INSTAGRAM_BUSINESS_ACCOUNT_ID`
- For Reels: upload video container → publish (2-step API — already partially in `app/integrations/instagram.py`)
- For long videos: trim first 60 s using MoviePy (already installed) → post as Reel/Video

### Changes Needed
1. Add `instagram_posted`, `instagram_posted_at` columns to videos table (Alembic migration)
2. Complete `app/integrations/instagram.py` — Reels upload flow (container create → publish)
3. Scheduler: add `check_instagram_queue` job every 15 min
4. Add `INSTAGRAM_ACCESS_TOKEN` and `INSTAGRAM_BUSINESS_ACCOUNT_ID` to config
5. Long video teaser: `trim_video_clip(path, duration=60)` utility using MoviePy

---

## 4. Notification System Improvements

### Notification Events

| Event | Channels |
|---|---|
| ✅ YouTube upload succeeded | Email + Discord + Telegram + Slack + WhatsApp |
| ❌ YouTube upload failed | Email + Discord + Telegram + Slack + WhatsApp |
| ✅ Instagram posted (24 h later) | Email + Discord + Telegram + Slack + WhatsApp |
| ❌ Instagram post failed | Email + Discord + Telegram + Slack + WhatsApp |
| ⚠️ Pipeline error | Discord + Telegram (quick ops alerts) |

### Standard Notification Format (All Channels)

**Success:**
```
✅ YouTube Upload Successful
📹 Title: "5 Python Tricks Nobody Tells You #Shorts"
🔗 URL: https://youtube.com/shorts/abc123
📊 Type: Short | Duration: 27s
🕐 Uploaded: 2026-07-18 14:30 UTC
📸 Instagram post scheduled for: 2026-07-19 14:30 UTC
📌 Manual actions needed in YouTube Studio:
   → Pin the auto-posted comment
   → Add end screen (last 20 s) — subscribe button + last video card
```

**Failure:**
```
❌ YouTube Upload FAILED
📹 Title: "5 Python Tricks Nobody Tells You #Shorts"
💥 Error: Quota exceeded — retry scheduled in 1 hour
🕐 Failed at: 2026-07-18 14:30 UTC
```

### 4A. Email (Gmail SMTP — free)
- Requires: `SMTP_HOST` (smtp.gmail.com), `SMTP_PORT` (587), `SMTP_USER`, `SMTP_PASSWORD` (Gmail App Password), `NOTIFY_EMAIL_TO`
- HTML template with thumbnail embedded, success/failure/Instagram variants

### 4B. Discord (Webhook — free)
- Rich embed: green=success, red=failure, blue=Instagram
- Thumbnail image in embed, clickable video URL
- Requires: `DISCORD_WEBHOOK_URL`

### 4C. Telegram Bot (Bot API — free)
- Photo message with thumbnail + caption, inline "▶ Watch" button
- Requires: `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`

### 4D. Slack (Incoming Webhook — free)
- Block Kit formatted message with image, fields, action button
- Requires: `SLACK_WEBHOOK_URL`

### 4E. WhatsApp via CallMeBot (free, personal use)
- Free API: `GET https://api.callmebot.com/whatsapp.php?phone=NUMBER&text=MSG&apikey=KEY`
- Setup: send one WhatsApp message to CallMeBot to activate (instructions at callmebot.com)
- Text-only (~100 msg/day free limit)
- Requires: `WHATSAPP_PHONE` (e.g. `+919876543210`) + `WHATSAPP_APIKEY`

---

## 5. API Keys Needed

| # | Key | Purpose | Free? |
|---|---|---|---|
| 1 | `YOUTUBE_API_KEY` | YouTube Data API | ✅ Free quota |
| 2 | `YOUTUBE_CLIENT_ID` | YouTube OAuth2 | ✅ Free |
| 3 | `YOUTUBE_CLIENT_SECRET` | YouTube OAuth2 | ✅ Free |
| 4 | `YOUTUBE_REFRESH_TOKEN` | YouTube OAuth2 | ✅ Free |
| 5 | `DASHBOARD_AUTH_TOKEN` | Dashboard login | ✅ You set this |
| 6 | `HF_API_TOKEN` | Hugging Face image generation | ✅ Free tier |
| 7 | `PEXELS_API_KEY` | Stock image backgrounds | ✅ Free tier |
| 8 | `PIXABAY_API_KEY` | Stock image backgrounds fallback | ✅ Free tier |
| 9 | `JAMENDO_CLIENT_ID` | Royalty-free background music | ✅ Free |
| 10 | `GROQ_API_KEY` | Fast LLM inference (Llama 3) | ✅ Free tier |
| 11 | `SMTP_USER` | Gmail address for email alerts | ✅ Free |
| 12 | `SMTP_PASSWORD` | Gmail App Password | ✅ Free |
| 13 | `NOTIFY_EMAIL_TO` | Where to receive alerts | ✅ Free |
| 14 | `DISCORD_WEBHOOK_URL` | Discord notifications | ✅ Free |
| 15 | `TELEGRAM_BOT_TOKEN` | Telegram bot | ✅ Free |
| 16 | `TELEGRAM_CHAT_ID` | Your Telegram chat | ✅ Free |
| 17 | `SLACK_WEBHOOK_URL` | Slack notifications | ✅ Free |
| 18 | `WHATSAPP_PHONE` | Your WhatsApp number | ✅ Free |
| 19 | `WHATSAPP_APIKEY` | CallMeBot API key | ✅ Free |
| 20 | `INSTAGRAM_ACCESS_TOKEN` | Instagram Graph API | ✅ Free |
| 21 | `INSTAGRAM_BUSINESS_ACCOUNT_ID` | Instagram Graph API | ✅ Free |

---

## 6. Implementation Order

### Phase 1 — Environment Setup ← IN PROGRESS
- Install all packages ✅
- Fix workflow Python path ✅
- Set API keys (asking one at a time)
- Run database migrations
- Verify app starts and dashboard is accessible

### Phase 2 — Bug Fixes + YouTube Monetization Improvements
- Fix long-script duplication bug (L1)
- Short script: `#Shorts` enforcement, loop-able ending (S1, S2)
- Long script: chapter timestamps, pattern interrupt validation, 8-min option (L2, L3, L5)
- SEO agent: power words, year, tag count, description format (T3, T4, M1–M5)
- Thumbnail agent: 2 variants with bold text (T1, T2, T5)
- Upload agent: auto-post comment after upload (S7, L6 — posting only, pinning is manual)
- Dashboard: manual-action reminder banner after upload (E2)

### Phase 3 — Notification System
- Wire Email, Discord, Telegram, Slack to upload events
- Add WhatsApp (CallMeBot) to `app/notifications/service.py`
- Standardize rich message format across all channels

### Phase 4 — Instagram Auto-Upload
- DB migration: `instagram_posted`, `instagram_posted_at` columns
- Complete Instagram Reels upload flow
- Long video: 60-second teaser clip via MoviePy
- Scheduler: 24-h delay queue check job
- Instagram success/failure notifications on all channels

### Phase 5 — Testing & Monitoring
- End-to-end test: generate Short → YouTube → all notifications → Instagram 24 h later
- Dashboard: Instagram status column, notification history panel

---

## 7. Deliberately Out of Scope

- **AI Presenter / Avatar (PiP)** — `PRESENTER_ENABLED=false` — deliberate decision, left unchanged
- **End screens via API** — not possible (no YouTube API endpoint exists)
- **Pinning comments via API** — not possible (manual step in YouTube Studio)
- **Paid APIs of any kind**

---

## 8. Risks & Notes

| Risk | Mitigation |
|---|---|
| YouTube API quota (10,000 units/day free) | Each upload ~1,600 units. Max ~6 uploads/day. Analytics costs extra. |
| Instagram Graph API requires Facebook Page | Must have Facebook Page linked to Instagram Business/Creator account |
| CallMeBot WhatsApp limit ~100 msgs/day | Fine for notification use |
| Groq free tier rate limits | Falls back to Ollama automatically |
| 8-min target for mid-roll ads | Won't implement without explicit approval (currently 6–8 min) |
