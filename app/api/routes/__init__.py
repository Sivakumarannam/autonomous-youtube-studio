from app.api.routes.health import router as health_router
from app.api.routes.channels import router as channels_router
from app.api.routes.topics import router as topics_router
from app.api.routes.research import router as research_router
from app.api.routes.scripts import router as scripts_router
from app.api.routes.voice import router as voice_router
from app.api.routes.upload import router as upload_router

__all__ = ["health_router", "channels_router", "topics_router", "research_router", "scripts_router", "voice_router", "upload_router"]