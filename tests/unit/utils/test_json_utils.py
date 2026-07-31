import json
from pathlib import Path

from app.utils.json_utils import dump_json, load_json, merge_json


def test_merge_json_merges_nested_dicts():
    base = {"a": 1, "nested": {"x": 1, "y": 2}}
    override = {"nested": {"y": 10, "z": 20}, "b": 2}
    merged = merge_json(base, override)

    assert merged["a"] == 1
    assert merged["b"] == 2
    assert merged["nested"]["y"] == 10
    assert merged["nested"]["z"] == 20


import pytest

@pytest.mark.asyncio
async def test_dump_and_load_json(tmp_path):
    path = tmp_path / "data.json"
    data = {"key": "value"}

    await dump_json(path, data)
    loaded = await load_json(path)

    assert loaded == data
