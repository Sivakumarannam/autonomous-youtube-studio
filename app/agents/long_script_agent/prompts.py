LONG_SCRIPT_SYSTEM_PROMPT = """You are an expert YouTube scriptwriter specializing in long-form educational content.
You write engaging, well-structured scripts for 8-10 minute videos (16:9, 1920x1080).
Videos MUST be at least 8 minutes 5 seconds long to qualify for YouTube mid-roll ads.

Your scripts must have:
- A powerful hook in the first 30 seconds
- Clear structure: Intro → Main sections → Examples → Conclusion → CTA
- Conversational tone — like talking to a friend
- MINIMUM 3 pattern interrupts spread across the video (every 90-120 seconds).
  Each interrupt must be a short re-engagement line like:
  "But here's the part most people never figure out..."
  "Wait — before we go further, this next part changes everything."
  "I saved the most surprising one for right here..."
- A forward-tease every 90 seconds: "Coming up in a moment — [topic hint] that most people get completely wrong."
- Specific examples, analogies, and data points
- Strong SEO alignment in the first 60 seconds

Word count target: 2000-2400 words (STRICT — this is required for 8-10 minutes; fewer than 2000 words will be rejected)
Pacing: ~160-175 words per minute (conversational, brisk TTS delivery)

You must also produce complete SEO metadata: exactly 20-28 relevant tags
and at least 7 relevant hashtags per video — these are hard requirements,
not suggestions, and videos with fewer will be automatically rejected.

CRITICAL — SPOKEN TEXT RULES:
The "hook", "introduction", "sections[].content", "conclusion", "cta",
and "full_script" fields are read aloud by a text-to-speech engine.
They MUST contain ONLY plain spoken English words.
NEVER include in those fields:
  - Emojis or symbols (🎵 🎻 ⚡ ✅ etc.)
  - Hashtags (#Shorts, #Tips, etc.)
  - URLs or links
  - Markdown formatting (**, __, ##, etc.)
Emojis and hashtags belong EXCLUSIVELY in the "hashtags" array and
"seo_description" field. Violating this rule ruins the audio.

Always respond with valid JSON only. No markdown. No explanation."""

def build_long_script_prompt(
    topic_title: str,
    research_summary: str | None,
    key_facts: list[str],
    talking_points: list[str],
    niche: str,
    language: str,
    rag_context: str | None = None,
) -> str:
    facts_block = ""
    if key_facts:
        facts_block = "\nKey facts to incorporate:\n" + "\n".join(f"- {f}" for f in key_facts[:10])

    points_block = ""
    if talking_points:
        points_block = "\nTalking points:\n" + "\n".join(f"- {p}" for p in talking_points[:7])

    research_block = ""
    if research_summary:
        research_block = f"\nResearch summary:\n{research_summary[:800]}"

    rag_block = ""
    if rag_context:
        rag_block = f"\n{rag_context}"

    return f"""Write a complete YouTube long-form video script for: "{topic_title}"

Channel niche: {niche}
Language: {language}{research_block}{facts_block}{points_block}{rag_block}

Script requirements:
- Total: 2000-2400 words (STRICT — this maps to 8-10 minutes at 165 wpm; fewer than 2000 words will be rejected; videos under 8 min 5 s lose mid-roll ad revenue)
- Hook: First sentence must be fascinating or controversial (gets immediate attention)
- Introduction: 150-200 words (hook + what viewer will learn + why it matters)
- 4-5 main sections with clear titles
- Each section: 300-400 words with examples, stories, and data points
- MINIMUM 3 pattern interrupts placed naturally across sections (not all in one place).
  Mark each one with the tag [PI] at the start so they are easy to count.
  Example lines: "[PI] But here's the part most people never figure out..."
  "[PI] Wait — this next point changes everything." "[PI] I saved the best one for right here..."
- A forward-tease at the end of sections 1, 2, and 3: a one-sentence preview of what's next.
- Conclusion: 150-200 words summarizing key takeaways
- MID-VIDEO SUBSCRIBE CTA: at approximately the 4-minute mark (inside section 3 or between sections 2-3),
  insert one natural spoken line asking the viewer to subscribe. Example:
  "If you're finding this useful, hit subscribe — I put out videos like this every week."
  Do NOT place this in the intro or outro — it must appear mid-video.
- CTA (outro): 75-100 words asking to like, subscribe, comment with a specific question to reply to
- Tags: EXACTLY 20 to 28 tags, all genuinely relevant to the topic. Do not repeat the title as separate tags. Do not pad with irrelevant filler.
- Hashtags: AT LEAST 7 hashtags, relevant to the topic/niche.
- Description: first two sentences must be the most compelling hook text (shown before "Show more"). Include a natural call-to-action.
- chapter_timestamps: generate a "chapter_timestamps" field as a list of objects with "time" (format "00:00") and "title".
  Chapter titles MUST be curiosity-driven — not generic labels. Bad: "Section 1". Good: "The Mistake Everyone Makes".
  Always start with "00:00 Introduction". This will be appended to the YouTube description for navigation.

Return ONLY valid JSON. Note the tags/hashtags arrays below are SHORTENED
for illustration only — your actual output must have 20-28 tags and at
least 7 hashtags, following this exact structure:
{{
  "hook": "The single opening sentence — powerful, surprising, or thought-provoking",
  "introduction": "Full introduction paragraph 100-150 words...",
  "sections": [
    {{
      "title": "Section 1 Title",
      "content": "Section content 200-300 words with examples...",
      "duration_seconds": 120
    }},
    {{
      "title": "Section 2 Title",
      "content": "Section content...",
      "duration_seconds": 120
    }},
    {{
      "title": "Section 3 Title",
      "content": "Section content...",
      "duration_seconds": 120
    }}
  ],
  "conclusion": "Conclusion 100-150 words...",
  "cta": "Call to action 50-75 words...",
  "full_script": "Complete script as one continuous text — intro + all sections + conclusion + cta",
  "word_count": 2100,
  "estimated_duration_seconds": 505,
  "seo_title": "SEO-optimized title under 70 chars with primary keyword and power word (e.g. Secret, Finally, Nobody Tells You) + current year",
  "seo_description": "FIRST TWO SENTENCES must be the hook (shown before Show More). Then keywords + call-to-action. 150-300 chars total.",
  "tags": ["keyword1", "keyword2", "keyword3", "... 20 to 28 total tags ..."],
  "hashtags": ["#Niche", "#Tag1", "#Tag2", "... at least 7 total ..."],
  "thumbnail_concept": "Brief description of what the thumbnail should show — bold 3-word text, high-contrast color, subject or emotion",
  "chapter_timestamps": [
    {{"time": "00:00", "title": "Introduction"}},
    {{"time": "01:30", "title": "Section 1 Title"}},
    {{"time": "03:00", "title": "Section 2 Title"}},
    {{"time": "04:30", "title": "Section 3 Title"}},
    {{"time": "06:00", "title": "Conclusion"}}
  ]
}}

JSON only. Generate a complete, ready-to-record script."""

def build_long_seo_prompt(topic: str, script_excerpt: str, niche: str) -> str:
    return f"""Generate SEO metadata for this YouTube video:

Topic: {topic}
Niche: {niche}
Script excerpt: {script_excerpt[:500]}

Requirements:
- Tags: EXACTLY 20 to 28 relevant tags.
- Hashtags: AT LEAST 7 relevant hashtags.
- Description: 150-300 chars, must include a natural call-to-action.

Return JSON:
{{
  "seo_title": "title under 70 chars",
  "seo_description": "description 150-300 chars with a call-to-action",
  "tags": ["... 20 to 28 tags total ..."],
  "hashtags": ["#Tag1", "... at least 7 hashtags total ..."]
}}

JSON only."""