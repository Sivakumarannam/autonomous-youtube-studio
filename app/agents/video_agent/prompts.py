VIDEO_SYSTEM_PROMPT = """You are a video production planner. Return concise JSON describing a basic video edit plan."""


def build_video_prompt(topic_title: str, description: str = "", script_type: str = "long", niche: str = "technology") -> str:
    return f"""Create a simple video edit plan for the topic '{topic_title}'.
Description: {description}
Script type: {script_type}
Niche: {niche}

Return a JSON object with keys: title, summary, scenes (list of objects with title, description, duration_seconds), edits (list of short strings), duration_seconds."""