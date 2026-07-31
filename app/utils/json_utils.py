import asyncio
import json, re
from pathlib import Path
from typing import Any, Dict, Union


async def load_json(path: Union[str, Path]) -> Any:
    return await asyncio.to_thread(_read_json, Path(path))


async def dump_json(path: Union[str, Path], data: Any, *, indent: int = 2) -> None:
    await asyncio.to_thread(_write_json, Path(path), data, indent)


def merge_json(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = {**base}
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_json(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, data: Any, indent: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=indent, ensure_ascii=False)
# --------------------------------------------------------------------
# NEW FUNCTION (Add below)
# --------------------------------------------------------------------

def extract_json(text: str) -> dict:
    """
    Extract JSON from LLM responses.

    Supports:

    - Raw JSON
    - ```json ... ```
    - Extra text before/after JSON
    """

    text = text.strip()

    text = re.sub(r"^```json", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"^```", "", text).strip()
    text = re.sub(r"```$", "", text).strip()

    match = re.search(r"\{.*\}", text, re.DOTALL)

    if not match:
        raise ValueError("No JSON object found in LLM response.")

    return json.loads(match.group())