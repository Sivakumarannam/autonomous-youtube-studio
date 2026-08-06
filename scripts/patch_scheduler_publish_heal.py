"""One-shot: heal scheduler idempotency without PublishStatus.PUBLISHED.

PublishStatus members: draft | approved | scheduled | rejected
Live state uses UploadStatus.PUBLISHED + youtube_video_id.

Run from repo root:
  python3 scripts/patch_scheduler_publish_heal.py
"""
from pathlib import Path

p = Path("app/scheduler/scheduler.py")
t = p.read_text()

# Undo bad PublishStatus.PUBLISHED if present
t = t.replace(
    "publish_status=PublishStatus.PUBLISHED,",
    "# publish_status unchanged (enum has no PUBLISHED)",
)

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
                                    published_at=upload.published_at
                                    or datetime.now(timezone.utc),
                                )
"""

if "mark_published" in t and "idempotency guard" in t and old not in t:
    # already has mark_published path — strip any PublishStatus.PUBLISHED leftovers
    p.write_text(t)
    print("scheduler already uses mark_published; cleaned PublishStatus.PUBLISHED if any")
elif old in t:
    p.write_text(t.replace(old, new, 1))
    print("patched app/scheduler/scheduler.py")
else:
    p.write_text(t)
    print("no simple pattern — file left as-is after PublishStatus cleanup")
