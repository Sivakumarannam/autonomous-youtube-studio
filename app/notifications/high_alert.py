"""Rate-limited high-severity alerts (crash / down / permanent failure)."""
from __future__ import annotations

import time
from typing import Optional

from app.core.logging import get_logger
from app.notifications.service import notify

logger = get_logger(__name__)

# key -> last sent monotonic time
_last_sent: dict[str, float] = {}
_DEFAULT_COOLDOWN_S = 300  # 5 minutes per alert key


async def high_alert(
    title: str,
    body: str,
    *,
    key: str,
    extra: Optional[dict] = None,
    cooldown_s: int = _DEFAULT_COOLDOWN_S,
) -> None:
    """
    Send level=error notification, at most once per `key` every cooldown_s.
    Never raises.
    """
    now = time.monotonic()
    last = _last_sent.get(key, 0.0)
    if now - last < cooldown_s:
        logger.debug("high_alert suppressed (cooldown)", key=key)
        return
    try:
        await notify(title=title, body=body, level="error", extra=extra or {})
        _last_sent[key] = now
    except Exception as exc:
        logger.warning("high_alert failed (non-fatal)", key=key, error=str(exc))
