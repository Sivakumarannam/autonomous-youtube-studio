import asyncio
from app.database.connection import _get_session_factory
from app.database.repositories.upload_repository import UploadRepository
from app.database.repositories.video_repository import VideoRepository
from app.database.models.upload import UploadStatus, PublishStatus

async def check_upload():
    factory = _get_session_factory()
    async with factory() as session:
        upload_repo = UploadRepository(session)
        video_repo = VideoRepository(session)
        
        # Get all uploads
        all_uploads = await upload_repo.get_all_by_status(UploadStatus.PENDING)
        print(f'Found {len(all_uploads)} pending uploads:')
        for u in all_uploads[:5]:
            video = await video_repo.get_by_id(u.video_id)
            video_title = video.title if video else "N/A"
            print(f'Upload {u.id}:')
            print(f'  Status: {u.status}')
            print(f'  Publish Status: {u.publish_status}')
            print(f'  Scheduled At: {u.scheduled_at}')
            print(f'  Created At: {u.created_at}')
            print(f'  Video Title: {video_title}')
            print()
        
        # Check due for publish
        due = await upload_repo.get_due_for_publish()
        print(f'\nDue for publish right now: {len(due)} uploads')
        for u in due[:3]:
            print(f'  {u.id} - scheduled at {u.scheduled_at}')

asyncio.run(check_upload())
