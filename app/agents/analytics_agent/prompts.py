ANALYTICS_SYSTEM_PROMPT = """You are a content analytics assistant. Return concise JSON for an analytics summary."""


def build_analytics_prompt(topic_title: str, views: int = 0, likes: int = 0, comments: int = 0, niche: str = "technology") -> str:
    return f"""Analyze the video performance for '{topic_title}'.
Views: {views}
Likes: {likes}
Comments: {comments}
Niche: {niche}

Return a JSON object with keys: summary, recommendations (list of strings), engagement_rate, score."""
