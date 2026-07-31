import pytest

from app.utils.prompt_utils import build_prompt, extract_variables, normalize_prompt, render_prompt


def test_extract_variables_returns_expected_fields():
    template = "Create a title for {{ topic }} and {{ audience }}"
    assert extract_variables(template) == ["audience", "topic"]


def test_build_prompt_renders_template():
    template = "Write about {{ topic }}"
    rendered = build_prompt(template, {"topic": "AI"})
    assert rendered == "Write about AI"


def test_build_prompt_raises_for_missing_variables():
    with pytest.raises(ValueError):
        build_prompt("Hello {{ name }}", {})


def test_normalize_prompt_strips_empty_lines():
    prompt = "\n  Hello \n\n  World  \n"
    assert normalize_prompt(prompt) == "Hello\nWorld"
