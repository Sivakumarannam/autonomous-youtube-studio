# 🚀 Quick Start Guide - Dashboard & Features

## Starting the Application

### Step 1: Navigate to Project
```bash
cd e:\autonomous-youtube-studio\autonomous-youtube-studio
```

### Step 2: Start FastAPI
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Step 3: Verify Startup
Look for these logs in the terminal:
```
Starting Autonomous YouTube Studio
Database ready
LLM provider initialized
Publish scheduler started.           ← ✅ Key line!
Daily automation scheduler started.
```

If you see "Publish scheduler started" - everything is working! 🎉

### Step 4: Open Dashboard
Open your browser and go to:
```
http://localhost:8000/dashboard
```

---

## Dashboard Layout

```
┌─────────────────────────────────────────────────────────────┐
│ Autonomous YouTube Studio — Ops Dashboard        [● live]  │
└─────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ Trigger New Pipeline Run                             [FULL]  │
│ [Channel ▼] [Topic ▼] [Script Type ▼] [Run Pipeline]       │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ Scheduler Status                                    [FULL]   │
│ Last tick: 2 seconds ago                                     │
│ Due count: 0 | Succeeded: 15 | Failed: 0                    │
└──────────────────────────────────────────────────────────────┘

┌─────────────────────────────┐ ┌──────────────────────────────┐
│ Pipeline Runs               │ │ Recently Uploaded to YouTube │
│ • Run 1: STAGE_5   50%     │ │ Videos Published: 3          │
│ • Run 2: Complete          │ │ • ✓ "Top 10 AI Tools 2026"  │
│ • Run 3: STAGE_2   20%     │ │   M1Qb68du5Cg • 2 min ago   │
│                            │ │   [▶ Watch]                  │
│                            │ │                              │
│                            │ │ • ✓ "YouTube SEO Tips"      │
│                            │ │   _zeXNFsvFig • 2 hours ago │
│                            │ │   [▶ Watch]                  │
│                            │ │                              │
│                            │ │ • ✓ "Viral Content Ideas"   │
│                            │ │   ntymlxQ6uuI • 1 day ago   │
│                            │ │   [▶ Watch]                  │
└─────────────────────────────┘ └──────────────────────────────┘

┌────────────────────┐ ┌───────────────────────────────────────┐
│ Upload Queue       │ │ Channel Automation                    │
│ • PENDING: 2       │ │ • Channel 1 [RUNNING] [Pause] [Delete]
│ • SCHEDULED: 1     │ │ • Channel 2 [PAUSED] [Start] [Delete] │
│ • PUBLISHED: 12    │ │ • Channel 3 [PAUSED] [Start] [Delete] │
└────────────────────┘ └───────────────────────────────────────┘
```

---

## Key Features

### 1️⃣ Create & Run Pipeline

**Flow:**
1. Select channel from "Trigger New Pipeline Run"
2. Select topic
3. Choose script type (short/long)
4. Click "Run Pipeline"
5. Watch it progress through stages in "Pipeline Runs" panel

**Status Indicators:**
- 🟡 PENDING = Waiting to start
- 🟡 STAGE_1 = Topic selection
- 🟡 STAGE_2 = Script generation
- 🟡 STAGE_3 = Video rendering
- 🟡 STAGE_4 = Voice generation
- 🟡 STAGE_5 = Quality check
- 🟢 COMPLETE = Ready for upload

**Timeline:** Usually 5-10 minutes per video

---

### 2️⃣ Check Upload Queue

**What You See:**
- Videos waiting to be uploaded
- Publishing status (APPROVED, REJECTED, SCHEDULED)
- Scheduled upload time
- Approve/Reject buttons

**Statuses:**
- 🟡 SCHEDULED = Queued for YouTube upload
- 🟡 UPLOADING = Currently uploading to YouTube
- 🟢 PUBLISHED = Successfully on YouTube

---

### 3️⃣ View Recently Uploaded Videos ⭐ NEW!

**What You See:**
- List of successfully published videos
- YouTube video IDs
- Exact timestamp of publication
- Human-readable time (e.g., "2 minutes ago")
- One-click "Watch on YouTube" links

**Auto-Updates:**
- Real-time via WebSocket when videos publish
- Polling every 20 seconds as fallback
- No page refresh needed

**Example:**
```
Recently Uploaded to YouTube
Videos Published: 3

✓ "Top 10 AI Tools 2026"
  M1Qb68du5Cg • PUBLISHED
  Jul 06, 18:30 • 2 minutes ago
  [▶ Watch on YouTube]
```

---

### 4️⃣ Manage Channel Automation

**Available Actions:**
- **START**: Immediately queue channel for processing
  - Clears "already ran today" guard
  - Processes on next scheduler tick (5 min max)
  
- **PAUSE**: Stop automation until you re-enable
  - Scheduler will skip this channel
  - Can resume anytime
  
- **DELETE**: Archive channel and stop forever
  - Removes from scheduler
  - Cannot be undone

**Status Indicators:**
- 🟢 RUNNING = Actively being scheduled
- 🟡 PAUSED = Waiting for manual restart
- 🔘 ARCHIVED = Deleted/inactive

---

### 5️⃣ Monitor Scheduler Status

**What It Shows:**
- Last tick timestamp (seconds ago)
- Due uploads found
- Successfully uploaded count
- Failed count

**Interpretation:**
- If "Last tick: 2 seconds ago" → Scheduler is running ✅
- If "Due count: 0" → All uploads already published
- If "Succeeded: 15" → 15 videos have uploaded successfully

---

## Common Workflows

### Workflow 1: Create Your First Video

```
1. Make sure channel exists
2. Make sure at least one topic exists
3. Click "Run Pipeline" on dashboard
4. Select channel and topic
5. Click "Run Pipeline"
6. Watch "Pipeline Runs" panel
   └─ Status updates from PENDING → STAGE_1 → ... → COMPLETE
7. Check "Upload Queue" - video appears with SCHEDULED status
8. Wait ~5 minutes
9. Watch "Recently Uploaded to YouTube" panel
   └─ Video appears with animation ✨
10. Click "▶ Watch on YouTube" to view your video!
```

**Time:** 10-15 minutes start to YouTube

---

### Workflow 2: Automate Channel

```
1. Create channel (via API)
2. Create topics (via API)
3. Go to dashboard
4. Find your channel in "Channel Automation"
5. Click [START]
   └─ Status changes to RUNNING
6. Scheduler automatically runs every 5 minutes
   └─ Creates pipeline runs
   └─ Generates videos
   └─ Publishes to YouTube
7. Watch "Recently Uploaded to YouTube" fill up automatically!
```

**Result:** Hands-off video publishing! 🤖

---

### Workflow 3: Troubleshoot a Problem

```
1. Video not uploading to YouTube?
   └─ Check: Is the app running?
   └─ Check: Does scheduler show "Last tick: X seconds ago"?
   └─ Run: python inspect_uploads.py
      └─ See if uploads are scheduled
      └─ See if scheduled_at time has passed

2. Upload stuck in SCHEDULED state?
   └─ Check: YouTube credentials configured?
   └─ Run: python test_manual_upload.py
      └─ Try uploading manually
      └─ See if error appears

3. Channel automation not running?
   └─ Check: Is channel status RUNNING?
   └─ Check: Has it already run today?
   └─ Try: Click [START] to reset it
   └─ Check: "Pipeline Runs" panel for new run

4. Need to see what scheduler is doing?
   └─ Run app with: --log-level=debug
   └─ Watch console output
   └─ Every decision gets logged
```

---

## Real-Time Features

### WebSocket Live Updates

The dashboard receives live updates automatically:

**Events Broadcast:**
- `pipeline-update` → Pipeline run status changed
- `upload-update` → Upload status changed
- `scheduler-update` → Scheduler ticked

**Visible Effects:**
- "Recently Uploaded to YouTube" refreshes immediately
- "Pipeline Runs" updates as stages complete
- "Upload Queue" shows status changes

**Status Indicator (top-right):**
- 🟢 `live` = Connected to WebSocket
- 🔴 `disconnected` = Connection lost (auto-reconnects)

---

## Dashboard Keyboard Shortcuts

| Action | Shortcut |
|--------|----------|
| Refresh page | F5 |
| Open dev tools | F12 |
| Search | Ctrl+F |
| - | - |
| *(Note: Dashboard is mostly mouse-driven for HTMX integration)* | |

---

## Tips & Tricks

### Tip 1: Use Relative Time
"2m ago" is shown automatically. It updates as you watch! No need to refresh.

### Tip 2: Direct YouTube Links
Click any "[▶ Watch]" button to open the video directly. Opens in new tab.

### Tip 3: Copy Video IDs
Hover over video ID to see full ID. Click to copy (not yet implemented, but shows full ID in tooltip).

### Tip 4: Monitor Multiple Channels
Run multiple channels on automation. Scheduler processes one at a time (queue management).

### Tip 5: Check Logs
App logs show every scheduler tick. Good for debugging automation issues.

---

## Monitoring Dashboard Health

### ✅ Green Flags (Everything Working)
- [ ] "live" indicator in top-right (green)
- [ ] Videos appear in "Recently Uploaded" within 5-15 minutes
- [ ] Pipeline Runs shows COMPLETE status
- [ ] Scheduler Status shows "Succeeded: N" increasing
- [ ] Upload Queue has uploads moving through stages

### ⚠️ Yellow Flags (Investigate)
- [ ] "disconnected" (WebSocket issue - wait for auto-reconnect)
- [ ] Videos SCHEDULED for >5 min but not publishing (check scheduler logs)
- [ ] Upload Queue shows ERROR status (check error_message)
- [ ] Pipeline Run stuck in STAGE_X for 15+ min (potential hang)

### 🔴 Red Flags (Critical)
- [ ] App crashed/not running
- [ ] Database connection error
- [ ] YouTube credentials invalid
- [ ] Video file missing or corrupt

---

## Performance Metrics

| Metric | Expected | Status |
|--------|----------|--------|
| Dashboard load | < 1 second | ✅ Fast |
| Video upload to YouTube | 5-15 minutes | ✅ Automated |
| Scheduler tick interval | Every 5 minutes | ✅ Regular |
| WebSocket updates | Real-time | ✅ Instant |
| Panel refreshes | < 500ms | ✅ Smooth |
| Animation duration | 300-800ms | ✅ Polished |

---

## Get Help

### Check These First:
1. Is the app running? (see startup logs)
2. Is scheduler running? (run `python check_scheduler_status.py`)
3. Do logs show errors? (watch console output)

### Debug Scripts:
```bash
# Check if scheduler is ticking
python check_scheduler_status.py

# Inspect upload database state
python inspect_uploads.py

# Test upload service manually
python test_manual_upload.py
```

### Read Documentation:
- `CHANGELOG_2026_07_07.md` - Technical changes
- `BEFORE_AFTER_COMPARISON.md` - Problem/solution overview
- `CODE_CHANGES_TECHNICAL.md` - Code-level details

---

## What's Next?

Future enhancements planned:
- [ ] Analytics integration
- [ ] Thumbnail optimization
- [ ] A/B testing different titles
- [ ] Content calendar view
- [ ] Bulk operations
- [ ] Export video data

---

## Summary

🎬 **Your video pipeline is now fully automated and beautiful!**

✅ Create videos via dashboard  
✅ Scheduler publishes automatically  
✅ Dashboard shows results in real-time  
✅ One-click YouTube access  
✅ Fully transparent logging  

**Now go create amazing content!** 🚀

---

*For more details, see other documentation files in the project root.*
