from .models import (
    StoryboardRequest,
    StoryboardResponse,
)
from .service import StoryboardService


class StoryboardAgent:

    def __init__(self):
        self.service = StoryboardService()

    async def run(
        self,
        request: StoryboardRequest,
    ) -> StoryboardResponse:

        return await self.service.generate(request)