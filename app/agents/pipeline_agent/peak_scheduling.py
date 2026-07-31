"""Peak-engagement-time upload scheduling.

Replaces the flat `now() + pipeline_publish_delay_minutes` scheduling with a
per-channel "peak window" lookup. Static, non-ML default peak windows
(DEFAULT_PEAK_WINDOWS) apply to every channel unless overridden via
Channel.config — this is intentional, approved behavior, not a fallback of
last resort. The flat-delay value (`now + flat_delay_minutes`) is used only
as the safety floor in three specific cases: malformed/unparseable
Channel.config, no window entry for the run's content type in either the
channel's config or the defaults, or the next qualifying window lying beyond
the horizon cap.

Design (approved):
  - Peak windows are stored in the existing `Channel.config` JSON text
    column under a `peak_windows` key — no schema migration needed.
  - Shape:
        {
          "peak_windows": {
            "short": {"weekday": [18, 22], "weekend": [11, 14]},
            "long":  {"weekday": [19, 21], "weekend": [12, 15]}
          }
        }
    Hours are local to the channel's timezone, 24h, half-open [start, end).
  - If a channel has no `config`, invalid JSON, or a malformed/missing
    `peak_windows` entry for the given content type, this is treated
    identically to "not configured" — falls back to flat-delay. This
    function NEVER raises; any parsing/validation problem is caught,
    logged as a warning, and treated as "no peak windows".
  - Weekday/weekend classification and window bounds are evaluated using
    the channel's LOCALIZED datetime (zoneinfo.ZoneInfo(channel.timezone)),
    not UTC, to avoid off-by-one-day errors near local midnight.
  - Horizon cap: if the earliest qualifying window start is more than
    PEAK_SCHEDULING_HORIZON_HOURS (48h) after the flat-delay floor, fall
    back to the flat-delay value instead of waiting further.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from app.core.logging import get_logger
from app.database.models.channel import Channel

logger = get_logger(__name__)

PEAK_SCHEDULING_HORIZON_HOURS = 48

# Default peak windows applied when a channel has no `peak_windows` override
# at all (Channel.config missing/null, or missing this key). Static,
# non-ML defaults: weekday evenings and weekend midday.
DEFAULT_PEAK_WINDOWS: dict[str, dict[str, tuple[int, int]]] = {
    "short": {"weekday": (18, 22), "weekend": (11, 14)},
    "long": {"weekday": (19, 21), "weekend": (12, 15)},
}


def _parse_window(raw: object) -> Optional[tuple[int, int]]:
    """Validate a single [start, end) window. Returns None if malformed."""
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        return None
    start, end = raw
    if not isinstance(start, int) or not isinstance(end, int):
        return None
    if isinstance(start, bool) or isinstance(end, bool):  # bool is an int subclass
        return None
    if not (0 <= start < 24 and 0 <= end <= 24):
        return None
    if start >= end:
        return None
    return start, end


def _resolve_windows_for_content_type(
    channel: Channel, content_type: str
) -> Optional[dict[str, tuple[int, int]]]:
    """Return {"weekday": (s,e), "weekend": (s,e)} for this content type, or
    None if nothing usable is configured/defaulted. Never raises.
    """
    configured: Optional[dict] = None

    raw_config = getattr(channel, "config", None)
    if raw_config:
        try:
            parsed = json.loads(raw_config)
            peak_windows = parsed.get("peak_windows") if isinstance(parsed, dict) else None
            if isinstance(peak_windows, dict):
                entry = peak_windows.get(content_type)
                if isinstance(entry, dict):
                    weekday = _parse_window(entry.get("weekday"))
                    weekend = _parse_window(entry.get("weekend"))
                    if weekday is not None and weekend is not None:
                        configured = {"weekday": weekday, "weekend": weekend}
                    else:
                        logger.warning(
                            "Malformed peak_windows entry for channel; "
                            "falling back to flat-delay scheduling.",
                            channel_id=str(getattr(channel, "id", None)),
                            content_type=content_type,
                        )
        except Exception:
            logger.warning(
                "Channel.config is not valid JSON / peak_windows unreadable; "
                "falling back to flat-delay scheduling.",
                channel_id=str(getattr(channel, "id", None)),
            )
            configured = None

    if configured is not None:
        return configured

    return DEFAULT_PEAK_WINDOWS.get(content_type)


def compute_scheduled_at(
    channel: Channel,
    content_type: str,
    now_utc: datetime,
    flat_delay_minutes: int,
) -> datetime:
    """Compute scheduled_at, preferring the next peak-engagement window.

    Always returns a tz-aware UTC datetime. Never raises — any malformed
    config or unresolvable window falls back to the flat-delay value.
    """
    floor_utc = now_utc + timedelta(minutes=flat_delay_minutes)

    try:
        tz = ZoneInfo(channel.timezone)
    except Exception:
        tz = ZoneInfo("UTC")

    windows = _resolve_windows_for_content_type(channel, content_type)
    if windows is None:
        return floor_utc

    horizon_utc = floor_utc + timedelta(hours=PEAK_SCHEDULING_HORIZON_HOURS)

    # Walk forward day by day (in local time) starting from floor's local
    # day, looking for the earliest window start >= floor_utc.
    floor_local = floor_utc.astimezone(tz)
    for day_offset in range(0, PEAK_SCHEDULING_HORIZON_HOURS // 24 + 2):
        candidate_day_local = (floor_local + timedelta(days=day_offset)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        is_weekend = candidate_day_local.weekday() >= 5  # Sat=5, Sun=6
        window = windows["weekend"] if is_weekend else windows["weekday"]
        start_hour, end_hour = window

        window_start_local = candidate_day_local.replace(hour=start_hour)
        window_end_local = (
            candidate_day_local + timedelta(days=1)
            if end_hour == 24
            else candidate_day_local.replace(hour=end_hour)
        )

        # If floor falls inside today's window, schedule at floor itself.
        if window_start_local <= floor_local < window_end_local:
            candidate_utc = floor_local.astimezone(tz).astimezone(
                floor_utc.tzinfo
            )
            return floor_utc if day_offset == 0 else candidate_utc

        if window_start_local >= floor_local:
            candidate_utc = window_start_local.astimezone(floor_utc.tzinfo)
            if candidate_utc > horizon_utc:
                break
            return candidate_utc

    # No qualifying window within the horizon cap.
    return floor_utc
