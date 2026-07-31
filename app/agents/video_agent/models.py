from pydantic import BaseModel, Field


class VideoScene(BaseModel):
    title: str = Field(default="")
    description: str = Field(default="")
    duration_seconds: int = Field(default=10)


class VideoAgentOutput(BaseModel):
    title: str = Field(default="")
    summary: str = Field(default="")
    scene_count: int = Field(default=0)
    scenes: list[VideoScene] = Field(default_factory=list)
    edits: list[str] = Field(default_factory=list)
    output_path: str | None = Field(default=None)
    duration_seconds: int = Field(default=0)
    file_size: int = Field(default=0)
    success: bool = Field(default=True)