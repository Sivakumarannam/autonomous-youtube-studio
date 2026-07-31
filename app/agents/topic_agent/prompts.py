TOPIC_SYSTEM_PROMPT = """You are an expert YouTube content strategist and trend analyst.
Your job is to identify high-potential YouTube topics that will get maximum views and engagement.

You analyze trends from multiple sources and score topics based on:
- Current search volume and trending momentum
- Competition level (lower is better)
- Audience interest and engagement potential
- Relevance to the channel niche
- Viral potential

Always respond with valid JSON only. No markdown. No explanation."""


from datetime import datetime


def build_topic_generation_prompt(
    niche: str,
    count: int,
    language: str,
    content_type: str,
    sources: list[str],
) -> str:
    content_guidance = {
        "short": "YouTube Shorts (under 60 seconds, punchy, hook-driven)",
        "long": "long-form YouTube videos (8-10 minutes, educational, in-depth)",
        "both": "both YouTube Shorts and long-form videos",
    }.get(content_type, "YouTube videos")

    # Resolve the real current date at prompt-build time rather than letting
    # the LLM guess from training data (which produced stale years like
    # "...in 2024" long after 2024 had passed). No year is hardcoded here —
    # datetime.now() always reflects the server's actual current date, so
    # this keeps working correctly in 2027, 2028, and beyond with no
    # further changes.
    today = datetime.now()
    current_date_str = today.strftime("%B %d, %Y")
    current_year = today.year

    return f"""Today's date is {current_date_str}. Generate {count} trending YouTube topic ideas for a channel in the niche: "{niche}".

Content format: {content_guidance}
Language: {language}
Sources to consider: {", ".join(sources)}

IMPORTANT: Use {current_year} (the current year) in any topic title or content that references a year. Do not reference past years as if they were current or upcoming.

For each topic, analyze:
1. Current trending momentum (Google Trends, YouTube search)
2. Audience pain points and questions
3. Competition gap opportunities
4. Viral and shareable potential

Respond ONLY with a valid JSON array. Each object must have:
- "topic": string (the exact video title, SEO-optimized, compelling)
- "score": number (0-100, trending score — 90+ means extremely hot)
- "reason": string (one sentence why this will perform well)
- "keywords": array of strings (5-8 target keywords)
- "content_type": string ("short", "long", or "both")

Example format:
[
  {{
    "topic": "Docker vs Kubernetes: Which One Should You Use This Year?",
    "score": 95,
    "reason": "High search volume, beginner confusion drives clicks, comparison content gets 3x more views",
    "keywords": ["docker", "kubernetes", "devops", "containers", "docker tutorial"],
    "content_type": "long"
  }}
]

Generate exactly {count} topics. Prioritize topics scoring above 75. Return JSON array only."""


def build_trend_enrichment_prompt(topics: list[str], niche: str) -> str:
    topic_list = "\n".join(f"- {t}" for t in topics)
    return f"""Given these potential YouTube topics for the "{niche}" niche:

{topic_list}

Score each topic and add enrichment data. Return a JSON array with these fields per topic:
- "topic": original topic string
- "score": 0-100 trending score
- "reason": one-sentence explanation
- "keywords": list of 5-8 SEO keywords
- "content_type": "short", "long", or "both"

Return JSON array only. No markdown."""