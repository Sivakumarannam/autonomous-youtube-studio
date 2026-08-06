"""One-shot: heal scheduler idempotency to set publish_status=PUBLISHED.\n\nRun from repo root:\n  python scripts/patch_scheduler_publish_heal.py\n"""
from pathlib import Path

p = Path("app/scheduler/scheduler.py")
t = p.read_text()
old = """                            upload = await upload_repo.update(
                                upload, status=UploadStatus.PUBLISHED
                            )
"""
new = """                            if upload.youtube_video_id:
                                upload = await upload_repo.mark_published(
                                    upload,
                                    youtube_video_id=upload.youtube_video_id,
                                    youtube_url=upload.youtube_url
                                    or f"https://youtu.be/{upload.youtube_video_id}",
                                )
                            else:
                                upload = await upload_repo.update(
                                    upload,
                                    status=UploadStatus.PUBLISHED,
                                    publish_status=PublishStatus.PUBLISHED,
                                    published_at=upload.published_at
                                    or datetime.now(timezone.utc),
                                )
"""
if old not in t:
    if "mark_published" in t and "idempotency guard" in t:
        print("already patched")
    else:
        raise SystemExit("pattern not found — check scheduler.py manually")
else:
    p.write_text(t.replace(old, new, 1))
    print("patched app/scheduler/scheduler.py")
