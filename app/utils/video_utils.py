import re
from pathlib import Path
from typing import Tuple

DURATION_PATTERN = re.compile(r"^(?:(\d+):)?([0-5]?\d):([0-5]?\d)$")


def parse_duration_to_seconds(duration: str) -> int:
    match = DURATION_PATTERN.match(duration.strip())
    if not match:
        raise ValueError("Duration must be formatted as HH:MM:SS or MM:SS")
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2))
    seconds = int(match.group(3))
    total = hours * 3600 + minutes * 60 + seconds
    if total <= 0:
        raise ValueError("Duration must be greater than zero")
    return total


def format_seconds_to_hms(seconds: int) -> str:
    if seconds < 0:
        raise ValueError("Seconds must be non-negative")
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"


def calculate_clip_bounds(duration_seconds: int, start_seconds: int, end_seconds: int) -> Tuple[int, int]:
    if start_seconds < 0 or end_seconds < 0:
        raise ValueError("Clip bounds must be non-negative")
    if end_seconds <= start_seconds:
        raise ValueError("End time must be greater than start time")
    if end_seconds > duration_seconds:
        raise ValueError("End time cannot exceed total duration")
    return start_seconds, end_seconds


def is_valid_resolution(resolution: str) -> bool:
    parts = resolution.split("x")
    if len(parts) != 2:
        return False
    return all(part.isdigit() and int(part) > 0 for part in parts)


def validate_video_path(path: str) -> bool:
    candidate = Path(path)
    return candidate.exists() and candidate.is_file()
