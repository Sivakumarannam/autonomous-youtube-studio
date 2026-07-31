from .agents import StoryboardAgent
from .models import StoryboardRequest


async def generate_storyboard(script: str):

    agent = StoryboardAgent()

    return await agent.run(
        StoryboardRequest(
            script=script,
        )
    )