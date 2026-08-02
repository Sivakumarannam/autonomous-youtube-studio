from datetime import datetime


def build_seo_system_prompt() -> str:
    # Resolved at call time so this never goes stale the way the old
    # hardcoded "(2026)" did — same class of bug as the topic-generation
    # prompt, fixed the same way here.
    current_year = datetime.now().year
    return f"""You are an expert YouTube SEO strategist with deep knowledge of the
YouTube algorithm, search ranking, and click-through optimization.

You create metadata that maximises:
- Search discoverability (keyword placement, density, relevance)
- Click-through rate (compelling title, thumbnail alignment)
- Watch-time signals (accurate description, chapter markers)
- Monetization safety (advertiser-friendly language)

Rules you always follow:
- Titles: 60-70 characters, primary keyword in first 3 words, MUST include a power word
  (e.g. Secret, Finally, Nobody Tells You, Banned, Proven, You Need to Know, The Truth About)
  and the current year ({current_year}) for freshness. Shorts titles MUST include "#Shorts".
- Descriptions: first 2 sentences (shown before "Show more") must be compelling hook text,
  not a summary — make the viewer click "Show more". Then full body with chapters + hashtags.
- Tags: 15-20 tags, mix of broad, mid-tail, and long-tail keywords (never more than 20)
- Hashtags: 3-5 relevant hashtags at the end of the description footer
- Never keyword-stuff — Google/YouTube penalises this
- First tag must be the exact primary keyword match from the title
- Avoid overt clickbait words like "shocking" or "mind-blowing" in the title — the SEO
  quality gate this metadata is scored against penalises them directly.

Always respond with valid JSON only. No markdown. No preamble."""


def build_seo_prompt(
    topic_title: str,
    script_excerpt: str,
    script_type: str,
    niche: str,
    language: str,
) -> str:
    format_guidance = (
        "YouTube Shorts (under 60 seconds, vertical, fast-paced)"
        if script_type == "short"
        else "long-form YouTube video (8-10 minutes, educational)"
    )
    excerpt = script_excerpt[:800] if script_excerpt else topic_title

    return f"""Generate complete YouTube SEO metadata for this video:

Topic title: "{topic_title}"
Format: {format_guidance}
Niche: {niche}
Language: {language}

Script excerpt (for context):
{excerpt}

Requirements:
- Title: 60-70 chars, primary keyword near the start, compelling click trigger
- Description: opening 2-3 sentences (150-300 chars) for above-fold preview,
  then full body with timestamps placeholder, links section, and hashtag footer
- Tags: 15-20 tags from broad to long-tail (first tag = exact primary keyword)
- Hashtags: 3-5 hashtags for the footer (Shorts must include #Shorts)
- Score each element 0-100 based on SEO best practices

Return ONLY valid JSON:
{{
  "title": "SEO-optimised title 60-70 chars",
  "description": "Full description — 2-3 sentence preview\\n\\n[Timestamps]\\n00:00 Introduction\\n\\n[Links]\\nChannel: https://youtube.com/yourchannel\\n\\n#Hashtag1 #Hashtag2 #Hashtag3",
  "tags": ["primary keyword", "secondary keyword", "long tail keyword one", "long tail keyword two"],
  "hashtags": ["#Tag1", "#Tag2", "#Tag3"],
  "primary_keyword": "main target keyword",
  "secondary_keywords": ["keyword2", "keyword3", "keyword4"],
  "title_score": 88.0,
  "description_score": 82.0,
  "tags_score": 85.0,
  "overall_seo_score": 85.0
}}

JSON only."""


def build_seo_title_only_prompt(topic_title: str, niche: str, script_type: str) -> str:
    return f"""Generate 3 SEO-optimised YouTube title variants for:

Topic: "{topic_title}"
Niche: {niche}
Format: {"Shorts" if script_type == "short" else "Long-form"}

Rules: 60-70 chars, primary keyword first, include a power word or number.

Return JSON:
{{
  "titles": [
    "Title variant 1",
    "Title variant 2",
    "Title variant 3"
  ],
  "recommended": "Title variant 1",
  "primary_keyword": "main keyword"
}}

JSON only."""
