# Troubleshooting Guide — Autonomous YouTube Studio

Common errors, their causes, and how to fix them.

---

## 🔑 Authentication Errors

### `{"detail": "Not authenticated."}`
**Cause:** Missing or wrong `DASHBOARD_AUTH_TOKEN`.  
**Fix:**
- Check the token is set in Replit Secrets
- Use the `/login` page in the browser (enter the token)
- For API calls: add `-H "Authorization: Bearer YOUR_TOKEN"` to curl

---

### `Dashboard auth is not configured`
**Cause:** `DASHBOARD_AUTH_TOKEN` secret is empty.  
**Fix:** Add it in Replit Secrets → restart the workflow.

---

## 🤖 LLM / Groq Errors

### `429 Too Many Requests — rate limited`
**Cause:** Groq free tier limit hit (12,000 tokens/minute, 14,400 requests/day).  
**Fix:** The app auto-retries with backoff. Wait 15–30 seconds. For heavy use, upgrade to Groq paid or space out pipeline runs.

### `groq_rate_limited — tpm_info: Limit 12000`
**Cause:** Token-per-minute limit exceeded when running multiple pipelines at once.  
**Fix:** Run one pipeline at a time. Short pipelines use fewer tokens than long.

### `LLM provider 'groq' not configured`
**Cause:** `GROQ_API_KEY` secret is missing.  
**Fix:** Add `GROQ_API_KEY` in Replit Secrets → restart.

### `Script failed quality gate (score below threshold)`
**Cause:** Groq scored the generated script below `QUALITY_MIN_SCORE` (default 70).  
**Fix:**
- Lower threshold: set `QUALITY_MIN_SCORE=60` in env vars
- Try a different topic title (more specific titles produce better scripts)
- Run the pipeline again (Groq responses vary)

### `Script failed SEO gate`
**Cause:** SEO score below `SEO_MIN_SCORE` (default 60).  
**Fix:** Set `SEO_MIN_SCORE=50` or use a keyword-rich topic title.

---

## 🎬 Video Rendering Errors

### `MoviePy / ImageMagick error`
**Cause:** ImageMagick not found or misconfigured.  
**Fix:** Verify ImageMagick is installed:
```bash
which convert   # should return a path
```
If missing, reinstall via Replit package manager.

### `libstdc++.so.6: cannot open shared object file`
**Cause:** Missing C++ standard library in the Replit Nix environment.  
**Fix:** The workflow command must include the `LD_LIBRARY_PATH` prefix:
```bash
LD_LIBRARY_PATH=/nix/store/04344hrpsbjzy7wq7vhwgcyarpbliz1l-gcc-14.2.1.20250322-lib/lib:$LD_LIBRARY_PATH python3 -m uvicorn app.main:app --host 0.0.0.0 --port 5000
```
This is already configured in the Replit workflow.

### `greenlet: ValueError — library required`
**Cause:** Same as above — missing `libstdc++.so.6`.  
**Fix:** Same as above.

### Video renders but has no audio
**Cause:** `VOICE_ENABLED=false` or voice stage failed silently.  
**Fix:** Set `VOICE_ENABLED=true` in env vars → restart → re-run pipeline.

### `gTTS error: Failed to connect`
**Cause:** No internet access or Google TTS is temporarily unavailable.  
**Fix:** Check network, retry. gTTS needs internet. If on Replit, it usually works.

---

## 🖼️ Image Generation Errors

### `HuggingFace failed — NameResolutionError`
**Cause:** `api-inference.huggingface.co` DNS not resolvable from Replit (network restriction).  
**Fix:** This is expected on Replit free tier. The system **automatically falls back** to Pollinations AI — no action needed.

### `Pollinations image fetch failed`
**Cause:** Pollinations API temporarily down or image prompt too long.  
**Fix:** The system falls back to a branded gradient with text overlay. Pipeline continues normally.

### All scenes show gradient backgrounds
**Cause:** Both HuggingFace and Pollinations failed for all scenes.  
**Fix:** Check Replit internet connectivity. Try running the pipeline again. Gradients are a valid fallback.

---

## 🎵 Music Errors

### `Jamendo request failed`
**Cause:** `JAMENDO_CLIENT_ID` is wrong or Jamendo API is down.  
**Fix:** Verify the client ID at https://devportal.jamendo.com/. Pipeline continues without music.

### No background music in video
**Cause:** No music files in `storage/music/` and Jamendo unavailable.  
**Fix:** Add MP3 files to `storage/music/` as a local fallback, or verify `JAMENDO_CLIENT_ID`.

---

## 📹 YouTube Upload Errors

### `YouTube upload failed — 401 Unauthorized`
**Cause:** Refresh token expired or credentials are wrong.  
**Fix:**
1. Verify `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN` in Replit Secrets
2. Re-generate the refresh token using the OAuth flow
3. Make sure YouTube Data API v3 is enabled in Google Cloud Console

### `YouTube upload failed — 403 quotaExceeded`
**Cause:** YouTube Data API daily quota (10,000 units) exhausted.  
**Fix:** Wait until midnight Pacific Time for quota reset. Uploads resume automatically next scheduler tick.

### `YouTube upload failed — 400 badRequest`
**Cause:** Video file corrupted, missing, or zero bytes.  
**Fix:**
- Check `storage/videos/` for the file
- Re-run the pipeline to regenerate the video
- Check available disk space

### `Video file not found for upload`
**Cause:** Video render completed but file was not saved, or path is wrong.  
**Fix:** Check `storage/videos/` directory. If empty, re-run the pipeline.

---

## 📲 Notification Errors

### Email not sending
**Cause:** Gmail App Password incorrect, or "Less secure apps" not enabled.  
**Fix:**
1. Use a **Gmail App Password** (not your Gmail login password)
2. Generate at: https://myaccount.google.com/apppasswords
3. Make sure 2FA is enabled on your Gmail account

### Slack webhook returns 404
**Cause:** Webhook URL revoked or channel deleted.  
**Fix:** Create a new Incoming Webhook in Slack App settings.

### Discord webhook returns 400
**Cause:** Embed payload malformed.  
**Fix:** Check `DISCORD_WEBHOOK_URL` is a full URL starting with `https://discord.com/api/webhooks/`

### Telegram: `{"ok":false,"error_code":400,"description":"Bad Request: chat not found"}`
**Cause:** `TELEGRAM_CHAT_ID` is wrong.  
**Fix:**
1. Send `/start` to your bot
2. Get your chat ID: `https://api.telegram.org/botYOUR_TOKEN/getUpdates`
3. Use the `chat.id` value (may be negative for groups: `-100123456789`)

---

## 🚀 Deployment Errors

### App crashes immediately on deploy
**Cause:** Missing secrets in production environment.  
**Fix:** Add all required secrets in Replit Deployments → Secrets tab.

### `sqlite3.OperationalError: no such table`
**Cause:** Database not initialized on first deploy.  
**Fix:** Set `DEV_AUTO_CREATE_TABLES=true` for first run, then switch to Alembic migrations for production.

### Port not opening / blank preview
**Cause:** App bound to wrong port or `LD_LIBRARY_PATH` missing.  
**Fix:** Ensure the workflow command uses port 5000 and includes the `LD_LIBRARY_PATH` prefix.

---

## 🔍 General Debugging Steps

1. **Check app health:** `curl http://localhost:5000/health`
2. **Check logs:** View workflow logs in Replit → shows all startup validation results
3. **Check pipeline status:**
   ```bash
   curl "http://localhost:5000/api/v1/pipeline/PIPELINE_ID" \
     -H "Authorization: Bearer YOUR_TOKEN"
   ```
4. **Check environment:**
   ```bash
   python3 -c "from app.core.config import settings; print(settings.llm_provider, settings.groq_model)"
   ```
5. **Reset a stuck pipeline:** Re-create the topic and run a new pipeline.

---

## Contact / Support

- Groq API docs: https://console.groq.com/docs
- YouTube API docs: https://developers.google.com/youtube/v3
- Pollinations AI: https://pollinations.ai
- Pexels API: https://www.pexels.com/api/
- Jamendo API: https://devportal.jamendo.com/
