QUALITY_SYSTEM_PROMPT = """You are a senior YouTube content quality reviewer with expertise in
scriptwriting, SEO, audience psychology, and platform best practices.

You evaluate scripts across seven dimensions and provide actionable feedback.
Your scores are calibrated, honest, and consistent — you never inflate scores.

Scoring guidelines:
  90-100: Exceptional, publish immediately
  75-89:  Good, minor improvements welcome
  60-74:  Acceptable, specific issues to address
  40-59:  Needs rework, significant problems
  0-39:   Reject, fundamental issues

Always respond with valid JSON only. No markdown. No preamble."""


def build_quality_prompt(
    script_content: str,
    script_type: str,
    topic_title: str,
    niche: str,
    word_count: int,
    min_score: int = 70,
) -> str:
    format_context = (
        "YouTube Shorts (target: 65-75 words, 25-28 seconds, 9:16)"
        if script_type == "short"
        else "long-form YouTube video (target: 2000-2400 words, 8-10 minutes, 16:9 — minimum 8 min 5 s for mid-roll ads)"
    )
    excerpt = script_content[:1500]

    return f"""Review this YouTube script and score each quality dimension:

Topic: "{topic_title}"
Format: {format_context}
Niche: {niche}
Word count: {word_count}

Script:
---
{excerpt}
---

Score each dimension 0-100 and explain your reasoning:

1. grammar_score — spelling, grammar, punctuation, sentence structure
2. fact_consistency_score — accuracy, no contradictions, claims are plausible
3. engagement_score — hook strength, pacing, pattern interrupts, curiosity gaps.
   Checklist (deduct points for each failure):
   - Hook opens with an action verb, number, or bold claim in the FIRST 3 WORDS: -10 if missing
   - The core conflict or problem is fully stated within the first 3 seconds: -10 if missing
   - For long-form: MUST contain at least 3 distinct [PI]-tagged pattern interrupt lines
     (re-engagement phrases). Deduct 15 points if fewer than 3 are present.
   - For long-form: a mid-video subscribe CTA appears around the 4-minute mark: -5 if missing
   - CTA ends with a SPECIFIC question for viewers to answer in comments (not generic "like & sub"): -5 if missing
4. retention_score — will viewers watch to the end? smooth transitions?
5. seo_score — keyword usage, title alignment, searchability signals.
   Title must contain: a power word (Secret/Finally/Nobody/Banned/Shocking/Hidden/Revealed/Truth) OR
   a number OR a year (2025/2026). Deduct 10 if none of these are present.
6. uniqueness_score — original angle, not generic, not duplicated content
7. readability_score — conversational tone, clear language, appropriate complexity

Minimum passing score: {min_score}/100 overall average.

Return ONLY valid JSON:
{{
  "grammar_score": 88.0,
  "fact_consistency_score": 82.0,
  "engagement_score": 85.0,
  "retention_score": 78.0,
  "seo_score": 80.0,
  "uniqueness_score": 75.0,
  "readability_score": 90.0,
  "overall_score": 82.6,
  "passed": true,
  "feedback": "Strong script with good structure. Hook is compelling. Consider adding a stat in the intro.",
  "improvement_suggestions": [
    "Add a specific statistic in the first 30 seconds",
    "The third section could use a concrete example",
    "CTA could be more specific — tell viewers exactly what to comment"
  ],
  "rejection_reason": null
}}

If overall_score < {min_score}, set passed=false and provide a rejection_reason string.
JSON only."""