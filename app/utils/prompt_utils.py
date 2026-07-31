import re
from string import Template
from typing import Dict, Iterable, List


PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def normalize_prompt(prompt: str) -> str:
    lines = [line.strip() for line in prompt.strip().splitlines() if line.strip()]
    return "\n".join(lines)


def render_prompt(template: str, values: Dict[str, str]) -> str:
    prompt = normalize_prompt(template)

    def replace(match: re.Match) -> str:
        key = match.group(1)
        if key not in values:
            return match.group(0)
        return str(values[key])

    return PLACEHOLDER_PATTERN.sub(replace, prompt)


def extract_variables(template: str) -> List[str]:
    return sorted({match.group(1) for match in PLACEHOLDER_PATTERN.finditer(template)})


def build_prompt(template: str, variables: Dict[str, str]) -> str:
    missing = [key for key in extract_variables(template) if key not in variables]
    if missing:
        raise ValueError(f"Missing template variables: {', '.join(missing)}")
    return render_prompt(template, variables)
