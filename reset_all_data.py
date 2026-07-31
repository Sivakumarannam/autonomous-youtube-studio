"""
Full database reset — wipes EVERY channel's data, not just one.

Use this only when you genuinely want to start the whole app over from
zero (e.g. switching to a new YouTube account/auth, like this run) —
not for clearing out a single channel. For that, use the per-channel
"Reset" button in the dashboard instead (Channel Automation section),
which leaves other channels and your login untouched.

What this DOES delete (every row, every channel):
    pipeline_runs, analytics, uploads, storyboards, quality_reports,
    thumbnails, voices, videos, scripts, research, topics,
    channel_automations, channels

What this does NOT touch:
    - users (your dashboard login — never touched)
    - the database schema itself (tables stay, only rows are cleared)
    - YouTube. This is DB-only. It does not call the YouTube API at
      all. If you switched YouTube auth, your new credentials likely
      don't even have permission to touch videos from the old
      channel/account anyway — clean up the old channel on YouTube's
      side yourself (you mentioned you already have).

After running this, create your new channel — e.g. via the dashboard,
or:
    POST /channels
    {
      "name": "Quirklore",
      "niche": "facts and trivia",
      "language": "en",
      "content_type": "shorts",
      "aspect_ratio": "9:16",
      "youtube_channel_id": "<your channel's UC... ID, not @Quirklores>"
    }

Run from the project root:
    python reset_all_data.py
"""
from __future__ import annotations

import asyncio
import sys


async def main() -> None:
    from sqlalchemy import delete, text

    from app.database.connection import _get_session_factory
    from app.database.models.pipeline_run import PipelineRun
    from app.database.models.analytics import Analytics
    from app.database.models.upload import Upload
    from app.database.models.storyboard import Storyboard
    from app.database.models.quality_report import QualityReport
    from app.database.models.thumbnail import Thumbnail
    from app.database.models.voice import Voice
    from app.database.models.video import Video
    from app.database.models.script import Script
    from app.database.models.research import Research
    from app.database.models.topic import Topic
    from app.database.models.channel_automation import ChannelAutomation
    from app.database.models.channel import Channel
    from app.database.models.agent_log import AgentLog

    print(__doc__, flush=True)
    print("=" * 70, flush=True)
    print("THIS WIPES EVERY CHANNEL'S DATA IN THIS DATABASE. IRREVERSIBLE.", flush=True)
    print("=" * 70, flush=True)
    confirm = input("Type EXACTLY 'DELETE EVERYTHING' to proceed: ")
    if confirm != "DELETE EVERYTHING":
        print("Aborted — no changes made.", flush=True)
        sys.exit(1)

    print("Connecting to the database...", flush=True)
    try:
        session_factory = _get_session_factory()
        session = session_factory()
    except Exception as exc:
        print(f"FAILED to create a database session: {exc!r}", flush=True)
        sys.exit(1)

    try:
        async with session:
            print("Connected. Deleting rows (FK-safe order)...", flush=True)
            # FK-safe order: every child table before its parent.
            for model, label in [
                (PipelineRun, "pipeline_runs"),
                (Analytics, "analytics"),
                (Upload, "uploads"),
                (Storyboard, "storyboards"),
                (QualityReport, "quality_reports"),
                (Thumbnail, "thumbnails"),
                (Voice, "voices"),
                (Video, "videos"),
                (Script, "scripts"),
                (Research, "research"),
                (Topic, "topics"),
                (ChannelAutomation, "channel_automations"),
                (Channel, "channels"),
                (AgentLog, "agent_logs"),
            ]:
                try:
                    result = await asyncio.wait_for(
                        session.execute(delete(model)), timeout=30.0
                    )
                    print(f"  {label}: {result.rowcount} row(s) deleted", flush=True)
                except asyncio.TimeoutError:
                    print(
                        f"  {label}: TIMED OUT after 30s — the DB connection "
                        f"itself may be unreachable. Check DATABASE_URL in .env.",
                        flush=True,
                    )
                    sys.exit(1)

            print("Committing...", flush=True)
            await session.commit()
    except Exception as exc:
        print(f"FAILED: {exc!r}", flush=True)
        sys.exit(1)

    print("=" * 70, flush=True)
    print("Done. Database is clean. 'users' (your login) was left untouched.", flush=True)
    print("Next: create your Quirklore channel via POST /channels or the dashboard.", flush=True)
    print("=" * 70, flush=True)


if __name__ == "__main__":
    asyncio.run(main())