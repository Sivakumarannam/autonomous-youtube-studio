UPLOAD_SYSTEM_PROMPT = """You are a YouTube upload planner. Return concise metadata for a video upload."""


def build_upload_prompt(
    video_title: str,
    description: str = "",
    tags: list[str] | None = None,
    script_type: str = "long",
) -> str:
    tag_text = ", ".join(tags or [])

    if script_type == "short":
        comment_instruction = """Write a SHORT-form comment (under 12 words) that sparks a quick reply.
It must ask a YES/NO or this-or-that question related to the video topic.
Examples: "Would you actually try this? Drop a yes or no 👇"
          "Which surprised you more — #1 or #3?"
          "Did you already know this one? Be honest 😅"
Never write: "Like and subscribe!" or "Check out my channel!" — those kill engagement."""
    else:
        comment_instruction = """Write a LONG-FORM comment (under 20 words) that invites a thoughtful reply.
It must ask an open-ended question tied to the video's central argument or most surprising point.
Examples: "Which of these facts completely changed how you think about [topic]? Tell me below 👇"
          "What's the ONE thing from this video you're going to apply first? Comment and I'll reply."
          "Most people skip step 3 — did you already know that trick? Let me know."
The comment must feel like it was written by a person, not a bot. Never generic."""

    return f"""Prepare a YouTube upload payload for the video titled '{video_title}'.
Description: {description}
Tags: {tag_text}
Format: {"YouTube Shorts" if script_type == "short" else "Long-form video"}

{comment_instruction}

Return a JSON object with keys: title, description, tags, status, pinned_comment."""
