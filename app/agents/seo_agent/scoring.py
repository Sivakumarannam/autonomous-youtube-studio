"""
Rule-based SEO scoring gate.

Scores already-stored Script SEO metadata against four deterministic criteria
(title quality, description quality, inline hashtag count, tag list count).
Returns a float 0–100.  No LLM calls; never retryable.

Criterion weights
─────────────────
  Title        25 pts  (length 60-70, no clickbait, keyword in title)
  Description  25 pts  (CTA presence, minimum length ≥ 100 chars)
  Hashtags     25 pts  (≥ 7 #word tokens embedded in description text)
  Tags         25 pts  (20–28 items in seo_tags JSON list)
  ─────────────────────
  Total        100 pts

Gate threshold: settings.seo_min_score (default 60).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# Phrase lists
# ---------------------------------------------------------------------------

_CLICKBAIT_PHRASES: tuple[str, ...] = (
    "you won't believe",
    "you will not believe",
    "shocking",
    "mind blowing",
    "mind-blowing",
    "this will change your life",
    "secret revealed",
    "they don't want you to know",
    "they do not want you to know",
    "click here",
    "you need to see this",
    "jaw dropping",
    "jaw-dropping",
    "epic fail",
    "gone wrong",
    "gone viral",
    "insane trick",
    "one weird trick",
    "number one trick",
)

_CTA_PHRASES: tuple[str, ...] = (
    "subscribe",
    "like and subscribe",
    "comment below",
    "leave a comment",
    "share this",
    "follow us",
    "follow for more",
    "follow for daily",
    "follow me for",
    "hit the bell",
    "notification bell",
    "click the link",
    "link in bio",
    "link in description",
    "check out",
    "don't forget to",
    "do not forget to",
    "let us know",
    "sign up",
    "join us",
    "visit our",
    "watch more",
    "watch till",
    "watch until",
    "learn more",
    "drop a comment",
    "drop a like",
    "hit like",
    "smash like",
    "save this",
    "save for later",
    "share with",
    "what do you think",
    "stay tuned",
    "tap follow",
    "turn on",
    "turn notifications",
)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class SeoScoreBreakdown:
    """Per-dimension scores (0–25 each) and diagnostic flags."""

    title_score: float = 0.0        # 0–25
    description_score: float = 0.0  # 0–25
    hashtag_score: float = 0.0      # 0–25
    tags_score: float = 0.0         # 0–25
    total: float = 0.0              # 0–100

    # Diagnostics (useful for logging and test assertions)
    title_length: int = 0
    has_clickbait: bool = False
    has_keyword_in_title: bool = False
    has_cta: bool = False
    description_length: int = 0
    hashtag_count: int = 0
    tag_count: int = 0


# ---------------------------------------------------------------------------
# Scoring function
# ---------------------------------------------------------------------------

def score_seo_metadata(
    seo_title: Optional[str],
    seo_description: Optional[str],
    seo_tags_json: Optional[str],
    hashtags_json: Optional[str],
) -> SeoScoreBreakdown:
    """Score the four SEO metadata fields deterministically.

    Parameters mirror the Script model columns:
      seo_title        — plain string (YouTube video title)
      seo_description  — plain string; may contain embedded #hashtags
      seo_tags_json    — JSON-serialised ``list[str]`` of YouTube tags
      hashtags_json    — JSON-serialised ``list[str]``; used to build the
                         keyword pool for the title keyword check

    Returns a :class:`SeoScoreBreakdown` with per-dimension scores and
    boolean diagnostic flags.  Never raises.
    """
    result = SeoScoreBreakdown()

    title = (seo_title or "").strip()
    description = (seo_description or "").strip()

    tags: list[str] = _parse_json_list(seo_tags_json)
    hashtags: list[str] = _parse_json_list(hashtags_json)

    # ── Title (0–25) ────────────────────────────────────────────────────────
    title_lower = title.lower()
    result.title_length = len(title)

    # Length sub-score (0–10): optimal 60–70 chars
    if 60 <= len(title) <= 70:
        length_pts = 10.0
    elif 45 <= len(title) <= 85:
        length_pts = 5.0
    else:
        length_pts = 0.0

    # Clickbait sub-score (0–8)
    result.has_clickbait = any(p in title_lower for p in _CLICKBAIT_PHRASES)
    clickbait_pts = 0.0 if result.has_clickbait else 8.0

    # Keyword sub-score (0–7): ≥ 1 meaningful word from tags/hashtags in title
    keyword_words: set[str] = {
        word.lower()
        for tag in (tags + hashtags)
        for word in re.split(r"[\s_#\-]+", tag)
        if len(word) > 3
    }
    result.has_keyword_in_title = bool(
        keyword_words and any(w in title_lower for w in keyword_words)
    )
    keyword_pts = 7.0 if result.has_keyword_in_title else 0.0

    result.title_score = length_pts + clickbait_pts + keyword_pts

    # ── Description (0–25) ──────────────────────────────────────────────────
    desc_lower = description.lower()
    result.description_length = len(description)

    # CTA sub-score (0–15)
    result.has_cta = any(p in desc_lower for p in _CTA_PHRASES)
    cta_pts = 15.0 if result.has_cta else 0.0

    # Length sub-score (0–10): at least 100 chars
    length_desc_pts = 10.0 if len(description) >= 100 else 0.0

    result.description_score = cta_pts + length_desc_pts

    # ── Hashtags (0–25): #word tokens embedded in description text ──────────
    inline_hashtags = re.findall(r"#\w+", description)
    result.hashtag_count = len(inline_hashtags)

    if result.hashtag_count >= 7:
        result.hashtag_score = 25.0
    elif result.hashtag_count >= 4:
        result.hashtag_score = 15.0
    elif result.hashtag_count >= 1:
        result.hashtag_score = 8.0
    else:
        result.hashtag_score = 0.0

    # ── Tags (0–25): count of items in seo_tags JSON list ───────────────────
    result.tag_count = len(tags)

    if 20 <= result.tag_count <= 28:
        result.tags_score = 25.0
    elif 15 <= result.tag_count <= 35:
        result.tags_score = 15.0
    else:
        result.tags_score = 0.0

    result.total = (
        result.title_score
        + result.description_score
        + result.hashtag_score
        + result.tags_score
    )
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_json_list(raw: Optional[str]) -> list[str]:
    """Parse a JSON-encoded list[str]; return [] on any error."""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if item]
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return []
