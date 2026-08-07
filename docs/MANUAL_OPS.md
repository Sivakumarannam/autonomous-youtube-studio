# Manual Ops — Autonomous YouTube Studio (Oracle / production)

Daily and emergency procedures for the VM. App path assumed: `~/studio`.

---

## 1. Deploy / update

```bash
cd ~/studio
git pull origin main
docker compose -f docker/docker-compose.oracle.yml up -d --build
docker compose -f docker/docker-compose.oracle.yml logs api -f
```

Health:

```bash
curl -sS https://mystudioapp.duckdns.org/health
# or local
curl -sS http://127.0.0.1:8000/health
```

---

## 2. Dashboard + chatbot

1. Open `https://mystudioapp.duckdns.org/login`
2. Enter `DASHBOARD_AUTH_TOKEN`
3. Dashboard: `/dashboard`
4. Chatbot panel: use the chat UI on the dashboard (WebSocket `/ws/...`)

### Seed / refresh chatbot knowledge base

Auto-seeds `docs/project_overview.md` on first start if KB is empty.

Manual ingest (API, needs auth):

```bash
TOKEN="YOUR_DASHBOARD_AUTH_TOKEN"
# Upload text into KB via dashboard Knowledge Base panel, or:
curl -sS -X POST "https://mystudioapp.duckdns.org/api/v1/chat/knowledge" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"Manual Ops","text":"...paste procedure...","source_type":"manual"}'
```

If the chat API path differs in your build, use **Dashboard → Knowledge Base** upload instead.

Useful docs to keep in KB:

- `docs/project_overview.md`
- `docs/MANUAL_OPS.md` (this file)
- `docs/TROUBLESHOOTING.md`
- `docs/AUTOMATION_GUIDE.md`

---

## 3. Host disk / RAM cleanup

Script: `scripts/host_cleanup.sh` (Docker prune + `storage/frames` + `storage/image_cache`).

```bash
cd ~/studio
STUDIO_DIR=$HOME/studio STORAGE_RETENTION_DAYS=14 ./scripts/host_cleanup.sh
```

Cron (daily 03:30 UTC):

```cron
30 3 * * * STUDIO_DIR=/home/ubuntu/studio STORAGE_RETENTION_DAYS=14 /home/ubuntu/studio/scripts/host_cleanup.sh >> /home/ubuntu/studio/logs/host_cleanup.log 2>&1
```

App-level retention (videos/audio/cache) is already scheduled inside the API process.

---

## 4. High alerts (crash / down)

- Health watchdog pings DB every 2 minutes; high-alert after 2 consecutive failures.
- Orphaned `RUNNING` pipeline runs are marked `FAILED` on startup and high-alerted.
- Permanent pipeline failure uses `high_alert` (rate-limited).

Ensure notification env is set (email / Slack / Discord / Telegram). Level `error` must be enabled on at least one channel.

---

## 5. TLS (Caddy + Let’s Encrypt)

Caddy auto-obtains and renews certificates for the site block in `docker/Caddyfile`.

```text
mystudioapp.duckdns.org {
    reverse_proxy api:8000
}
```

Requirements:

- DNS A/AAAA for `mystudioapp.duckdns.org` → VM public IP
- Ports **80** and **443** open to the Caddy container
- Caddy service running in compose

Check certs:

```bash
docker compose -f docker/docker-compose.oracle.yml logs caddy | tail -50
```

Renewal is automatic (Caddy); no cron needed for certs.

---

## 6. Stuck pipeline / manual trigger

```bash
TOKEN="YOUR_TOKEN"
# list / inspect via dashboard Pipeline Runs panel, or API:
curl -sS "https://mystudioapp.duckdns.org/api/v1/pipeline/PIPELINE_ID" \
  -H "Authorization: Bearer $TOKEN"
```

Restart API only:

```bash
docker compose -f docker/docker-compose.oracle.yml restart api
```

---

## 7. Logs

```bash
docker compose -f docker/docker-compose.oracle.yml logs api --tail=200
docker compose -f docker/docker-compose.oracle.yml logs caddy --tail=100
tail -100 ~/studio/logs/host_cleanup.log
```

---

## 8. Docs map (cleanup index)

| Doc | Purpose |
|-----|---------|
| `docs/MANUAL_OPS.md` | This file — production runbook |
| `docs/MANUAL_GUIDE.md` | Manual video via dashboard/API |
| `docs/TROUBLESHOOTING.md` | Errors and fixes |
| `docs/SETUP_GUIDE.md` | Install |
| `docs/AUTOMATION_GUIDE.md` | Daily automation |
| `docs/project_overview.md` | Chatbot seed / architecture |
| `docs/CONFIG_REFERENCE.md` | Env vars |
