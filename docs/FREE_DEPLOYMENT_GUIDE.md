# Free Deployment Guide — Autonomous YouTube Studio

Options ranked by ease and reliability. All free tiers, no credit card required unless noted.

---

## ✅ Option 1 — Replit Deployments (Recommended)

**Free tier:** Replit Autoscale — you get free egress and compute for hobby projects.  
**Best for:** Always-on production hosting with zero config.

### Steps

1. In your Replit project, click **Deploy** (top-right)
2. Choose **Autoscale** deployment
3. Add all required secrets in the **Secrets** tab of the deployment:
   ```
   GROQ_API_KEY
   DASHBOARD_AUTH_TOKEN
   YOUTUBE_CLIENT_ID
   YOUTUBE_CLIENT_SECRET
   YOUTUBE_REFRESH_TOKEN
   HF_API_TOKEN
   JAMENDO_CLIENT_ID
   PEXELS_API_KEY
   PIXABAY_API_KEY
   ```
4. Add env vars in the **Environment** tab:
   ```
   LLM_PROVIDER=groq
   GROQ_MODEL=llama-3.3-70b-versatile
   DEV_AUTO_CREATE_TABLES=true
   VOICE_ENABLED=true
   APP_PORT=5000
   ```
5. Click **Deploy**
6. Your app gets a permanent URL like `https://your-project.replit.app`

### Important for Replit Deploy
- The run command must include the `LD_LIBRARY_PATH` fix:
  ```bash
  LD_LIBRARY_PATH=/nix/store/04344hrpsbjzy7wq7vhwgcyarpbliz1l-gcc-14.2.1.20250322-lib/lib:$LD_LIBRARY_PATH python3 -m uvicorn app.main:app --host 0.0.0.0 --port 5000
  ```
  This is already configured in the workflow.

---

## ✅ Option 2 — Render.com (Free Web Service)

**Free tier:** 750 hours/month, sleeps after 15 min inactivity.  
**Best for:** Background workers, scheduled pipelines.

### Steps

1. Push your code to GitHub
2. Sign up at https://render.com
3. New → **Web Service** → connect your GitHub repo
4. Settings:
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Environment:** add all secrets
5. Deploy

> ⚠️ Free tier sleeps when idle — the scheduler may miss ticks. Upgrade to Starter ($7/mo) for always-on.

---

## ✅ Option 3 — Railway.app

**Free tier:** $5/month free credit (no credit card for signup).  
**Best for:** Quick deploy with persistent storage.

### Steps

1. Sign up at https://railway.app
2. New Project → **Deploy from GitHub**
3. Add environment variables (same list as Render)
4. Railway auto-detects the Python app and deploys

> SQLite file persists on Railway's attached disk. For longer-term use, add a Railway PostgreSQL plugin.

---

## ✅ Option 4 — Fly.io

**Free tier:** 3 shared-CPU VMs + 3GB persistent storage free.  
**Best for:** More control, persistent SQLite, background scheduler.

### Steps

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# Deploy
flyctl launch
flyctl secrets set GROQ_API_KEY=xxx DASHBOARD_AUTH_TOKEN=xxx ...
flyctl deploy
```

The app's `storage/` directory (videos, audio, cache) persists on Fly volumes.

---

## ✅ Option 5 — Hugging Face Spaces (Gradio/Docker)

**Free tier:** CPU Spaces are free, persistent, always-on.  
**Caveat:** Designed for ML demos, but Docker Spaces work for FastAPI.

### Steps

1. Create a new Space at https://huggingface.co/spaces
2. Choose **Docker** SDK
3. Upload your code + `Dockerfile`
4. Add secrets in Space Settings → Repository Secrets

---

## ⚠️ What Needs Special Attention on Any Platform

| Issue | Fix |
|-------|-----|
| `libstdc++.so.6` missing | Add `gcc` to system deps or use the `LD_LIBRARY_PATH` workaround |
| SQLite is ephemeral | Use PostgreSQL (Render/Railway/Supabase free tiers) for production |
| FFmpeg not available | Install via apt/nix: `apt install ffmpeg` in Dockerfile |
| YouTube redirect URI | Update `YOUTUBE_REDIRECT_URI` to match your deployment URL |
| Storage directory missing | Create `storage/videos/`, `storage/audio/`, `storage/cache/` on startup |

---

## Production Checklist

Before deploying to production, verify:

- [ ] `DASHBOARD_AUTH_TOKEN` is set (strong, random token)
- [ ] `APP_ENV=production` (disables dev convenience features)
- [ ] `DEV_AUTO_CREATE_TABLES=false` in production — run Alembic migrations instead
- [ ] All YouTube OAuth credentials are correct
- [ ] `YOUTUBE_REDIRECT_URI` matches your deployment domain
- [ ] Persistent storage volume mounted (for `storage/` dir)
- [ ] Email/Slack/Discord/Telegram notifications configured

---

## Recommended: Replit + Supabase (Free PostgreSQL)

For the most reliable free setup:

1. Deploy on **Replit Autoscale** (as above)
2. Create a free PostgreSQL DB at https://supabase.com (500MB free)
3. Add `DATABASE_URL=postgresql://...` to Replit Secrets
4. Set `DEV_AUTO_CREATE_TABLES=false` and run:
   ```bash
   python3 -m alembic upgrade head
   ```

This gives you a permanent, scalable database with zero cost.
