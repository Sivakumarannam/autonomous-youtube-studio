"""Persistent store for the current Instagram access token.

Long-lived Instagram tokens (via the "Business Login for Instagram" flow)
are valid ~60 days. Rather than requiring a manual .env edit + container
restart every time the token is refreshed, the refreshed token is written
to a small local JSON file under storage/ — the app reads from there first,
falling back to the .env-configured value if the file doesn't exist yet
(e.g. on first boot after this feature was added).

This file lives in the same directory tree as other runtime state
(storage/) and is NOT meant to be committed to git or baked into the
Docker image — it's created/updated at runtime.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_STORE_PATH = Path(settings.storage_local_path) / "instagram_token.json"


def get_current_token() -> tuple[str, Optional[date]]:
    """Return (token, issued_at). issued_at is None if unknown (falls back
    to .env's INSTAGRAM_ACCESS_TOKEN with no tracked issue date — the
    watchdog job treats an unknown issued_at as "assume it might already
    be close to expiry" rather than silently never warning)."""
    if _STORE_PATH.exists():
        try:
            data = json.loads(_STORE_PATH.read_text())
            token = data.get("access_token", "")
            issued_at_str = data.get("issued_at", "")
            issued_at = date.fromisoformat(issued_at_str) if issued_at_str else None
            if token:
                return token, issued_at
        except Exception as exc:
            logger.warning(
                "Failed to read instagram_token.json — falling back to .env token",
                error=str(exc),
            )

    # Fall back to the .env-configured token.
    issued_at = None
    if settings.instagram_token_issued_at:
        try:
            issued_at = date.fromisoformat(settings.instagram_token_issued_at)
        except ValueError:
            logger.warning(
                "INSTAGRAM_TOKEN_ISSUED_AT is not a valid YYYY-MM-DD date — ignoring",
                value=settings.instagram_token_issued_at,
            )
    return settings.meta_access_token, issued_at


def save_refreshed_token(token: str, issued_at: Optional[date] = None) -> None:
    """Persist a newly refreshed token so subsequent API calls (and the
    watchdog's own day-count) use it immediately, without a restart."""
    issued_at = issued_at or date.today()
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STORE_PATH.write_text(
        json.dumps(
            {
                "access_token": token,
                "issued_at": issued_at.isoformat(),
                "saved_at": datetime.utcnow().isoformat() + "Z",
            }
        )
    )
    logger.info("Instagram token saved", issued_at=issued_at.isoformat())


def days_remaining() -> Optional[int]:
    """Days until the current token's ~60-day validity window ends, or
    None if we have no issued_at date to compute from at all."""
    _, issued_at = get_current_token()
    if issued_at is None:
        return None
    elapsed = (date.today() - issued_at).days
    return max(0, 60 - elapsed)
