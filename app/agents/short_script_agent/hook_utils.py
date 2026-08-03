"""Hook hardening helpers for ShortScriptAgent (weak-opener strip)."""
from __future__ import annotations

import re

_WEAK_HOOK_STARTS = re.compile(
    r"^\s*("
    r"here'?s what|here is what|in this video|today we|welcome|"
    r"hey guys|let'?s talk|have you ever wondered|so you want to|"
    r"this video will|i'?m going to show you|did you know that today"
    r")\b",
    re.IGNORECASE,
)

EXTRA_LEAK_PATTERNS: list[str] = [
    r"here'?s what you need to know",
    r"in this short",
    r"welcome back",
]


def strengthen_hook(hook: str, full_script: str) -> str:
    """If the model returned a weak opener, try the first strong sentence of full_script."""
    hook = (hook or "").strip()
    if hook and not _WEAK_HOOK_STARTS.match(hook):
        return hook
    for sentence in re.split(r"(?<=[.!?])\s+", (full_script or "").strip()):
        s = sentence.strip()
        if len(s.split()) < 3:
            continue
        if _WEAK_HOOK_STARTS.match(s):
            continue
        if len(s.split()) <= 16:
            return s
    return hook
