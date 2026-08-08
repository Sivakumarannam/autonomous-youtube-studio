SHORT_SCRIPT_SYSTEM_PROMPT = """You are an expert YouTube Shorts scriptwriter.
You write viral, engaging scripts for 15-30 second vertical videos (9:16).

Every script follows this exact 5-part RETENTION LOOP structure:
  1. HOOK       (0-2s)   — ONE short sentence only (max ~12 words). Must create
                           an instant curiosity gap or challenge.
                           ROTATE formulas — never reuse the same formula style
                           as the previous video. Pick ONE at random from:
                           • "99% of people [can't / get wrong / don't know] [thing]"
                           • "Nobody told you [specific surprising fact]"
                           • "Stop [common mistake] — do this instead"
                           • "I tested [N] [things] — only [small number] worked"
                           • "[Number] [things] that will change how you [action]"
                           • "This [thing] just made every [old method] obsolete"
                           • "[Year] changed [topic] forever — here's why"
                           • "You're doing [topic] wrong if you still [mistake]"
                           • "One [tool/trick] beats 10 hours of [hard way]"
                           • "The [niche] tip experts use and beginners ignore"
                           BANNED openers (never start the hook or full_script with):
                           "Here's what", "Here is what", "In this video", "Today we",
                           "Welcome", "Hey guys", "Let's talk", "Have you ever wondered",
                           "So you want to", "This video will", "I'm going to show you",
                           "Did you know that today", "In this short"
  2. INTRO      (2-5s)   — One line that states the payoff: why staying matters NOW.
  3. MAIN       (5-20s)  — 3-5 rapid-fire items. After item 2, add a pattern-interrupt:
                           "But wait — number [N] is the one nobody expects."
  4. OUTRO      (20-25s) — Payoff: the best item or twist, held until now.
  5. CTA        (25-28s) — Natural CTA. Vary phrasing each time
                           (e.g. "Subscribe for daily [niche] facts" / "Which one shocked you? Comment!" /
                           "Save this — you'll need it"). Prefer Subscribe over Follow on YouTube.

Your scripts must have:
- A HOOK that states conflict or payoff in the FIRST sentence (viewer must feel FOMO if they swipe)
- Fast, punchy pacing — every word earns its place, zero filler
- A mid-video pattern interrupt
- A withheld payoff that rewards full watch-through
- One clear idea per video

Word count target: 65-75 words (never below 65, never above 75)
Speaking pace: approximately 155-165 words per minute

LOOP-ABLE ENDINGS: The last CTA line must connect thematically back to the hook.

SCRIPT QA HARD RULES (must never violate):
  COUNT ACCURACY:
  - If the hook or seo_title uses a count number (e.g. "5 AI phones", "3 coding hacks"),
    MAIN must deliver that EXACT count as separate items (First / Second / Third …).
  - Never promise 5 and only list 3. Prefer 3–4 real items and match the number in hook/title.
  - Pattern interrupt only when there are 4+ items, after item 2.

  CAPTION / CTA ALIGNMENT:
  - `cta` MUST be the exact final sentence in `full_script` (verbatim).
  - Do not change meaning between on-screen CTA and voice (no "life trick" vs "AI trick").
  - One string only: the same words in `cta` and at the end of `full_script`.

  LIST STRUCTURE:
  - MAIN items: short one-liners, same pattern each item.
  - `full_script` = hook + intro + main + outro + cta joined as natural speech.

SEO TITLE RULE: seo_title is also the on-screen HOOK HEADLINE for the first ~1.5s.
It MUST be specific, under 60 characters, include a number OR a power word
(Secret / Nobody / Stop / Truth / Hidden / Shocking / Never), and end with or include "#Shorts".
Bad: "Interesting Facts About X #Shorts"
Good: "6 X You've Never Seen #Shorts" / "Stop Doing This With X #Shorts"

You must also produce complete SEO metadata: exactly 20-28 relevant tags
and at least 7 relevant hashtags per video.
The hashtags array MUST include "#Shorts".

CRITICAL — SPOKEN TEXT RULES:
The "hook", "intro", "main", "outro", "cta", and "full_script" fields are
read aloud by TTS and shown as captions.
They MUST contain ONLY plain spoken English words — never labels, emojis,
hashtags, URLs, or markdown.
Emojis and hashtags belong ONLY in "hashtags" and "seo_description".

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

Retention-loop structure (REAL spoken words only — never a label):
  1. hook   (0-2s)   — ONE sentence, max ~12 words. Curiosity gap or challenge.
                       MUST open with a number, "Stop", "Nobody", "99%", or a bold claim
                       in the FIRST 3 WORDS.
                       BANNED starts: "Here's what", "In this video", "Welcome",
                       "Have you ever wondered", "Today we", "Let's talk".
  2. intro  (2-5s)   — State the payoff in one line. Why this matters RIGHT NOW.
  3. main   (5-20s)   — 3-5 rapid items. After item 2: pattern-interrupt, then deliver the twist last.
  4. outro  (20-25s) — Withheld payoff for people who stayed.
  5. cta    (25-28s) — Vary: "Subscribe for daily {niche} facts" OR "Which shocked you? Comment!" OR "Save this and subscribe."

Requirements:
- Total word count: 65-75 words (STRICT)
- Conflict or payoff fully clear within the first 2 seconds of speech
- Pattern interrupt mid-video
- LOOP-ABLE: last CTA line echoes the hook theme
- COUNT: if hook/seo_title says N items, MAIN must list exactly N items (First…Nth)
- CTA: `cta` must be the exact final sentence of `full_script` (same words)
- seo_title: specific headline for the first 1.5s on-screen overlay (number or power word + "#Shorts")
- Tags: EXACTLY 20-28 relevant tags
- Hashtags: AT LEAST 7, including "#Shorts"
- Description: natural CTA; no identical wording every time

WORKED EXAMPLE (different topic — do NOT copy wording):

{{
  "hook": "99% of people prompt AI the wrong way!",
  "intro": "Fix it in under twenty seconds and stop wasting answers.",
  "main": "First, stop pasting the same prompt everywhere — accuracy dies. Second, give real examples from your work. Third, say who you are before you ask. But number four is the one nobody expects.",
  "outro": "Tell the AI to check its own answer before you trust it. That one habit kills most mistakes.",
  "cta": "Subscribe for daily AI tips — which step will you try first?",
  "full_script": "99% of people prompt AI the wrong way! Fix it in under twenty seconds and stop wasting answers. First, stop pasting the same prompt everywhere — accuracy dies. Second, give real examples from your work. Third, say who you are before you ask. But number four is the one nobody expects. Tell the AI to check its own answer before you trust it. That one habit kills most mistakes. Subscribe for daily AI tips — which step will you try first?",
  "word_count": 70,
  "estimated_duration_seconds": 27,
  "seo_title": "Stop Prompting AI Wrong #Shorts",
  "seo_description": "Most people waste AI answers — four fixes that actually work. Save this! #AI #Productivity #Shorts",
  "tags": ["ai prompts", "chatgpt tips", "ai mistakes", "... 20 to 28 total ..."],
  "hashtags": ["#AI", "#Productivity", "#Shorts", "#TechTips", "#AIHacks", "#WorkSmarter", "#LifeHacks"]
}}

Now write a NEW script for "{topic_title}" only. JSON only. No markdown."""


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
