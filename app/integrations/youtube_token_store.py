"""Track YouTube OAuth refresh-token issue date for dashboard countdown.

Access tokens (~1h) are refreshed automatically by YouTubeAuthManager using
YOUTUBE_REFRESH_TOKEN from .env. Google may also expire the *refresh* token
(e.g. ~7 days for apps in Testing). We cannot renew a refresh token without
user consent — this store only tracks issued_at so the UI/watchdog can warn
before that window ends.

State file lives under storage/ (runtime only, not committed).
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_STORE_PATH = Path(settings.storage_local_path) / "youtube_token.json"


def get_issued_at() -> Optional[date]:
    if _STORE_PATH.exists():
        try:
            data = json.loads(_STORE_PATH.read_text())
            issued_at_str = data.get("issued_at", "")
            if issued_at_str:
                return date.fromisoformat(issued_at_str)
        except Exception as exc:
            logger.warning("Failed to read youtube_token.json", error=str(exc))

    if settings.youtube_token_issued_at:
        try:
            return date.fromisoformat(settings.youtube_token_issued_at)
        except ValueError:
            logger.warning(
                "YOUTUBE_TOKEN_ISSUED_AT is not YYYY-MM-DD — ignoring",
                value=settings.youtube_token_issued_at,
            )
    return None


def mark_token_ok(issued_at: Optional[date] = None) -> None:
    """Record a successful refresh check (keeps issued_at if already set)."""
    existing = get_issued_at()
    issued = issued_at or existing or date.today()
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STORE_PATH.write_text(
        json.dumps(
            {
                "issued_at": issued.isoformat(),
                "last_ok_at": datetime.utcnow().isoformat() + "Z",
            }
        )
    )


def set_issued_at(issued_at: Optional[date] = None) -> None:
    """Call after the operator pastes a new YOUTUBE_REFRESH_TOKEN."""
    mark_token_ok(issued_at or date.today())


def days_remaining() -> Optional[int]:
    """Days left in the configured refresh-token lifetime window."""
    issued_at = get_issued_at()
    if issued_at is None:
        return None
    lifetime = max(1, int(getattr(settings, "youtube_token_lifetime_days", 7)))
    elapsed = (date.today() - issued_at).days
    return max(0, lifetime - elapsed)
