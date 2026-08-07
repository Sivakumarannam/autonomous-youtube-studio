#!/usr/bin/env bash
# Host disk/RAM hygiene for Autonomous YouTube Studio (Oracle VM).
# Safe defaults: only unused Docker data + app temp dirs past retention.
set -euo pipefail

RETENTION_DAYS="${STORAGE_RETENTION_DAYS:-14}"
STUDIO_DIR="${STUDIO_DIR:-$HOME/studio}"
LOG_TAG="[host_cleanup]"

log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $LOG_TAG $*"; }

log "start retention_days=$RETENTION_DAYS"

# ── Disk snapshot (before) ──────────────────────────────────────────
df -h / | tail -1 | awk '{print "disk_before used="$3" avail="$4" use="$5}'

# ── Docker: unused containers/images/networks (not volumes) ─────────
if command -v docker >/dev/null 2>&1; then
  log "docker system prune"
  docker system prune -f --filter "until=${RETENTION_DAYS}h" 2>/dev/null \
    || docker system prune -f

  log "docker image prune (dangling)"
  docker image prune -f

  # Optional aggressive (uncomment if disk is critical):
  # docker builder prune -f --filter "until=${RETENTION_DAYS}h"
else
  log "docker not found — skip"
fi

# ── App temp dirs (frames / image_cache only — never videos/audio) ──
if [[ -d "$STUDIO_DIR/storage" ]]; then
  for sub in frames image_cache; do
    dir="$STUDIO_DIR/storage/$sub"
    if [[ -d "$dir" ]]; then
      log "prune $dir older than ${RETENTION_DAYS}d"
      find "$dir" -type f -mtime +"$RETENTION_DAYS" -delete 2>/dev/null || true
      find "$dir" -type d -empty -delete 2>/dev/null || true
    fi
  done
fi

# ── Disk snapshot (after) ───────────────────────────────────────────
df -h / | tail -1 | awk '{print "disk_after used="$3" avail="$4" use="$5}'
free -h | awk '/Mem:/{print "ram total="$2" used="$3" avail="$7}'

log "done"
