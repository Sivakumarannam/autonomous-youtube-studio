from pydantic import BaseModel, Field


class StoryboardScene(BaseModel):
    scene_number: int = Field(..., description="Scene number")

    timestamp: str = Field(..., description="Timestamp")

    duration_seconds: int = Field(..., description="Scene duration")

    narration: str = Field(..., description="Narration")

    visual: str = Field(..., description="Visual description")

    image_prompt: str = Field(..., description="Prompt for image generation")


class StoryboardRequest(BaseModel):
    script: str


class StoryboardResponse(BaseModel):
    scenes: list[StoryboardScene]