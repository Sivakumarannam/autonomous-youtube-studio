from uuid import UUID

from pydantic import BaseModel


class StoryboardGenerateRequest(BaseModel):
    script_id: UUID
    script: str


class StoryboardUpdateRequest(BaseModel):
    scenes: dict


class StoryboardSceneResponse(BaseModel):
    scene_number: int
    narration: str
    visual: str
    image_prompt: str
    duration_seconds: int


class StoryboardGenerateResponse(BaseModel):
    id: UUID
    script_id: UUID
    scenes: dict


class StoryboardResponse(BaseModel):
    id: UUID
    script_id: UUID
    scenes: dict

    model_config = {
        "from_attributes": True,
    }


class DeleteResponse(BaseModel):
    message: str