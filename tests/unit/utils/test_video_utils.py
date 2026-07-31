import pytest

from app.utils.video_utils import (
    calculate_clip_bounds,
    format_seconds_to_hms,
    is_valid_resolution,
    parse_duration_to_seconds,
)


def test_parse_duration_to_seconds_handles_mmss_and_hhmmss():
    assert parse_duration_to_seconds("01:30") == 90
    assert parse_duration_to_seconds("1:02:03") == 3723


def test_parse_duration_to_seconds_rejects_invalid_format():
    with pytest.raises(ValueError):
        parse_duration_to_seconds("abc")


def test_format_seconds_to_hms_computes_correct_string():
    assert format_seconds_to_hms(3661) == "01:01:01"


def test_calculate_clip_bounds_validates_values():
    assert calculate_clip_bounds(120, 10, 20) == (10, 20)
    with pytest.raises(ValueError):
        calculate_clip_bounds(120, 30, 10)


def test_is_valid_resolution_accepts_standard_values():
    assert is_valid_resolution("1920x1080")
    assert not is_valid_resolution("hd")
