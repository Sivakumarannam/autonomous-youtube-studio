RESEARCH_SYSTEM_PROMPT = """You are an expert research analyst and content researcher for YouTube creators.
Your job is to deeply research topics and extract the most valuable, accurate, and engaging information.

You focus on:
- Factual accuracy and credibility
- Audience-relevant insights
- Compelling angles and talking points
- Actionable information

Always respond with valid JSON only. No markdown. No preamble."""


def build_research_prompt(
    topic_title: str,
    topic_description: str | None,
    niche: str,
    language: str,
) -> str:
    description_clause = f"\nTopic description: {topic_description}" if topic_description else ""

    return f"""Research the following YouTube video topic thoroughly:

Topic: "{topic_title}"{description_clause}
Channel niche: {niche}
Target language: {language}

Conduct comprehensive research and provide:
1. A clear, engaging summary (2-3 paragraphs)
2. 8-12 key facts and statistics
3. 3-5 reliable reference sources
4. 5-7 unique talking points and content angles
5. Target audience profile
6. Difficulty/complexity level

Return ONLY valid JSON in this exact structure:
{{
  "summary": "2-3 paragraph comprehensive summary...",
  "key_facts": [
    "Fact 1 with specific data or statistic",
    "Fact 2 ...",
    ...
  ],
  "references": [
    "Official documentation or authoritative source",
    "Academic or industry report",
    ...
  ],
  "talking_points": [
    "Unique angle: how beginners often misunderstand X",
    "Comparison: X vs Y performance benchmark",
    ...
  ],
  "target_audience": "Description of who benefits most from this content",
  "difficulty_level": "beginner"
}}

Ensure all facts are accurate and up to date. Return JSON only."""


def build_fact_extraction_prompt(raw_content: str, topic: str) -> str:
    return f"""Extract key facts and insights from this research content about "{topic}":

{raw_content[:3000]}

Return JSON with:
{{
  "key_facts": ["fact 1", "fact 2", ...],
  "talking_points": ["point 1", "point 2", ...]
}}

JSON only."""