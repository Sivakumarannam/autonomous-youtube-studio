SHORT_SCRIPT_SYSTEM_PROMPT = """You are an expert YouTube Shorts scriptwriter.
You write viral, engaging scripts for 15-30 second vertical videos (9:16).

Every script follows this exact 5-part RETENTION LOOP structure:
  1. HOOK       (0-3s)   — A bold curiosity-gap or challenge line. Use ONE of these proven formulas:
                           • "99% of people [can't do / get wrong / don't know] [thing]"
                           • "Your [teacher/boss/doctor] never told you [surprising fact]"
                           • "I tested [N] people on this — only [small number] got it right"
                           • "Stop [common mistake] — here's what to do instead"
                           • "This [thing] will change how you [relevant action] forever"
  2. INTRO      (3-6s)   — One line confirming the stakes: why this matters to the viewer right now.
  3. MAIN       (6-20s)  — Deliver 3-5 rapid-fire items. After item 2, add a pattern-interrupt tease:
                           "But wait — number [N] is the one nobody expects."
  4. OUTRO      (20-25s) — Payoff: the "best" item or surprising twist, held back until now.
  5. CTA        (25-28s) — Natural, low-friction call to action. Vary the phrasing each time
                           (e.g. "Follow for daily [niche] facts" / "Which one shocked you? Comment!" /
                           "Save this — you'll need it" / "Share with someone who needs to hear this").

Your scripts must have:
- A curiosity-gap HOOK that makes the viewer feel they'll miss out if they scroll
- Fast, punchy pacing — every word earns its place, zero filler
- A mid-video pattern interrupt that re-engages any viewer about to drop off
- A withheld payoff that rewards viewers who watch to the end
- One clear idea per video

Word count target: 65-75 words (never below 65, never above 75)
Speaking pace: approximately 155-165 words per minute (brisk, punchy pacing)

LOOP-ABLE ENDINGS: The last line of the CTA must connect thematically back
to the hook so that a viewer who re-watches immediately feels rewarded.
This creates the loop effect that drives multiple views per viewer on Shorts.

SEO TITLE RULE: Every Shorts title MUST end with or include "#Shorts".
Example: "This Python Trick Saves Hours #Shorts"

You must also produce complete SEO metadata: exactly 20-28 relevant tags
and at least 7 relevant hashtags per video — these are hard requirements,
not suggestions, and videos with fewer will be automatically rejected.
The hashtags array MUST include "#Shorts" as one of the entries.

CRITICAL — SPOKEN TEXT RULES:
The "hook", "intro", "main", "outro", "cta", and "full_script" fields are
read aloud by a text-to-speech engine and shown as on-screen captions.
They MUST contain ONLY the actual words a presenter would say out loud —
never a description of what the section is, never a label, never any part
of these instructions. If you find yourself writing something like "the
opening sentence that grabs attention" instead of an actual attention-
grabbing sentence, you have made a mistake — write the real words instead.

They MUST contain ONLY plain spoken English words. NEVER include in those
fields:
  - Emojis or symbols (🎵 🎻 ⚡ ✅ etc.)
  - Hashtags (#Shorts, #Tips, etc.)
  - URLs or links
  - Markdown formatting (**, __, ##, etc.)
  - Meta-commentary, labels, or instructions of any kind
Emojis and hashtags belong EXCLUSIVELY in the "hashtags" array and
"seo_description" field. Violating any of these rules ruins the video.

Always respond with valid JSON only. No markdown. No explanation."""


def build_short_script_prompt(
    topic_title: str,
    research_summary: str | None,
    key_facts: list[str],
    niche: str,
    language: str,
    rag_context: str | None = None,
) -> str:
    facts_section = ""
    if key_facts:
        facts_list = "\n".join(f"- {f}" for f in key_facts[:5])
        facts_section = f"\nKey facts to use:\n{facts_list}"

    research_section = ""
    if research_summary:
        research_section = f"\nResearch context:\n{research_summary[:500]}"

    rag_section = ""
    if rag_context:
        rag_section = f"\n{rag_context}"

    return f"""Write a YouTube Shorts script for this topic: "{topic_title}"

Channel niche: {niche}
Language: {language}{research_section}{facts_section}{rag_section}

Retention-loop structure (write REAL spoken words — never a label or description):
  1. hook   (0-3s)   — Curiosity-gap or challenge. E.g. "99% of people get [topic] wrong."
                       or "Your [authority] never told you this about [topic]."
  2. intro  (3-6s)   — Confirm the stakes in one line. Why this matters RIGHT NOW.
  3. main   (6-20s)  — 3-5 rapid-fire items. After item 2, add a pattern-interrupt:
                       "But number [N] is the one that surprises everyone." Then deliver it last.
  4. outro  (20-25s) — The withheld payoff/best item. Reward viewers who stayed.
  5. cta    (25-28s) — Vary phrasing each time: "Follow for daily {niche} facts" OR
                       "Which one shocked you? Comment below!" OR "Share this with someone who needs it."

Requirements:
- Total word count: 65-75 words (STRICT — target is 25-28 seconds at brisk TTS pace)
- Hook MUST open with an action verb, number, or provocative claim in the FIRST 3 WORDS.
  Bad: "Have you ever wondered…" Good: "99% of people…" / "Nobody tells you…" / "Stop doing this…"
- Hook must create a curiosity gap — viewer must feel they'll miss out if they scroll
- Pattern interrupt EVERY 5 seconds — a verbal or conceptual reset that re-grabs attention
  (e.g. sudden question, shocking stat, "But wait —", "Here's the twist:", "Most people miss this:")
- Withheld payoff in the outro that rewards full watch-through
- One key takeaway only
- LOOP-ABLE: last CTA line must echo the hook theme so re-watching feels intentional
- The conflict or problem must be fully stated within the first 3 seconds
- seo_title MUST include "#Shorts" (e.g. "The Truth About X #Shorts")
- Tags: EXACTLY 20 to 28 tags, all genuinely relevant to the topic and
  niche — include broad niche terms, specific topic terms, and related
  concepts. Do not repeat the title as separate tags. Do not pad with
  irrelevant filler — every tag must be a real, searchable term someone
  might use to find this video.
- Hashtags: AT LEAST 7 hashtags, relevant to the topic/niche, suitable for
  embedding in the YouTube description (e.g. #Shorts plus topic-specific
  hashtags).
- Description: must include a natural call-to-action (subscribe, like,
  comment, or share — phrase it naturally, not identically every time).

Below is a WORKED EXAMPLE for a completely different topic ("AI productivity
mistakes"), showing the exact tone and structure to follow. Do NOT reuse
any of this example's wording — it is only here to show you what real,
concrete spoken lines look like, as opposed to a description of a section.
Tags/hashtags arrays are SHORTENED here for illustration only — your actual
output must have 20-28 tags and at least 7 hashtags:

{{
  "hook": "You're making this common AI mistake every single day!",
  "intro": "Here's how to fix it in under twenty seconds.",
  "main": "First, stop copy-pasting the same prompt everywhere — it kills accuracy. Second, always give the AI real examples from your own work. Third, tell it who you are before every request. But number four is the one that surprises everyone.",
  "outro": "Ask the AI to check its own answer before you accept it. That single habit alone fixes most mistakes people make.",
  "cta": "Follow for more AI tips every day and save this for the next time you use AI!",
  "full_script": "You're making this common AI mistake every single day! Here's how to fix it in under twenty seconds. First, stop copy-pasting the same prompt everywhere — it kills accuracy. Second, always give the AI real examples from your own work. Third, tell it who you are before every request. But number four is the one that surprises everyone. Ask the AI to check its own answer before you accept it. That single habit alone fixes most mistakes people make. Follow for more AI tips every day and save this for the next time you use AI!",
  "word_count": 70,
  "estimated_duration_seconds": 27,
  "seo_title": "This AI Mistake Is Costing You Time",
  "seo_description": "Most people use AI wrong — here's the 3-step fix that actually works. Save this for later!",
  "tags": ["ai productivity", "ai mistakes", "chatgpt tips", "ai prompts", "productivity hacks", "... 20 to 28 total tags ..."],
  "hashtags": ["#AI", "#Productivity", "#Shorts", "#TechTips", "#AIHacks", "#WorkSmarter", "#LifeHacks", "... at least 7 total ..."]
}}

Now write a NEW script for the actual topic given above ("{topic_title}"),
following the same structure and tone, but with entirely original spoken
lines you write yourself for this specific topic. Return ONLY valid JSON
in the exact same shape as the example. JSON only. No markdown."""


def build_short_seo_prompt(topic: str, script: str, niche: str) -> str:
    return f"""Generate SEO metadata for this YouTube Shorts video:

Topic: {topic}
Niche: {niche}
Script excerpt: {script[:300]}

Requirements:
- Tags: EXACTLY 20 to 28 relevant tags.
- Hashtags: AT LEAST 7 relevant hashtags.
- Description: 100-150 chars, must include a natural call-to-action.

Return JSON:
{{
  "seo_title": "title under 60 chars",
  "seo_description": "description 100-150 chars with a call-to-action",
  "tags": ["... 20 to 28 tags total ..."],
  "hashtags": ["#Shorts", "... at least 7 hashtags total ..."]
}}

JSON only."""