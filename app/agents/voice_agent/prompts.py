"""
Voice Agent prompts.

The Voice Agent primarily uses gTTS / pyttsx3 for audio generation,
not an LLM. The LLM is used only for script pre-processing:
cleaning filler words, adding SSML-like pause markers, and
estimating duration before synthesis.
"""

VOICE_PREP_SYSTEM_PROMPT = """You are a professional voiceover script editor.
You prepare scripts for text-to-speech synthesis by:
- Removing markdown symbols, asterisks, hashtags, and special characters
- Adding natural pause indicators: [pause] for 0.5s, [long-pause] for 1s
- Expanding abbreviations (e.g. K8s → Kubernetes, CI/CD → CI CD)
- Removing emojis and emoji-like characters that TTS reads incorrectly
- Ensuring smooth, natural phrasing suitable for narration

Return ONLY the cleaned script text — no JSON, no explanations, no quotes."""


def build_voice_prep_prompt(script_content: str, language: str = "en") -> str:
    excerpt = script_content[:3000]
    return f"""Prepare this script for text-to-speech synthesis:

Language: {language}
Script:
---
{excerpt}
---

Clean the script:
1. Remove all markdown (**, __, #, -, *, etc.)
2. Expand abbreviations: K8s→Kubernetes, CI/CD→CI CD, TTS→text to speech, etc.
3. Remove URLs — replace with "the link in the description"
4. Add [pause] after major section headings
5. Add [pause] after the hook/introduction
6. Remove emojis entirely
7. Keep all actual content words

Return ONLY the cleaned script text. No JSON. No quotes. No explanations."""


def build_duration_estimate_prompt(word_count: int, script_type: str) -> str:
    """Estimate reading duration — used as a fallback calculation."""
    wpm = 135 if script_type == "long" else 150
    estimated_seconds = round((word_count / wpm) * 60)
    return str(estimated_seconds)