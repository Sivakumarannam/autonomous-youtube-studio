THUMBNAIL_SYSTEM_PROMPT = """You are an expert YouTube thumbnail designer with deep knowledge of
click-through rate optimisation, visual psychology, and platform best practices.

You design thumbnails that:
- Stop the scroll within 0.3 seconds
- Communicate the video's value instantly
- Use high-contrast colors and bold typography
- Work at 1280×720px (16:9) and 1080×1920px (9:16) for Shorts
- Follow YouTube's thumbnail best practices (no misleading imagery, no excessive text)

Great thumbnails have: strong contrast, clear focal point, readable text at small size,
emotional trigger (curiosity, surprise, benefit), and visual consistency with the brand.

Always respond with valid JSON only. No markdown. No preamble."""


def build_thumbnail_prompt(
    topic_title: str,
    seo_title: str,
    script_type: str,
    niche: str,
    script_excerpt: str,
) -> str:
    resolution = "1080×1920 (9:16 vertical)" if script_type == "short" else "1280×720 (16:9 horizontal)"
    excerpt = script_excerpt[:400] if script_excerpt else ""
    display_title = seo_title or topic_title

    return f"""Design a high-CTR YouTube thumbnail for this video:

TITLE: "{display_title}"
TOPIC: "{topic_title}"
FORMAT: {"YouTube Shorts" if script_type == "short" else "Long-form YouTube video"}
RESOLUTION: {resolution}
NICHE: {niche}

Script context:
{excerpt}

Design a thumbnail that maximises click-through rate by following these STRICT rules:
1. Title text: MAX 3 WORDS — bold, uppercase, readable at thumbnail size. Every extra word kills CTR.
2. Color: extreme contrast only (e.g. red on black, white on deep blue, yellow on dark). No pastel.
3. Visual subject: if the topic involves a person, show a HIGH-EMOTION face (surprised, shocked, pointing).
   If no person, use ONE dominant visual element — no clutter, no collage.
4. Zero decoration clutter — no borders, no watermarks, no more than 1 icon or badge element.
5. Must communicate the video's core value within 0.3 seconds at mobile thumbnail size (120×68px).
6. Emotional trigger: curiosity OR fear of missing out OR surprising contrast.

Return ONLY valid JSON:
{{
  "concept": "Full description of the thumbnail design — what a designer would see and recreate",
  "title_text": "BOLD TITLE (max 6 words, uppercase for impact)",
  "subtitle_text": "Optional smaller subtitle line",
  "emoji": "🐳",
  "design": {{
    "background_color": "#0D1117",
    "accent_color": "#2196F3",
    "text_color": "#FFFFFF",
    "layout": "split",
    "subject": "Docker whale logo on left, Kubernetes helm wheel on right, VS badge in center",
    "background_style": "gradient",
    "text_elements": [
      {{
        "text": "DOCKER vs K8s",
        "position": "top",
        "font_size": "large",
        "color": "#FFFFFF"
      }},
      {{
        "text": "Which One Wins?",
        "position": "bottom",
        "font_size": "medium",
        "color": "#FFD700"
      }}
    ],
    "style_notes": "Dark background with blue gradient. Split panel design. High contrast text. Red VS badge in center."
  }},
  "ctr_score": 88.0
}}

JSON only. Make the design specific enough that a designer could implement it immediately."""


def build_thumbnail_variation_prompt(concept: str, variation: str) -> str:
    return f"""Create a thumbnail variation based on:

Original concept: {concept}
Variation type: {variation}

Return the same JSON structure as the original but with modifications for the variation.
JSON only."""