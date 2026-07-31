import asyncio
from uuid import UUID
from app.database.connection import _get_session_factory
from app.database.repositories.upload_repository import UploadRepository
from app.database.repositories.video_repository import VideoRepository
from app.agents.upload_agent.service import UploadAgentService

async def test_upload():
    factory = _get_session_factory()
    async with factory() as session:
        upload_repo = UploadRepository(session)
        video_repo = VideoRepository(session)
        
        # Get the problematic upload
        u = await upload_repo.get_or_raise(UUID("e2728a89-1089-480c-96f0-c698cf44c701"))
        print(f"Upload found: {u.id}")
        print(f"  Status: {u.status}")
        print(f"  Publish Status: {u.publish_status}")
        print(f"  Video ID: {u.video_id}")
        
        # Get the video
        video = await video_repo.get_by_id(u.video_id)
        if not video:
            print("ERROR: Video not found!")
            return
        
        print(f"Video found: {video.id}")
        print(f"  Status: {video.status}")
        print(f"  Video Path: {video.video_path}")
        print(f"  Audio Path: {video.audio_path}")
        
        # Try to upload
        print("\nAttempting to upload...")
        try:
            upload_agent = UploadAgentService(session)
            result = await upload_agent.run_upload_for_video(
                video=video, 
                upload=u, 
                raise_on_error=True
            )
            print(f"Result: Status={result.status}, YouTube ID={result.youtube_video_id}")
            if result.error_message:
                print(f"Error: {result.error_message}")
        except Exception as e:
            print(f"Exception occurred: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

asyncio.run(test_upload())
