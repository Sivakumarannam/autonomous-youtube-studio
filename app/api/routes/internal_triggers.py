from fastapi import APIRouter, Header, HTTPException
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/internal", tags=["internal"])

def _check_secret(x_trigger_secret: str | None):
    if not settings.scheduler_trigger_secret or x_trigger_secret != settings.scheduler_trigger_secret:
        raise HTTPException(status_code=403, detail="Forbidden")

@router.post("/tick/publish")
async def tick_publish(x_trigger_secret: str | None = Header(None)):
    _check_secret(x_trigger_secret)
    from app.scheduler.scheduler import VideoPublishScheduler
    result = await VideoPublishScheduler()._publish_due_videos()
    return {"ok": True, "result": result}

@router.post("/tick/automation")
async def tick_automation(x_trigger_secret: str | None = Header(None)):
    _check_secret(x_trigger_secret)
    from app.scheduler.automation_scheduler import DailyAutomationScheduler
    await DailyAutomationScheduler()._tick()
    return {"ok": True}

@router.post("/tick/instagram")
async def tick_instagram(x_trigger_secret: str | None = Header(None)):
    _check_secret(x_trigger_secret)
    from app.scheduler.instagram_scheduler import InstagramCrossPostScheduler
    await InstagramCrossPostScheduler()._tick()
    return {"ok": True}