# Automatic Step-by-Step Guide — Autonomous YouTube Studio

This guide shows how to run the studio on **full autopilot** — it picks topics, generates videos, and uploads to YouTube without any manual intervention.

---

## How Automation Works

The system has two schedulers running in the background:

| Scheduler | Interval | What it does |
|-----------|----------|-------------|
| **Publish Scheduler** | Every 5 min | Uploads SCHEDULED videos to YouTube |
| **Daily Automation Scheduler** | Every 60 min | Picks topics and triggers pipeline runs for active channels |

---

## Step 1 — Create a Channel (Once)

```bash
curl -X POST "http://localhost:5000/api/v1/channels" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "AI Daily Tips",
    "niche": "artificial intelligence",
    "content_type": "both",
    "description": "Daily short and long AI videos",
    "upload_schedule": "daily"
  }'
```

---

## Step 2 — Seed Topics (Recommended)

Add a batch of topics so the automation scheduler has content to pick from:

```bash
# Short topic
curl -X POST "http://localhost:5000/api/v1/topics" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"channel_id":"CHANNEL_ID","title":"What is GPT-5?","content_type":"short","source":"manual"}'

# Long topic
curl -X POST "http://localhost:5000/api/v1/topics" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"channel_id":"CHANNEL_ID","title":"Complete Guide to Prompt Engineering 2026","content_type":"long","source":"manual"}'
```

The scheduler picks `pending` topics and marks them `published` after completion so they are never duplicated.

---

## Step 3 — Enable Channel Automation

**Via Dashboard:**
1. Go to **Channel Automation** panel
2. Find your channel and click **[Start]**
3. Status changes to `RUNNING` ✅

**Via API:**
```bash
curl -X POST "http://localhost:5000/api/v1/channels/CHANNEL_ID/automation/start" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## Step 4 — Enable Auto-Upload (Optional)

By default videos queue for manual approval. To fully automate uploads:

```bash
# Add to Replit env vars:
AUTO_UPLOAD=true
```

With this on, every video that passes quality and SEO gates is automatically approved and uploaded on schedule.

---

## Step 5 — Configure Notification Alerts

Get notified when a video is done or fails:

```bash
# Email (Gmail)
NOTIFICATION_EMAIL_ENABLED=true
NOTIFICATION_EMAIL_FROM=you@gmail.com
NOTIFICATION_EMAIL_PASSWORD=your-app-password   # Gmail App Password, not account password
NOTIFICATION_EMAIL_TO=you@gmail.com
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587

# Slack
NOTIFICATION_SLACK_ENABLED=true
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...

# Discord
NOTIFICATION_DISCORD_ENABLED=true
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# Telegram
NOTIFICATION_TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=123456:ABC-...
TELEGRAM_CHAT_ID=-100123456789
```

---

## Step 6 — The Automatic Flow (What Happens Daily)

```
Every 60 minutes:
  Daily Automation Scheduler wakes up
  → Finds all RUNNING channels
  → For each channel, picks a "pending" topic
  → Creates a PipelineRun (script_type based on channel's content_type)
  → Pipeline executes: script → quality → seo → voice → video → upload record

Every 5 minutes:
  Publish Scheduler wakes up
  → Finds all uploads with status=SCHEDULED and scheduled_at <= now()
  → Uploads .mp4 to YouTube via resumable upload API
  → Marks upload PUBLISHED
  → Sends notification (email/Slack/Discord/Telegram)
  → (Optional) Posts Reel to Instagram
```

---

## Step 7 — Monitor the Automation

**Dashboard panels to watch:**
- **Scheduler Status** — shows last tick time and due/succeeded/failed counts
- **Pipeline Runs** — shows all active and recent runs
- **Upload Queue** — shows pending → scheduled → published progression
- **Recently Uploaded to YouTube** — live list of published videos with links

**API polling:**
```bash
# List all pipeline runs
curl "http://localhost:5000/api/v1/pipeline" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Check scheduler status
curl "http://localhost:5000/api/v1/pipeline/scheduler-status" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## Automation Schedule Reference

| Setting | Default | Description |
|---------|---------|-------------|
| `AUTOMATION_CHECK_INTERVAL_MINUTES` | 60 | How often automation ticks |
| `AUTOMATION_MAX_CONCURRENT_CHANNELS` | 1 | Channels processed per tick |
| `AUTOMATION_SHORTS_ONLY_DAYS` | 15 | Days before switching to shorts-only mode |
| `SCHEDULER_INTERVAL_MINUTES` | 5 | How often publish scheduler runs |
| `AUTO_UPLOAD` | false | Auto-approve and upload without manual review |

---

## Pause / Resume Automation

```bash
# Pause a channel
curl -X POST "http://localhost:5000/api/v1/channels/CHANNEL_ID/automation/pause" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Resume
curl -X POST "http://localhost:5000/api/v1/channels/CHANNEL_ID/automation/start" \
  -H "Authorization: Bearer YOUR_TOKEN"
```
