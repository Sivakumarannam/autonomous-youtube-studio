import asyncio
from uuid import UUID
from app.database.connection import _get_session_factory
from app.database.repositories.upload_repository import UploadRepository

async def check():
    factory = _get_session_factory()
    async with factory() as session:
        repo = UploadRepository(session)
        u = await repo.get_or_raise(UUID("bcb839b2-af0b-4b19-ac99-475984ee621d"))
        print(f"Upload Status: {u.status}")
        print(f"Publish Status: {u.publish_status}")
        print(f"Scheduled At: {u.scheduled_at}")
        print(f"YouTube ID: {u.youtube_video_id}")

asyncio.run(check())
