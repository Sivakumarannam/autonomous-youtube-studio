#!/usr/bin/env python3
"""
setup_verify.py — Run after cloning/importing to confirm the environment is ready.

Usage:
    python3 scripts/setup_verify.py

Exit code 0 = all checks passed.
Exit code 1 = one or more checks failed.
"""

import importlib
import os
import subprocess
import sys

# Ensure workspace root is on the path so `app` package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REQUIRED_PACKAGES = [
    "fastapi", "uvicorn", "sqlalchemy", "alembic", "asyncpg", "aiosqlite",
    "pydantic", "structlog", "apscheduler", "httpx", "tenacity",
    "moviepy", "PIL", "numpy", "gtts", "google.auth",
    "googleapiclient", "bs4", "trafilatura", "requests",
    "asyncpraw", "groq",
]

REQUIRED_SECRETS = [
    "GEMINI_API_KEY",
    "YOUTUBE_API_KEY",
    "YOUTUBE_CLIENT_ID",
    "YOUTUBE_CLIENT_SECRET",
    "DASHBOARD_AUTH_TOKEN",
]

OPTIONAL_SECRETS = [
    "YOUTUBE_REFRESH_TOKEN",
    "GROQ_API_KEY",
    "PEXELS_API_KEY",
    "PIXABAY_API_KEY",
    "JAMENDO_CLIENT_ID",
    "INSTAGRAM_ACCESS_TOKEN",
    "SLACK_WEBHOOK_URL",
    "DISCORD_WEBHOOK_URL",
    "TELEGRAM_BOT_TOKEN",
    "NOTIFICATION_EMAIL_FROM",
]

OK   = "\033[32m✓\033[0m"
WARN = "\033[33m⚠\033[0m"
FAIL = "\033[31m✗\033[0m"

failures = []


def check(label: str, ok: bool, detail: str = "", required: bool = True) -> None:
    icon = OK if ok else (FAIL if required else WARN)
    print(f"  {icon}  {label}" + (f" — {detail}" if detail else ""))
    if not ok and required:
        failures.append(label)


# ── 1. Python packages ────────────────────────────────────────────────────────
print("\n[1] Python packages")
for pkg in REQUIRED_PACKAGES:
    try:
        importlib.import_module(pkg)
        check(pkg, True)
    except ImportError as e:
        check(pkg, False, str(e))

# ── 2. Environment secrets ────────────────────────────────────────────────────
print("\n[2] Required secrets")
for key in REQUIRED_SECRETS:
    check(key, bool(os.environ.get(key)), required=True)

print("\n[3] Optional secrets")
for key in OPTIONAL_SECRETS:
    check(key, bool(os.environ.get(key)), required=False)

# ── 3. Database migrations ────────────────────────────────────────────────────
print("\n[4] Database migrations")
try:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "current"],
        capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(__file__))
    )
    output = result.stdout + result.stderr
    has_head = "(head)" in output
    check(
        "Alembic at HEAD",
        has_head,
        output.strip().splitlines()[-1] if output.strip() else "no output",
    )
except Exception as e:
    check("Alembic migration check", False, str(e))

# ── 4. App import ─────────────────────────────────────────────────────────────
print("\n[5] App boot check")
try:
    import app.core.config  # noqa: F401
    check("app.core.config loads", True)
except Exception as e:
    check("app.core.config loads", False, str(e))

try:
    from app.core.config import settings
    check("LLM_PROVIDER set", bool(settings.llm_provider), settings.llm_provider)
    check("DATABASE_URL resolved", bool(settings.database_url), settings.database_url[:40] + "…")
except Exception as e:
    check("settings load", False, str(e))

# ── 5. FFmpeg ─────────────────────────────────────────────────────────────────
print("\n[6] System tools")
try:
    result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
    version_line = result.stdout.splitlines()[0] if result.stdout else "unknown"
    check("FFmpeg", result.returncode == 0, version_line)
except FileNotFoundError:
    check("FFmpeg", False, "not found in PATH")

# ── Summary ───────────────────────────────────────────────────────────────────
print()
if failures:
    print(f"\033[31mSetup incomplete — {len(failures)} required check(s) failed:\033[0m")
    for f in failures:
        print(f"  • {f}")
    sys.exit(1)
else:
    print("\033[32mAll required checks passed — environment is ready.\033[0m")
    print("Run the app:  python3 -m uvicorn app.main:app --host 0.0.0.0 --port 5000 --reload")
    sys.exit(0)
