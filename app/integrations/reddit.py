"""Reddit trend scraper.

Uses the Reddit API (via asyncpraw) to pull hot/rising posts from
subreddits relevant to the channel niche and return them as candidate
video topics.

Activates automatically when REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET
are set. Falls back silently if credentials are missing — the topic
agent continues with LLM-generated topics.
"""
from __future__ import annotations

import re
from typing import Optional

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Map common niche keywords → subreddits to scrape
NICHE_SUBREDDITS: dict[str, list[str]] = {
    "technology":     ["technology", "tech", "gadgets", "Futurology", "artificial"],
    "ai":             ["artificial", "MachineLearning", "ChatGPT", "singularity", "OpenAI"],
    "science":        ["science", "askscience", "EverythingScience", "Futurology"],
    "history":        ["history", "AskHistorians", "todayilearned", "HistoryMemes"],
    "facts":          ["todayilearned", "interestingasfuck", "Damnthatsinteresting", "woahdude"],
    "education":      ["explainlikeimfive", "todayilearned", "AskScience", "learnprogramming"],
    "finance":        ["personalfinance", "investing", "stocks", "wallstreetbets", "financialindependence"],
    "health":         ["Health", "nutrition", "fitness", "medicine", "psychology"],
    "business":       ["Entrepreneur", "smallbusiness", "startups", "business"],
    "programming":    ["programming", "Python", "javascript", "webdev", "learnprogramming"],
    "gaming":         ["gaming", "pcgaming", "Games", "indiegaming"],
    "food":           ["food", "Cooking", "recipes", "AskCulinary"],
    "travel":         ["travel", "solotravel", "backpacking", "digitalnomad"],
    "psychology":     ["psychology", "PsychologyToday", "askpsychology", "cogsci"],
    "space":          ["space", "Astronomy", "astrophysics", "nasa", "spacex"],
    "default":        ["todayilearned", "interestingasfuck", "Damnthatsinteresting", "Futurology", "technology"],
}


def _get_subreddits(niche: str) -> list[str]:
    """Return relevant subreddits for a given niche string."""
    niche_lower = niche.lower()
    for key, subs in NICHE_SUBREDDITS.items():
        if key in niche_lower or niche_lower in key:
            return subs
    return NICHE_SUBREDDITS["default"]


def _clean_title(title: str) -> str:
    """Strip Reddit formatting, links, and flair from a post title."""
    title = re.sub(r"\[.*?\]", "", title)          # remove [flair]
    title = re.sub(r"\(https?://\S+\)", "", title)  # remove markdown links
    title = re.sub(r"\s+", " ", title).strip()
    return title


def is_configured() -> bool:
    return bool(settings.reddit_client_id and settings.reddit_client_secret)


async def fetch_trending_topics(
    niche: str,
    limit: int = 15,
    min_score: int = 100,
) -> list[dict]:
    """
    Fetch hot Reddit posts relevant to a niche and return them as
    topic dicts compatible with TopicAgentService.

    Each dict has keys: topic, score, reason, keywords, source.
    Returns [] if credentials are missing or on any error.
    """
    if not is_configured():
        logger.debug("Reddit credentials not set — skipping trend scrape.")
        return []

    try:
        import asyncpraw  # type: ignore
    except ImportError:
        logger.warning("asyncpraw not installed — Reddit scraping disabled.")
        return []

    subreddits = _get_subreddits(niche)
    topics: list[dict] = []

    try:
        reddit = asyncpraw.Reddit(
            client_id=settings.reddit_client_id,
            client_secret=settings.reddit_client_secret,
            user_agent=settings.reddit_user_agent,
        )

        seen: set[str] = set()

        for sub_name in subreddits[:4]:  # cap at 4 subreddits per run
            try:
                subreddit = await reddit.subreddit(sub_name)
                async for post in subreddit.hot(limit=20):
                    if post.score < min_score:
                        continue
                    if post.stickied:
                        continue

                    title = _clean_title(post.title)
                    if not title or len(title) < 10:
                        continue
                    if title.lower() in seen:
                        continue
                    seen.add(title.lower())

                    # Extract keywords from title words (4+ chars)
                    keywords = list({
                        w.lower() for w in re.findall(r"[a-zA-Z]{4,}", title)
                    })[:8]

                    topics.append({
                        "topic": title,
                        "score": min(post.score / 1000, 10.0),  # normalise to 0-10
                        "reason": (
                            f"Trending on r/{sub_name} with "
                            f"{post.score:,} upvotes and "
                            f"{post.num_comments:,} comments"
                        ),
                        "keywords": keywords,
                        "source": "reddit",
                        "reddit_url": f"https://reddit.com{post.permalink}",
                    })

                    if len(topics) >= limit:
                        break

            except Exception as sub_err:
                logger.warning("Reddit subreddit fetch failed", sub=sub_name, error=str(sub_err))
                continue

            if len(topics) >= limit:
                break

        await reddit.close()
        logger.info("Reddit trends fetched", niche=niche, count=len(topics))

    except Exception as exc:
        logger.warning("Reddit scraper failed (non-fatal)", error=str(exc))
        return []

    return topics[:limit]
