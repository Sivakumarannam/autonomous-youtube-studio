#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# Production Startup Script — Autonomous YouTube Studio
#
# Usage:
#   bash scripts/start_production.sh
#
# What it does:
#   1. Validates required environment variables
#   2. Runs Alembic database migrations (idempotent — safe to run on every boot)
#   3. Starts the FastAPI application with uvicorn
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

echo "========================================="
echo " Autonomous YouTube Studio — Production  "
echo "========================================="

# ── 1. Validate required env vars ─────────────────────────────────────────────
REQUIRED_VARS=(
    "DATABASE_URL"
    "DASHBOARD_AUTH_TOKEN"
    "GROQ_API_KEY"
    "APP_SECRET_KEY"
    "JWT_SECRET_KEY"
)

MISSING=()
for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var:-}" ]; then
        MISSING+=("$var")
    fi
done

if [ ${#MISSING[@]} -gt 0 ]; then
    echo "❌ ERROR: Missing required environment variables:"
    for var in "${MISSING[@]}"; do
        echo "   - $var"
    done
    exit 1
fi

echo "✓ Environment variables validated"

# ── 2. Run Alembic migrations ─────────────────────────────────────────────────
echo ""
echo "Running database migrations..."
python3 -m alembic upgrade head
echo "✓ Database migrations applied"

# ── 3. Start application ──────────────────────────────────────────────────────
echo ""
echo "Starting application on port ${APP_PORT:-8000}..."
exec python3 -m uvicorn app.main:app \
    --host "0.0.0.0" \
    --port "${APP_PORT:-8000}" \
    --workers 1 \
    --log-level "warning"