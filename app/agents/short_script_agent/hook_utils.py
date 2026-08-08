"""Hook hardening helpers for ShortScriptAgent (weak-opener strip + variety)."""
from __future__ import annotations

import re

_WEAK_HOOK_STARTS = re.compile(
    r"^\s*("
    r"here'?s what|here is what|in this video|today we|welcome|"
    r"hey guys|let'?s talk|have you ever wondered|so you want to|"
    r"this video will|i'?m going to show you|did you know that today|"
    r"in this short|welcome back"
    r")\b",
    re.IGNORECASE,
)

_OVERUSED_HOOK = re.compile(
    r"^\s*("
    r"99%\s+of\s+people|"
    r"nobody\s+told\s+you|"
    r"stop\s+\w+|"
    r"have\s+you\s+ever"
    r")\b",
    re.IGNORECASE,
)

EXTRA_LEAK_PATTERNS: list[str] = [
    r"here'?s what you need to know",
    r"in this short",
    r"welcome back",
]


def strengthen_hook(hook: str, full_script: str = "") -> str:
    """Strip weak openers; if still a long cliché template, try first strong script line."""
    hook = (hook or "").strip()
    weak = bool(_WEAK_HOOK_STARTS.match(hook)) if hook else True
    long_cliche = bool(
        full_script and hook and _OVERUSED_HOOK.match(hook) and len(hook.split()) > 14
    )
    if hook and not weak and not long_cliche:
        return hook

    for sentence in re.split(r"(?<=[.!?])\s+", (full_script or "").strip()):
        s = sentence.strip()
        if len(s.split()) < 3 or len(s.split()) > 16:
            continue
        if _WEAK_HOOK_STARTS.match(s):
            continue
        return s
    return hook
