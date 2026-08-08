"""Boost pending topic scores from recent YouTube analytics (growth loop)."""
from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.database.models.analytics import Analytics
from app.database.models.script import Script
from app.database.models.topic import Topic, TopicStatus
from app.database.models.upload import Upload
from app.database.models.video import Video

logger = get_logger(__name__)

_STOP = {
    "the", "a", "an", "and", "or", "to", "of", "in", "for", "on", "with",
    "your", "you", "this", "that", "shorts", "video", "how", "what", "why",
}


def _keywords(title: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", (title or "").lower())
    return {w for w in words if len(w) > 2 and w not in _STOP}


async def apply_performance_scores(
    session: AsyncSession,
    channel_id: UUID,
    top_n: int = 10,
) -> int:
    """
    Raise score on pending topics that share keywords with high-view uploads.
    Returns number of topics boosted.
    """
    q = (
        select(Analytics, Upload, Script)
        .join(Upload, Analytics.upload_id == Upload.id)
        .join(Video, Upload.video_id == Video.id)
        .join(Script, Video.script_id == Script.id)
        .join(Topic, Script.topic_id == Topic.id)
        .where(and_(Topic.channel_id == channel_id, Analytics.views > 0))
        .order_by(desc(Analytics.views))
        .limit(top_n)
    )
    rows = (await session.execute(q)).all()
    if not rows:
        return 0

    winner_kw: dict[str, float] = {}
    for analytics, upload, script in rows:
        title = (upload.title or getattr(script, "title", None) or "")
        weight = float(analytics.views or 0) + 5.0 * float(
            analytics.average_view_percentage or 0
        )
        for kw in _keywords(title):
            winner_kw[kw] = winner_kw.get(kw, 0.0) + weight

    if not winner_kw:
        return 0

    pending = (
        await session.execute(
            select(Topic).where(
                and_(
                    Topic.channel_id == channel_id,
                    Topic.status.notin_(
                        (TopicStatus.REJECTED, TopicStatus.FAILED, TopicStatus.PUBLISHED)
                    ),
                )
            )
        )
    ).scalars().all()

    boosted = 0
    for topic in pending:
        kws = _keywords(topic.title)
        if not kws:
            continue
        overlap = sum(winner_kw.get(k, 0.0) for k in kws)
        if overlap <= 0:
            continue
        bump = min(25.0, (overlap ** 0.5) / 10.0)
        new_score = float(topic.score or 0.0) + bump
        if new_score > float(topic.score or 0.0):
            topic.score = new_score
            boosted += 1

    if boosted:
        await session.flush()
        logger.info(
            "Performance feedback boosted topics",
            channel_id=str(channel_id),
            boosted=boosted,
            winners=len(rows),
        )
    return boosted
