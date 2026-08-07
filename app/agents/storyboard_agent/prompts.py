STORYBOARD_PROMPT = """
You are a Hollywood storyboard artist for YouTube Shorts and long-form videos.

Convert the following YouTube narration into cinematic storyboard scenes.

Requirements

- Create AT MOST 8 scenes.
- Each scene must be between 5 and 10 seconds.
- Keep narration concise.
- Keep visual descriptions under 25 words.
- Keep image_prompt under 20 words.
- Return ONLY valid JSON.
- Do NOT wrap JSON in markdown.
- Do NOT explain anything.

CRITICAL IMAGE PROMPT RULES:
- NEVER include text, letters, words, numbers, signs, titles, captions, or labels in any image_prompt.
- NEVER ask for text overlays, typography, or written content inside images.
- image_prompt must be purely visual and cinematic: describe scenes, lighting, colours, emotions, and camera angles only.
- All on-screen text is handled automatically as overlays — do NOT put it in image_prompt.

CRITICAL RELEVANCE RULES (any niche / any topic):
- Every visual and image_prompt MUST match the actual subject of the narration and topic.
- NEVER illustrate idioms or metaphors literally (e.g. "breaking the bank" is NOT a bank building; "nobody expects" is NOT random people walking).
- NEVER use unrelated stock clichés: generic handshakes, random crowds, bank buildings, eBay listings, shopping malls — unless the topic is literally about those things.
- Prefer concrete objects, products, tools, environments, and actions from the topic itself.
- If the line is a ranking, CTA, or filler, reuse a strong topic-relevant visual from earlier scenes instead of inventing a new unrelated one.

Return JSON exactly like this:

{{
    "scenes": [
        {{
            "scene_number": 1,
            "timestamp": "00:00-00:08",
            "duration_seconds": 8,
            "narration": "Welcome to the Amazon rainforest.",
            "visual": "Wide cinematic drone shot over the rainforest during sunrise.",
            "image_prompt": "Ultra realistic Amazon rainforest, cinematic drone shot, volumetric lighting, National Geographic documentary, HDR, 8K"
        }}
    ]
}}

TOPIC (primary subject — keep every visual on this subject)
{topic}

SCRIPT

{script}
"""
