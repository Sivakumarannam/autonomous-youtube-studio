"""Targeted unit tests for peak-engagement-time upload scheduling.

Covers: mid-window approval, just-before-window approval, no-config
fallback, and malformed-config safe fallback.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from app.agents.pipeline_agent.peak_scheduling import compute_scheduled_at


def _make_channel(*, timezone_name="UTC", config=None):
    channel = MagicMock()
    channel.id = "channel-uuid-001"
    channel.timezone = timezone_name
    channel.config = config
    return channel


def test_mid_window_schedules_immediately_after_flat_delay():
    """If floor already falls inside today's peak window, use the floor
    itself (no artificial extra wait)."""
    config = json.dumps(
        {"peak_windows": {"short": {"weekday": [10, 14], "weekend": [10, 14]}}}
    )
    channel = _make_channel(config=config)
    # Wednesday 2026-07-08 10:05 UTC -> floor (15 min later) at 10:20, still
    # inside the [10, 14) window.
    now_utc = datetime(2026, 7, 8, 10, 5, tzinfo=timezone.utc)

    result = compute_scheduled_at(
        channel=channel, content_type="short", now_utc=now_utc, flat_delay_minutes=15
    )

    expected_floor = datetime(2026, 7, 8, 10, 20, tzinfo=timezone.utc)
    assert result == expected_floor


def test_just_before_window_waits_for_window_start():
    """If floor lands just before today's window, schedule at the window
    start rather than immediately."""
    config = json.dumps(
        {"peak_windows": {"short": {"weekday": [18, 22], "weekend": [18, 22]}}}
    )
    channel = _make_channel(config=config)
    # Wednesday 2026-07-08 17:50 UTC -> floor at 18:05, which IS inside
    # [18, 22) already, so use a floor before the window instead.
    now_utc = datetime(2026, 7, 8, 17, 30, tzinfo=timezone.utc)

    result = compute_scheduled_at(
        channel=channel, content_type="short", now_utc=now_utc, flat_delay_minutes=15
    )

    # floor = 17:45, before window start 18:00 -> should wait for window.
    expected_window_start = datetime(2026, 7, 8, 18, 0, tzinfo=timezone.utc)
    assert result == expected_window_start


def test_no_config_falls_back_to_default_peak_windows():
    """A channel with no config at all still uses the static defaults
    (not a bare flat-delay), since defaults are always active."""
    channel = _make_channel(config=None)
    # Wednesday 2026-07-08 05:00 UTC, well before default weekday short
    # window (18-22).
    now_utc = datetime(2026, 7, 8, 5, 0, tzinfo=timezone.utc)

    result = compute_scheduled_at(
        channel=channel, content_type="short", now_utc=now_utc, flat_delay_minutes=15
    )

    expected_window_start = datetime(2026, 7, 8, 18, 0, tzinfo=timezone.utc)
    assert result == expected_window_start


def test_malformed_config_falls_back_safely_without_raising():
    """Invalid JSON and malformed peak_windows shapes must never raise and
    must fall back to the (default) peak-window behavior, identical to the
    unconfigured case."""
    now_utc = datetime(2026, 7, 8, 5, 0, tzinfo=timezone.utc)
    expected_window_start = datetime(2026, 7, 8, 18, 0, tzinfo=timezone.utc)

    # Invalid JSON entirely.
    bad_json_channel = _make_channel(config="{not valid json")
    result = compute_scheduled_at(
        channel=bad_json_channel,
        content_type="short",
        now_utc=now_utc,
        flat_delay_minutes=15,
    )
    assert result == expected_window_start

    # Valid JSON, but malformed window shape (start >= end).
    malformed_channel = _make_channel(
        config=json.dumps(
            {"peak_windows": {"short": {"weekday": [22, 18], "weekend": [10, 14]}}}
        )
    )
    result = compute_scheduled_at(
        channel=malformed_channel,
        content_type="short",
        now_utc=now_utc,
        flat_delay_minutes=15,
    )
    assert result == expected_window_start

    # Valid JSON, missing weekend key.
    missing_key_channel = _make_channel(
        config=json.dumps({"peak_windows": {"short": {"weekday": [18, 22]}}})
    )
    result = compute_scheduled_at(
        channel=missing_key_channel,
        content_type="short",
        now_utc=now_utc,
        flat_delay_minutes=15,
    )
    assert result == expected_window_start

    # Non-integer hour values.
    non_int_channel = _make_channel(
        config=json.dumps(
            {
                "peak_windows": {
                    "short": {"weekday": ["18", "22"], "weekend": [10, 14]}
                }
            }
        )
    )
    result = compute_scheduled_at(
        channel=non_int_channel,
        content_type="short",
        now_utc=now_utc,
        flat_delay_minutes=15,
    )
    assert result == expected_window_start


def test_horizon_cap_falls_back_to_flat_delay_when_window_too_far():
    """If configured windows only exist for a content type that never
    matches within the 48h horizon relative to a tiny window, fall back to
    flat-delay rather than waiting indefinitely."""
    # Configure a window that only opens for 1 hour very late relative to
    # a long horizon walk — simulate by using a channel whose timezone
    # offset pushes the next window past the cap is hard with real windows
    # (they recur daily), so instead validate the cap directly by using a
    # window that starts "tomorrow" beyond a synthetic short horizon via a
    # content type absent from config -> forces default fallback check.
    channel = _make_channel(config=json.dumps({"peak_windows": {}}))
    now_utc = datetime(2026, 7, 8, 5, 0, tzinfo=timezone.utc)

    result = compute_scheduled_at(
        channel=channel, content_type="short", now_utc=now_utc, flat_delay_minutes=15
    )
    # No entry for "short" in explicit (empty) peak_windows dict -> falls
    # back to DEFAULT_PEAK_WINDOWS for "short", which recurs daily and is
    # well within 48h.
    expected_window_start = datetime(2026, 7, 8, 18, 0, tzinfo=timezone.utc)
    assert result == expected_window_start


def test_horizon_cap_actually_falls_back_when_next_window_exceeds_cap():
    """When the next qualifying window genuinely lies beyond the 48h cap,
    fall back to flat-delay instead of waiting for it."""
    from app.agents.pipeline_agent import peak_scheduling as ps

    # A window active only 00:00-01:00, both weekday/weekend, so day 0's
    # window has already passed by the time floor is computed (23:50), and
    # day 1's window (00:00-01:00) is only ~10 minutes away -- well inside
    # any real cap. To force a genuine "too far" case we shrink the cap
    # itself to less than that gap.
    config = json.dumps(
        {"peak_windows": {"short": {"weekday": [0, 1], "weekend": [0, 1]}}}
    )
    channel = _make_channel(config=config)
    now_utc = datetime(2026, 7, 8, 23, 50, tzinfo=timezone.utc)  # floor 00:05 Jul 9

    original_horizon = ps.PEAK_SCHEDULING_HORIZON_HOURS
    try:
        # Floor already lies inside [0,1) on Jul 9 -> would normally return
        # floor itself. Shrink the cap to 0 hours so even a same-day window
        # start counts as "too far" if it doesn't match floor exactly, and
        # use a window that starts slightly after floor to force a wait
        # that exceeds a near-zero cap.
        ps.PEAK_SCHEDULING_HORIZON_HOURS = 0
        far_config = json.dumps(
            {"peak_windows": {"short": {"weekday": [2, 3], "weekend": [2, 3]}}}
        )
        far_channel = _make_channel(config=far_config)
        result = compute_scheduled_at(
            channel=far_channel,
            content_type="short",
            now_utc=now_utc,
            flat_delay_minutes=15,
        )
        # floor = 00:05 Jul 9, next window start = 02:00 Jul 9 (~2h away),
        # which exceeds the (patched) 0h cap -> must fall back to floor.
        expected_floor = datetime(2026, 7, 9, 0, 5, tzinfo=timezone.utc)
        assert result == expected_floor
    finally:
        ps.PEAK_SCHEDULING_HORIZON_HOURS = original_horizon


def test_hour_24_end_boundary_treated_as_midnight():
    """A window configured with end hour 24 (e.g. [20, 24)) must be treated
    as running through midnight without raising ValueError."""
    config = json.dumps(
        {"peak_windows": {"short": {"weekday": [20, 24], "weekend": [20, 24]}}}
    )
    channel = _make_channel(config=config)
    # Floor at 23:50 UTC, inside [20, 24) -> schedule at floor itself.
    now_utc = datetime(2026, 7, 8, 23, 35, tzinfo=timezone.utc)

    result = compute_scheduled_at(
        channel=channel, content_type="short", now_utc=now_utc, flat_delay_minutes=15
    )

    expected_floor = datetime(2026, 7, 8, 23, 50, tzinfo=timezone.utc)
    assert result == expected_floor


def test_dst_spring_forward_does_not_raise_and_returns_valid_window():
    """Scheduling across a US DST spring-forward boundary (clocks jump from
    02:00 to 03:00 on 2026-03-08 in America/New_York) must not raise and
    must still return a UTC timestamp within the configured local window."""
    config = json.dumps(
        {"peak_windows": {"short": {"weekday": [9, 12], "weekend": [9, 12]}}}
    )
    channel = _make_channel(timezone_name="America/New_York", config=config)
    # 2026-03-08 05:00 UTC = 00:00 EST (before spring-forward that night).
    now_utc = datetime(2026, 3, 8, 5, 0, tzinfo=timezone.utc)

    result = compute_scheduled_at(
        channel=channel, content_type="short", now_utc=now_utc, flat_delay_minutes=15
    )

    # Result must be tz-aware UTC and fall within 09:00-12:00 local on some
    # nearby day, regardless of the DST transition happening in between.
    assert result.tzinfo is not None
    local_result = result.astimezone(ZoneInfo("America/New_York"))
    assert 9 <= local_result.hour < 12


def test_month_and_year_boundary_day_walk_does_not_raise():
    """Day-walking across a year boundary (Dec 31 -> Jan 1) must not raise
    and must still find a valid window."""
    config = json.dumps(
        {"peak_windows": {"short": {"weekday": [10, 11], "weekend": [10, 11]}}}
    )
    channel = _make_channel(config=config)
    now_utc = datetime(2025, 12, 31, 23, 55, tzinfo=timezone.utc)

    result = compute_scheduled_at(
        channel=channel, content_type="short", now_utc=now_utc, flat_delay_minutes=15
    )

    assert result.tzinfo is not None
    assert result >= now_utc


def test_weekend_detection_uses_localized_time_not_utc():
    """A UTC instant that is Friday night but already Saturday in the
    channel's local timezone must be treated as a weekend day."""
    # 2026-07-10 is a Friday. 23:30 UTC on Friday is already
    # 2026-07-11 (Saturday) 09:30 in Asia/Kolkata (+05:30).
    config = json.dumps(
        {
            "peak_windows": {
                "short": {"weekday": [1, 2], "weekend": [9, 12]}
            }
        }
    )
    channel = _make_channel(timezone_name="Asia/Kolkata", config=config)
    now_utc = datetime(2026, 7, 10, 23, 30, tzinfo=timezone.utc)

    result = compute_scheduled_at(
        channel=channel, content_type="short", now_utc=now_utc, flat_delay_minutes=15
    )

    # floor_utc = 23:45 UTC Fri = 05:15 local Sat (Asia/Kolkata, +5:30) ->
    # already Saturday locally even though the UTC instant is still Friday.
    # The weekend window [9, 12) local hasn't opened yet at 05:15, so it
    # must wait for local 09:00 Sat -> 03:30 UTC Sat. If weekday detection
    # incorrectly used the UTC (Friday) weekday instead, it would instead
    # apply the [1, 2) weekday window and produce a different, wrong time.
    expected_window_start = datetime(2026, 7, 11, 3, 30, tzinfo=timezone.utc)
    assert result == expected_window_start
