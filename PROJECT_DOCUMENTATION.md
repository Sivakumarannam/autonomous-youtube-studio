# Autonomous YouTube Studio — Project Documentation

**Last updated:** July 7, 2026
**Status:** Phases 1–6 complete and verified in production. SEO/Metadata Scoring in progress.

---

## 1. What This Project Is

A fully autonomous YouTube content pipeline: given a topic, it generates a
script, quality-checks it, renders a video (with AI-generated scene
backgrounds), uploads it to YouTube on a schedule, tracks analytics, and —
once "Channel Automation" is turned on for a channel — does all of this
**every day, indefinitely, with zero human input**, until the user pauses
or archives the channel.

It also includes a live operations dashboard (HTMX + WebSocket) for
monitoring and manually intervening (approve/reject/delete uploads,
start/pause channel automation, trigger one-off runs).

---

## 2. Tech Stack

- **Backend:** FastAPI (async), SQLAlchemy 2.x (async), Alembic migrations
- **Database:** PostgreSQL (asyncpg driver)
- **LLM:** Ollama (local, `qwen2.5-script:latest` model) — no paid API
- **Video rendering:** MoviePy + PIL, faster-whisper for audio/caption sync
- **Image generation:** Pollinations AI (free, no key) → Hugging Face
  Inference API (optional fallback) → solid-color text card (final fallback)
- **YouTube integration:** google-api-python-client patterns via raw httpx
  calls (OAuth2 refresh-token flow), resumable upload with correct
  Content-Range chunking
- **Scheduling:** APScheduler (two independent jobs — see Phase 2 and
  Final Phase below)
- **RAG (optional):** DuckDuckGo search → trafilatura extraction →
  sentence-transformers embeddings → FAISS + SQLite vector store
  (chromadb was tried but is blocked by some sandboxed environments'
  package firewalls — FAISS+SQLite is the permanent choice, not a
  workaround)
- **Dashboard:** Jinja2 + HTMX (no React/build step), native FastAPI
  WebSockets, Prometheus `/metrics` endpoint
- **Auth:** Simple shared-token guard (Bearer or Basic) on `/dashboard`
  and `/metrics` only — not a full user-auth system

---

## 3. Phase-by-Phase Summary

### Phase 1 — Core Agent Pipeline
- `script_agent` (short/long) → `quality_agent` → `video_agent` →
  `upload_agent` → `analytics_agent`, each independently callable.
- **Key bug fixed:** `renderer.py`'s `_assemble_video()` originally used a
  running `current` time accumulator that silently drifted from Whisper's
  real per-sentence timestamps, causing scene cards to desync from
  narration. Fixed to place each scene at its actual Whisper `start_seconds`
  and hold until the next scene's real start (preserving natural pauses).
- **Key bug fixed:** `uploader.py`'s resumable upload loop was missing
  `Content-Range` headers on chunk PUTs, causing YouTube to treat every
  256KB chunk as a complete (corrupted) file — manifested as "Processing
  abandoned" on YouTube Studio. Fixed to track byte offsets and total size
  correctly; confirmed via real uploads (308 Resume Incomplete → final 200).
- **Key gotcha:** YouTube Data API scopes are narrow and task-specific —
  `youtube.upload` ≠ `yt-analytics.readonly` ≠ `youtube`/`youtube.force-ssl`
  (needed for delete). Each new capability needs the refresh token
  regenerated with the added scope via OAuth Playground; existing scopes
  are not additive across separately-issued tokens.

### Phase 2 — YouTube Pipeline, Publishing Workflow, Scheduler
- `PipelineRun` model: one row per execution, tracks
  `status`/`current_stage`/`failed_stage`/`error_message` and links to the
  script/video/upload it produced.
- `Upload.publish_status` (DRAFT → APPROVED → SCHEDULED → REJECTED) is a
  **separate** enum from `Upload.status` (PENDING/UPLOADING/PUBLISHED/
  FAILED/SCHEDULED) — editorial state vs. technical upload state, on
  purpose, so upload_agent/analytics_agent's existing logic never had to
  change.
- Publish Scheduler (`app/scheduler/scheduler.py`): polls every N minutes
  for `publish_status=SCHEDULED AND scheduled_at<=now()`, re-validates
  state immediately before firing the real upload (prevents double-publish
  races), fires `UploadAgentService.run_upload_for_video()`.
- Auto-publish flow: `quality_min_score=85` gate → auto-approve → schedule
  with a configurable safety delay (`pipeline_publish_delay_minutes`)
  before actually publishing — the only manual-intervention window in a
  fully autonomous flow.
- **Recurring bug pattern to know about:** Alembic migrations that create
  a new enum type must let `op.create_table()` own the type creation — a
  separate standalone `enum.create()` call *and* referencing that enum
  inside `create_table()` causes `DuplicateObjectError`. Always follow the
  pattern already used for `uploads.publish_status` / `pipeline_runs.status`.

### Phase 3 — Retry Manager
- Two independent retry surfaces, not one:
  - **Surface A** — pipeline stage failures inside `PipelineAgentService`
  - **Surface B** — the Scheduler's actual upload call
- Shared classification (`app/utils/retry.py`,
  `is_retryable_error()`): network/timeout/5xx → retry with exponential
  backoff; `QualityError`/`NotFoundError`/4xx auth errors → fail
  immediately, no retry.
- Idempotency: retrying the upload-record-creation stage checks
  `pipeline_run.upload_id` first (skip if already populated); retrying the
  Scheduler's upload call checks `youtube_video_id`/`status==PUBLISHED`
  first (never double-uploads even if a prior attempt's response was lost).
  Every retry starts a **brand-new** resumable upload session — never
  resumes a stale one.
- **Real bug caught by self-review, not manual testing:** a `NameError`
  from a missing import was being silently swallowed by a broad
  `except` in the scheduler tick — would have caused every scheduled video
  to silently never publish, with zero visible error.

### Phase 4 — RAG Research (optional, off by default)
- `RAG_RESEARCH_ENABLED=false` by default. Search → Crawl → Extract →
  Embed → Store, then retrieval-augmented context gets injected into the
  script agent's prompt — additive only, never required.
- If any RAG step fails, falls back to generating the script *without*
  research context — verified via an explicit fail-safe integration test,
  not just code inspection.
- Vector store: FAISS + SQLite, with a process-wide singleton
  (`get_vector_store()`) — an early version gave each request its own
  `VectorStore`/lock, which would have corrupted the shared index file
  under concurrent requests; caught and fixed before ever running live.

### Phase 5 — Dashboard
- FastAPI native WebSocket (`/ws/pipeline`) broadcasting pipeline/upload/
  scheduler-tick events to an in-process `ConnectionManager` — no Redis,
  appropriate for this single-process scale.
- HTMX dashboard (`/dashboard`): live pipeline runs list, upload/publishing
  queue with approve/reject, "Recently Uploaded to YouTube" panel with
  Watch + **Delete** actions, Channel Automation panel with Start/Pause/
  Delete, scheduler status, trigger-new-run form.
- Prometheus `/metrics`: pipeline run counts by status, scheduler tick
  results, upload retry counts, HTTP request latency.
- **Security:** `/dashboard` and `/metrics` are protected by a shared-secret
  `DASHBOARD_AUTH_TOKEN` (Bearer or Basic auth accepted) — added after
  initially shipping both routes fully open. No other routes have auth;
  this is intentionally scoped, not a general auth system.
- **Delete Video feature:** deletes a video from YouTube AND the local
  dashboard, in that order (YouTube first — if that fails, the local
  record is kept so nothing is silently lost). Handles the edge case where
  a video was already deleted directly on YouTube (`404 videoNotFound`) by
  showing a confirmation dialog ("remove from dashboard only?") instead of
  crashing with a 500.
- **Real bug found and fixed post-launch:** deleting an `Upload` with a
  linked `Analytics` row violated a `NOT NULL` constraint on
  `analytics.upload_id` (SQLAlchemy tried to null out the FK on delete).
  Fixed by explicitly deleting linked `Analytics` rows first, in the same
  transaction, inside `UploadRepository.delete_upload()`.

### Final Phase — Channel Automation (fully autonomous, indefinite operation)
- New `ChannelAutomation` model (one row per channel):
  `automation_status` (STOPPED/RUNNING/PAUSED), `started_at`, `paused_at`,
  `cumulative_active_days` (freezes during Pause — does NOT count paused
  time), `last_run_date`, `last_long_pipeline_date`,
  `long_video_interval_days`.
- Content strategy: Days 1–15 → Shorts only, every day. Day 16+ → Shorts
  every day + a Long video every `long_video_interval_days` (default 2).
- **Second, independent scheduler** (`app/scheduler/automation_scheduler.py`)
  — deliberately NOT merged into the existing Publish Scheduler, since
  their responsibilities are different (this one *creates* PipelineRuns;
  the other only *publishes* already-scheduled uploads).
- Safety properties, each explicitly designed and tested:
  - **Overlap protection** — never creates a second PipelineRun for a
    channel while one is already RUNNING.
  - **Missed-day policy** — if the app was offline for N days, creates AT
    MOST one run per channel on the next tick; never backfills.
  - **Per-channel timezone** — "today" is computed in the channel's own
    timezone, not server time.
  - **Concurrency limit** — `asyncio.Semaphore` bounded by
    `AUTOMATION_MAX_CONCURRENT_CHANNELS` (default 1, matches this
    project's 2-physical-core hardware).
  - **Topic exclusion** — a topic that fails the Quality Gate is marked
    excluded from future automatic selection (reuses `TopicStatus`, no new
    column); automation itself never pauses because of one bad topic.
  - **Soft delete** — "Delete" archives a channel (stops automation, hides
    it from the dashboard) but never deletes historical Topics/Scripts/
    Videos/Uploads/Analytics. A true hard-delete is a deliberately separate,
    unbuilt admin operation.
- **Architectural bug found and fixed in the same phase:** `init_db()` was
  calling `Base.metadata.create_all()` unconditionally on every app
  startup — silently creating tables outside Alembic's tracking. This
  meant Alembic migrations were never actually the enforced source of
  truth for schema changes. Fixed by removing the unconditional call and
  gating any dev-convenience auto-create behind an explicit,
  default-`false` config flag.

### ImageProvider — AI-Generated Scene Backgrounds
- Replaces solid-color text cards with real images per scene.
- Provider chain: Pollinations AI (free, no key) → Hugging Face Inference
  API (only if `HF_API_TOKEN` set) → `None` (renderer falls back to the
  original solid-color card for that scene only — never fails the whole
  render).
- Disk-cached by `(script_id, prompt hash)`; concurrent requests for the
  same prompt are protected by a per-key `asyncio.Lock` with atomic
  temp-file-then-rename writes (an early version allowed two concurrent
  requests to double-fetch the same image — caught and fixed before this
  ever ran live, same category as the Phase 4 VectorStore singleton bug).
- **Known live issue (as of July 7, 2026):** Pollinations' free public API
  rate-limits under even light concurrent load (`Semaphore(3)` was enough
  to trigger `429 Too Many Requests` on ~2 of 3 scenes in one real run).
  The fallback works correctly (renders text cards for those scenes,
  pipeline completes successfully) — this is a quality-of-service gap, not
  a correctness bug. Planned fix: lower concurrency + add 429-aware retry
  with backoff, reusing the existing retry classification pattern.

### In Progress — Metadata & SEO Scoring
- Adding a scoring gate (title length/keyword, description CTA, ≥7
  hashtags, 20–28 tags) alongside the existing Quality Gate, reusing the
  same pass/fail → `TopicStatus.REJECTED` → continue-automation pattern
  already proven for quality failures. Scope TBD pending confirmation of
  whether this scores *existing* `Script.seo_title`/`seo_description`/
  `seo_tags` fields or needs new generation logic.

### Deferred (not yet built)
- **Self-healing pipeline** — detect a missing/failed artifact (e.g. no
  Voice record) and re-trigger that specific agent, rather than silently
  falling back or failing the whole run. Deliberately kept separate from
  SEO scoring — this is a different architecture (per-artifact health
  checks, not stage-level retry) and deserves its own design pass.
- **Peak-time-of-day scheduling** — publish at optimal engagement hours,
  not just a fixed delay after approval.
- **Formal Phase 6 integration/e2e test suite** — currently covered
  indirectly by extensive real end-to-end manual verification (real
  uploads, real deletes, real scheduler ticks) rather than a dedicated
  formal suite.

---

## 4. How to Run This Project Locally

### 4.1 Prerequisites
- Python 3.11
- PostgreSQL running locally (or a reachable instance)
- [Ollama](https://ollama.com) installed and running locally
- Git

### 4.2 First-Time Setup

```bash
# 1. Clone the repo
git clone <your-repo-url>
cd autonomous-youtube-studio

# 2. Create and activate a virtual environment (recommended)
python -m venv venv
source venv/bin/activate        # Linux/Mac
venv\Scripts\activate           # Windows

# 3. Install dependencies
pip install -r requirements.txt
```

### 4.3 Environment Variables

Create a `.env` file in the project root with at least:

```dotenv
# Database
DATABASE_URL=postgresql+asyncpg://<user>:<password>@localhost:5432/<dbname>

# LLM (Ollama, local, free)
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5-script:latest
OLLAMA_NUM_CTX_LARGE=8192
OLLAMA_NUM_CTX_SMALL=4096
OLLAMA_NUM_THREADS=4

# YouTube (OAuth2 — see section 4.6 for how to obtain these)
YOUTUBE_API_KEY=...
YOUTUBE_CLIENT_ID=...
YOUTUBE_CLIENT_SECRET=...
YOUTUBE_REFRESH_TOKEN=...
YOUTUBE_REDIRECT_URI=...

# Dashboard auth (any long random string — generate with:
#   python -c "import secrets; print(secrets.token_urlsafe(32))"
DASHBOARD_AUTH_TOKEN=<your-generated-token>

# Optional — RAG Research (off by default, safe to leave unset)
RAG_RESEARCH_ENABLED=false

# Optional — dev convenience only, keep false in normal use
DEV_AUTO_CREATE_TABLES=false

# Optional — Channel Automation tuning (sensible defaults exist)
AUTOMATION_CHECK_INTERVAL_MINUTES=60
AUTOMATION_MAX_CONCURRENT_CHANNELS=1

# Optional — ImageProvider
IMAGE_PROVIDER=pollinations
HF_API_TOKEN=            # only if you want the HuggingFace fallback
```

### 4.4 Database Setup

```bash
# Confirm Alembic's current state
alembic current

# Apply all migrations
alembic upgrade head

# Confirm it worked
alembic current
# should print the latest revision, marked (head)
```

**If you ever see a `DuplicateObjectError` on an enum type during a
migration:** this is a known pattern (see Phase 2 notes above) — it means
a migration is calling `.create()` on an enum type *and* referencing that
same type inside `op.create_table()`. The fix is to remove the standalone
`.create()` call and let `create_table()` own the type creation.

### 4.5 Running the App

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Watch the startup logs for these lines to confirm everything initialized:
```
Database initialized  (schema_mode="alembic-only")
LLM provider initialized  (provider=ollama)
Publish scheduler started.
Daily automation scheduler started.
```

### 4.6 Getting YouTube OAuth2 Credentials

1. Create a project in [Google Cloud Console](https://console.cloud.google.com),
   enable the **YouTube Data API v3** and **YouTube Analytics API**.
2. Create OAuth2 credentials (Client ID + Secret) for a Desktop app.
3. Use [Google's OAuth Playground](https://developers.google.com/oauthplayground):
   - Gear icon → "Use your own OAuth credentials" → enter your Client
     ID/Secret.
   - Select scopes: at minimum `youtube.upload`. Add
     `yt-analytics.readonly` if you want Analytics. Add `youtube` or
     `youtube.force-ssl` if you want the Delete Video feature to work
     (broader scope — read the tradeoff note in the Dashboard delete
     feature section above before enabling this).
   - Authorize, exchange the code for tokens, copy the refresh token into
     `YOUTUBE_REFRESH_TOKEN`.
4. **Important:** a refresh token's scopes are fixed at the moment it's
   issued — if you need a new scope later, you must regenerate the token
   with the old scopes *plus* the new one, not just add the new scope
   alone.

### 4.7 Accessing the Dashboard

Since `/dashboard` requires the `DASHBOARD_AUTH_TOKEN`, plain browser
navigation to `http://localhost:8000/dashboard` will return `401` (browsers
don't send custom headers on address-bar navigation). Two options:

- **curl** (quick checks): `curl -H "Authorization: Bearer <token>" http://localhost:8000/dashboard`
- **Browser, for actually clicking buttons:** install a header-injector
  extension (e.g. ModHeader), set `Authorization: Bearer <token>` as a
  request header, then visit `http://localhost:8000/dashboard` normally.

### 4.8 Running Tests

```bash
pytest -v
```

As of the last full local run: **859 passed, 0 failed** (a small number of
harmless warnings — a MoviePy/imageio deprecation notice and a
pre-existing unawaited-coroutine warning in one mocked test — neither
indicates a real problem).

### 4.9 Trying Channel Automation for the First Time

See the step-by-step dry-run checklist used originally (temporarily lower
`AUTOMATION_CHECK_INTERVAL_MINUTES` to something like 5 for faster
feedback, click Start on one real channel via the dashboard, watch the
logs and query `channel_automations`/`pipeline_runs` directly to confirm
each safety property — overlap protection, missed-day skip, day-16
transition, Pause freezing `cumulative_active_days`). Remember to set the
interval back to a production-appropriate value afterward.

---

## 5. Key Design Principles Followed Throughout

1. **Repository pattern** — no raw SQL in services, only repository
   methods.
2. **Async everywhere** — all DB operations use `AsyncSession`/`await`.
3. **Reuse before rebuild** — every new phase started by checking whether
   an existing mechanism (retry classification, topic exclusion, the
   Quality Gate pattern) could be extended instead of building a parallel
   system. This discipline avoided at least three would-be duplicate
   systems (a second retry manager, a second topic-tracking column, a
   second "Task Manager" model that would have shadowed `PipelineRun`).
4. **Fail-safe, not fail-fast, for optional features** — RAG, ImageProvider,
   and SEO scoring are all designed so a failure degrades gracefully
   (skip the feature, log a warning, continue) rather than halting the
   whole pipeline.
5. **Never trust a summary — verify the real thing.** Nearly every phase
   surfaced at least one bug that unit tests alone didn't catch (the
   Whisper timing drift, the chunked-upload corruption, the VectorStore
   locking bug, the `create_all()` schema-drift bug, the Analytics FK
   constraint) — all were caught either by real end-to-end runs or by
   independent local verification after an AI coding session claimed
   something was "done."
6. **Schema changes always confirmed before running** — every migration
   was shown and approved before being applied, and the Phase 2 enum
   DuplicateObjectError taught a specific, reusable lesson (let
   `create_table()` own enum creation) that was correctly applied in every
   subsequent migration.

---

## 6. Where to Get Help / What to Check First When Something Breaks

- **Pipeline run stuck or failed?** Check `pipeline_runs.failed_stage` and
  `error_message` directly in the DB, and check the server logs around
  that timestamp.
- **Video not publishing?** Check `uploads.publish_status` and
  `scheduled_at` — the Publish Scheduler only picks up rows where
  `publish_status=SCHEDULED AND scheduled_at<=now()`.
- **Channel automation not creating daily runs?** Check
  `channel_automations.last_run_date` (already ran today?) and
  `automation_status` (must be RUNNING, not PAUSED/STOPPED).
- **A migration fails with `DuplicateObjectError`?** See section 4.4 above
  — it's almost always the enum-creation double-ownership pattern.
- **Dashboard returns 401?** You're missing the `Authorization` header —
  see section 4.7.
