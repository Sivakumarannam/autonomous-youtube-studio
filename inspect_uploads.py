import asyncio
from app.database.connection import _get_session_factory
from app.database.repositories.upload_repository import UploadRepository
from app.database.repositories.video_repository import VideoRepository
from app.core.config import settings
from datetime import datetime, timezone

async def inspect():
    print(f"Scheduler interval minutes: {settings.scheduler_interval_minutes}")
    print(f"Auto publish enabled: {settings.auto_publish_enabled}")
    print()
    
    factory = _get_session_factory()
    async with factory() as session:
        upload_repo = UploadRepository(session)
        
        # Get all uploads regardless of status
        from sqlalchemy import select
        result = await session.execute(select(upload_repo.model))
        all_uploads = list(result.scalars().all())
        
        print(f"Total uploads in DB: {len(all_uploads)}")
        for u in all_uploads:
            u_str = str(u.id)[:8]
            print(f"  {u_str}... - Status: {u.status.name}, Publish: {u.publish_status.name if u.publish_status else 'None'}, Scheduled: {u.scheduled_at}, YouTube: {u.youtube_video_id}")
        
        print()
        due = await upload_repo.get_due_for_publish()
        now = datetime.now(timezone.utc)
        print(f"Current time: {now}")
        print(f"Due for publish (right now): {len(due)} uploads")
        for u in due:
            u_str = str(u.id)[:8]
            print(f"  {u_str}... - Scheduled at: {u.scheduled_at}, Status: {u.status.name}")

asyncio.run(inspect())
