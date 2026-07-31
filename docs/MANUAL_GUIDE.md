# Manual Step-by-Step Guide — Autonomous YouTube Studio

This guide walks you through creating and publishing a video **manually** using the dashboard.

---

## Prerequisites

Ensure the app is running at `http://localhost:5000` (or your Replit preview URL) and you have logged in with your `DASHBOARD_AUTH_TOKEN`.

---

## Step 1 — Log In

1. Open the app URL in your browser
2. You will be redirected to `/login`
3. Enter your `DASHBOARD_AUTH_TOKEN` and click **Sign In**
4. You will land on the Ops Dashboard

---

## Step 2 — Create a Channel (First Time Only)

A **Channel** represents a YouTube channel persona with a niche and upload schedule.

**Via Dashboard:**
1. Go to the **Channel Automation** panel at the bottom
2. Click **+ Add Channel** (if available)

**Via API (curl):**
```bash
curl -X POST "http://localhost:5000/api/v1/channels" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Tech Channel",
    "niche": "technology",
    "content_type": "both",
    "description": "AI and tech tips"
  }'
```
Save the returned `id` — that is your `CHANNEL_ID`.

---

## Step 3 — Add a Topic

A **Topic** is the video idea / title.

**Via API:**
```bash
curl -X POST "http://localhost:5000/api/v1/topics" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "channel_id": "CHANNEL_ID",
    "title": "Top 5 AI Tools You Must Try in 2026",
    "content_type": "short",
    "source": "manual"
  }'
```
Use `"content_type": "long"` for a full-length video (5–15 min).  
Save the returned `id` — that is your `TOPIC_ID`.

---

## Step 4 — Trigger a Pipeline Run

**Via Dashboard:**
1. In the **Trigger New Pipeline Run** panel at the top:
   - Select your Channel
   - Select your Topic
   - Choose **Short** or **Long** script type
   - Click **Run Pipeline**

**Via API:**
```bash
curl -X POST "http://localhost:5000/api/v1/pipeline/run" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "topic_id": "TOPIC_ID",
    "channel_id": "CHANNEL_ID",
    "script_type": "short"
  }'
```

---

## Step 5 — Watch Pipeline Progress

In the **Pipeline Runs** panel, you will see your run with stage indicators:

| Stage | What's happening |
|-------|-----------------|
| `script` | Groq LLM writing the video script |
| `quality` | AI scoring the script (must pass ≥70) |
| `seo` | Rule-based SEO check (must pass ≥60) |
| `voice` | gTTS generating spoken audio (MP3) |
| `video` | MoviePy rendering scenes + Ken Burns effect |
| `upload` | Creating the upload record (scheduled for YouTube) |
| `analytics` | Deferred 24h (YouTube analytics lag) |
| `COMPLETE` ✅ | Video is ready and queued for upload |

**Short video:** ~3–8 minutes total  
**Long video:** ~15–30 minutes total (36+ scenes with images)

---

## Step 6 — Approve the Upload

Once the pipeline reaches **COMPLETE**, the video appears in the **Upload Queue** panel.

- Status will be `SCHEDULED` (ready for upload)
- If `AUTO_UPLOAD=false` (default), click **Approve** to confirm
- If `AUTO_UPLOAD=true`, it uploads automatically at the scheduled time

---

## Step 7 — YouTube Upload (Scheduler)

The publish scheduler runs every **5 minutes**. It picks up all `SCHEDULED` uploads whose time has passed and:

1. Uploads the `.mp4` file to YouTube via the resumable upload API
2. Sets privacy to `public` (configurable)
3. Updates status to `PUBLISHED`
4. Sends a notification (if configured)

You will see the uploaded video appear in **Recently Uploaded to YouTube** with a clickable `▶ Watch` link.

---

## Step 8 — Verify on YouTube

Click the **▶ Watch** link in the dashboard to open the video on YouTube.

---

## Optional: Check Logs

```bash
# View live server logs in Replit terminal
# Or check via:
curl http://localhost:5000/health
```

---

## Useful API Endpoints Reference

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/health` | App health check |
| `GET` | `/api/v1/channels` | List all channels |
| `POST` | `/api/v1/channels` | Create a channel |
| `POST` | `/api/v1/topics` | Create a topic |
| `POST` | `/api/v1/pipeline/run` | Trigger pipeline |
| `GET` | `/api/v1/pipeline/{id}` | Check pipeline status |
| `GET` | `/api/v1/uploads` | List uploads |
| `GET` | `/dashboard` | Web dashboard |
