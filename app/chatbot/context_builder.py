"""Context Builder — queries the live database and builds a context string
that is injected into the chatbot's LLM prompt alongside RAG results.

Provides:
  - Recent pipeline runs (last 10) with status, stage, errors
  - Upload queue and recent uploads
  - Scheduler health
  - Active channels
  - Suggested questions based on current system state
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger

logger = get_logger(__name__)


async def build_live_context(session: AsyncSession) -> str:
    """Query the DB and return a concise plain-text context block for the LLM."""
    lines: list[str] = ["=== LIVE SYSTEM STATE ===", f"Timestamp: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"]

    try:
        from app.database.models.pipeline_run import PipelineRun, PipelineStatus
        from app.database.models.upload import Upload
        from app.database.models.channel import Channel

        # --- Channels ---
        ch_result = await session.execute(select(Channel).limit(20))
        channels = ch_result.scalars().all()
        if channels:
            lines.append(f"\nActive channels ({len(channels)}):")
            for ch in channels:
                lines.append(f"  - {ch.name} (id={ch.id})")
        else:
            lines.append("\nNo channels configured yet.")

        # --- Recent pipeline runs ---
        runs_result = await session.execute(
            select(PipelineRun)
            .order_by(desc(PipelineRun.created_at))
            .limit(10)
        )
        runs = runs_result.scalars().all()
        if runs:
            lines.append(f"\nRecent pipeline runs (last {len(runs)}):")
            for run in runs:
                age = _age_str(run.created_at)
                status_str = run.status.value if hasattr(run.status, "value") else str(run.status)
                line = f"  - Run {str(run.id)[:8]} | {status_str} | stage={run.current_stage or run.failed_stage or 'N/A'} | {age} ago"
                if run.error_message:
                    line += f"\n    ERROR: {run.error_message[:200]}"
                lines.append(line)
        else:
            lines.append("\nNo pipeline runs yet.")

        # --- Failed runs in last 24 h ---
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        failed_result = await session.execute(
            select(PipelineRun)
            .where(
                PipelineRun.status == PipelineStatus.FAILED,
                PipelineRun.created_at >= cutoff,
            )
            .order_by(desc(PipelineRun.created_at))
            .limit(5)
        )
        recent_failures = failed_result.scalars().all()
        if recent_failures:
            lines.append(f"\nRecent failures (last 24 h): {len(recent_failures)}")
            for run in recent_failures:
                lines.append(
                    f"  - Run {str(run.id)[:8]} failed at stage '{run.failed_stage}': "
                    f"{(run.error_message or 'no error message')[:150]}"
                )

        # --- Running pipelines ---
        running_result = await session.execute(
            select(PipelineRun).where(PipelineRun.status == PipelineStatus.RUNNING)
        )
        running = running_result.scalars().all()
        if running:
            lines.append(f"\nCurrently running: {len(running)} pipeline(s)")
            for run in running:
                lines.append(f"  - Run {str(run.id)[:8]} | stage={run.current_stage}")
        else:
            lines.append("\nNo pipelines currently running.")

        # --- Upload queue / recent uploads ---
        # NOTE: PublishStatus only has DRAFT/APPROVED/SCHEDULED/REJECTED —
        # "pending" and "uploading" were never valid values for this column
        # and previously caused a Postgres enum-comparison error here. That
        # error, combined with the missing rollback() below, poisoned the
        # whole DB session for the rest of the WebSocket connection (every
        # later query failed with "current transaction is aborted" even
        # though it had nothing to do with the real problem).
        try:
            from app.database.models.upload import PublishStatus
            queue_result = await session.execute(
                select(Upload)
                .where(Upload.publish_status.in_([
                    PublishStatus.DRAFT, PublishStatus.APPROVED, PublishStatus.SCHEDULED,
                ]))
                .limit(10)
            )
            queue = queue_result.scalars().all()
            if queue:
                lines.append(f"\nUpload queue: {len(queue)} pending")
        except Exception:
            # A failed query inside a Postgres transaction poisons every
            # subsequent query on this session until rolled back — always
            # roll back here, not just log, or every later query this
            # session runs (including unrelated ones) will fail too.
            await session.rollback()

        # Recent successful uploads
        uploads_result = await session.execute(
            select(Upload)
            .order_by(desc(Upload.created_at))
            .limit(5)
        )
        uploads = uploads_result.scalars().all()
        if uploads:
            lines.append(f"\nRecent uploads (last {len(uploads)}):")
            for up in uploads:
                status = getattr(up, "publish_status", "unknown")
                if hasattr(status, "value"):
                    status = status.value
                yt_id = getattr(up, "youtube_video_id", None) or "not yet uploaded"
                lines.append(f"  - {getattr(up, 'title', 'Untitled')[:60]} | status={status} | yt={yt_id}")

    except Exception as exc:
        # Same reasoning as above — roll back so this session is usable
        # for whatever query the chatbot engine runs next (e.g. saving the
        # assistant's reply), not just logged and left poisoned.
        await session.rollback()
        logger.warning("context_builder: DB query failed", error=str(exc))
        lines.append(f"\n[Context fetch partial — some data unavailable: {exc}]")

    lines.append("\n=== END LIVE STATE ===")
    return "\n".join(lines)


async def get_suggested_questions(session: AsyncSession) -> list[str]:
    """Return 4–6 suggested questions tailored to current system state."""
    suggestions = []
    try:
        from app.database.models.pipeline_run import PipelineRun, PipelineStatus
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

        # Did something fail recently?
        failed_result = await session.execute(
            select(func.count(PipelineRun.id)).where(
                PipelineRun.status == PipelineStatus.FAILED,
                PipelineRun.created_at >= cutoff,
            )
        )
        fail_count = failed_result.scalar() or 0
        if fail_count:
            suggestions.append(f"Why did the last pipeline run fail?")

        # Is anything running?
        running_result = await session.execute(
            select(func.count(PipelineRun.id)).where(PipelineRun.status == PipelineStatus.RUNNING)
        )
        if (running_result.scalar() or 0) > 0:
            suggestions.append("What's running right now?")

    except Exception:
        await session.rollback()

    # Always-on questions
    suggestions += [
        "What is the full pipeline flow?",
        "How many videos were uploaded this week?",
        "Is the scheduler healthy?",
        "How do I add a new channel?",
    ]
    return suggestions[:6]


def _age_str(dt: datetime) -> str:
    if dt is None:
        return "?"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - dt
    total_secs = int(delta.total_seconds())
    if total_secs < 60:
        return f"{total_secs}s"
    elif total_secs < 3600:
        return f"{total_secs // 60}m"
    elif total_secs < 86400:
        return f"{total_secs // 3600}h"
    else:
        return f"{total_secs // 86400}d"
