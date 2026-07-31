import json
import time
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.analytics_agent.agent import AnalyticsAgent
from app.agents.analytics_agent.models import AnalyticsAgentOutput
from app.core.config import settings as app_settings
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.database.models.agent_log import AgentLog, AgentLogLevel
from app.database.models.analytics import Analytics
from app.database.models.upload import Upload
from app.database.repositories.analytics_repository import AnalyticsRepository
from app.llm_providers.factory import get_llm_provider

logger = get_logger(__name__)

# Metrics to request; impressions/CTR may be unavailable on lower-tier accounts.
_PRIMARY_METRICS = [
    "views",
    "likes",
    "comments",
    "shares",
    "estimatedMinutesWatched",
    "averageViewDuration",
    "averageViewPercentage",
    "subscribersGained",
    "subscribersLost",
]

_EXTENDED_METRICS = _PRIMARY_METRICS + [
    "impressions",
    "impressionClickThroughRate",
]

# Metrics that should be averaged when rows are aggregated, not summed.
_AVERAGE_METRICS = {
    "averageViewDuration",
    "averageViewPercentage",
    "impressionClickThroughRate",
}


def _parse_raw_response(raw: dict) -> dict[str, float]:
    """Flatten a YouTube Analytics aggregate response into a plain metric dict.

    We always request reports **without** a ``dimensions`` parameter, so the
    API returns at most one aggregate row covering the entire date range.
    Ratio metrics (CTR, average view duration/percentage) are not additive,
    so summing multiple rows would produce incorrect results.  If the API
    unexpectedly returns more than one row we take only the first and log a
    warning rather than silently corrupting ratio values.
    """
    headers = [h["name"] for h in raw.get("columnHeaders", [])]
    rows = raw.get("rows") or []

    if not rows:
        return {h: 0.0 for h in headers}

    if len(rows) > 1:
        logger.warning(
            "YouTube Analytics returned multiple rows for an aggregate request; "
            "using only the first row to avoid incorrect ratio aggregation.",
            row_count=len(rows),
        )

    row = rows[0]
    return {headers[i]: float(val or 0) for i, val in enumerate(row)}


class AnalyticsAgentService:
    AGENT_NAME = "AnalyticsAgent"

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # LLM-based report (existing — kept for publishing_workflow compat)
    # ------------------------------------------------------------------

    async def run_for_topic(
        self,
        topic_title: str,
        views: int = 0,
        likes: int = 0,
        comments: int = 0,
        niche: str = "technology",
    ) -> AnalyticsAgentOutput:
        agent = AnalyticsAgent(llm_provider=get_llm_provider())
        output = await agent.generate_report(
            topic_title=topic_title,
            views=views,
            likes=likes,
            comments=comments,
            niche=niche,
        )
        await self._log(
            AgentLogLevel.INFO,
            f"Analytics report generated for {topic_title}",
            context=json.dumps({"topic_title": topic_title, "score": output.score}),
            entity_id=None,
            execution_time=time.monotonic(),
        )
        return output

    # ------------------------------------------------------------------
    # YouTube Analytics API — real data fetch
    # ------------------------------------------------------------------

    async def fetch_for_upload(
        self,
        upload: Upload,
        start_date: date,
        end_date: date,
    ) -> Analytics:
        """
        Call the YouTube Analytics API for *upload.youtube_video_id*, persist
        a snapshot in the ``analytics`` table, and return the ORM object.

        Tries the full metric set first (includes impressions/CTR); falls back
        to primary-only metrics if the account tier does not expose those.
        """
        from app.integrations.youtube.auth import YouTubeAuthManager
        from app.integrations.youtube.analytics import YouTubeAnalyticsService

        if not upload.youtube_video_id:
            raise ValueError(
                f"Upload {upload.id} has no YouTube video ID — "
                "cannot fetch analytics for an un-published video."
            )

        auth = YouTubeAuthManager(
            client_id=app_settings.youtube_client_id,
            client_secret=app_settings.youtube_client_secret,
            refresh_token=app_settings.youtube_refresh_token,
        )
        svc = YouTubeAnalyticsService(auth_manager=auth)

        start_str = start_date.isoformat()
        end_str = end_date.isoformat()

        try:
            try:
                raw = await svc.fetch_video_analytics(
                    video_id=upload.youtube_video_id,
                    start_date=start_str,
                    end_date=end_str,
                    metrics=_EXTENDED_METRICS,
                )
            except Exception as exc:
                # impressions/CTR metrics are gated by account tier.  If the API
                # rejects the request (4xx HTTP error), retry with primary metrics
                # only.  Re-raise on any other unexpected failure.
                err_str = str(exc).lower()
                if not any(kw in err_str for kw in ("400", "403", "unsupported", "invalid")):
                    raise
                logger.warning(
                    "Extended metrics unavailable; retrying with primary metrics",
                    youtube_video_id=upload.youtube_video_id,
                    error=str(exc),
                )
                raw = await svc.fetch_video_analytics(
                    video_id=upload.youtube_video_id,
                    start_date=start_str,
                    end_date=end_str,
                    metrics=_PRIMARY_METRICS,
                )
        except Exception as exc:
            try:
                from app.notifications import notify
                await notify(
                    title="Analytics collection failed ❌",
                    body=(
                        f"Could not fetch YouTube Analytics for "
                        f"'{upload.title or 'Untitled'}': {str(exc)[:200]}"
                    ),
                    level="error",
                    extra={
                        "Upload ID": str(upload.id),
                        "YouTube video ID": upload.youtube_video_id,
                    },
                )
            except Exception as _notify_exc:
                logger.warning("Notification failed (non-fatal)", error=str(_notify_exc))
            raise
        finally:
            await svc.close()
            await auth.close()

        data = _parse_raw_response(raw)

        analytics = Analytics(
            upload_id=upload.id,
            snapshot_date=datetime.now(timezone.utc),
            views=int(data.get("views", 0)),
            likes=int(data.get("likes", 0)),
            comments=int(data.get("comments", 0)),
            shares=int(data.get("shares", 0)),
            watch_time_minutes=data.get("estimatedMinutesWatched", 0.0),
            average_view_duration=data.get("averageViewDuration", 0.0),
            average_view_percentage=data.get("averageViewPercentage", 0.0),
            ctr=data.get("impressionClickThroughRate", 0.0),
            impressions=int(data.get("impressions", 0)),
            subscribers_gained=int(data.get("subscribersGained", 0)),
            subscribers_lost=int(data.get("subscribersLost", 0)),
            revenue=0.0,  # Revenue requires a monetisation-tier API scope
        )

        repo = AnalyticsRepository(self._session)
        analytics = await repo.create(analytics)

        await self._log(
            AgentLogLevel.INFO,
            f"Analytics snapshot saved for YouTube video {upload.youtube_video_id}",
            context=json.dumps({
                "upload_id": str(upload.id),
                "youtube_video_id": upload.youtube_video_id,
                "views": analytics.views,
            }),
            entity_id=str(upload.id),
            execution_time=time.monotonic(),
        )

        try:
            from app.notifications import notify
            await notify(
                title="Analytics collected ✅",
                body=(
                    f"Analytics snapshot saved for "
                    f"'{upload.title or 'Untitled'}' — {analytics.views} views."
                ),
                level="success",
                extra={
                    "Upload ID": str(upload.id),
                    "YouTube video ID": upload.youtube_video_id,
                    "Views": analytics.views,
                },
            )
        except Exception as exc:
            logger.warning("Notification failed (non-fatal)", error=str(exc))

        return analytics

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _log(
        self,
        level: AgentLogLevel,
        message: str,
        context: str | None = None,
        entity_id: str | None = None,
        execution_time: float | None = None,
    ) -> None:
        entry = AgentLog(
            agent_name=self.AGENT_NAME,
            level=level,
            message=message,
            context=context,
            entity_type="upload",
            entity_id=entity_id,
            execution_time=execution_time,
        )
        self._session.add(entry)
        await self._session.flush()