from pydantic import BaseModel, Field


class ResearchAgentInput(BaseModel):
    topic_id: str
    topic_title: str
    topic_description: str | None = None
    niche: str = "technology"
    language: str = "en"


class ResearchAgentOutput(BaseModel):
    summary: str = Field(..., description="Concise topic summary for script writers")
    key_facts: list[str] = Field(default_factory=list, description="Bullet-point facts")
    references: list[str] = Field(default_factory=list, description="Source URLs or citations")
    talking_points: list[str] = Field(default_factory=list, description="Suggested content angles")
    target_audience: str = Field(default="", description="Who this content is for")
    difficulty_level: str = Field(default="beginner", description="beginner | intermediate | advanced")