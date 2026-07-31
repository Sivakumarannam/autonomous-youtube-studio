STORYBOARD_PROMPT = """
You are a Hollywood storyboard artist.

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

SCRIPT

{script}
"""