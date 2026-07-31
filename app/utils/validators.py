import os
import re
from pathlib import Path
from typing import Union

URL_PATTERN = re.compile(
    r"^(https?)://(?:localhost|[\w\-]+(?:\.[\w\-]+)+)(:\d+)?(?:[/?#].*)?$"
)
FILENAME_PATTERN = re.compile(r"^[\w\-\. ]+$")


def is_valid_filename(filename: str) -> bool:
    return bool(FILENAME_PATTERN.match(filename)) and filename not in {".", ".."}


def is_valid_url(url: str) -> bool:
    return bool(URL_PATTERN.match(url.strip()))


def is_safe_path(path: Union[str, Path]) -> bool:
    path_obj = Path(path)
    try:
        return not any(part == ".." for part in path_obj.parts) and path_obj.is_absolute() is False
    except Exception:
        return False


def validate_duration_seconds(seconds: int) -> bool:
    return 0 < seconds <= 86400


def ensure_path_exists(path: Union[str, Path]) -> Path:
    path_obj = Path(path)
    path_obj.mkdir(parents=True, exist_ok=True)
    return path_obj
