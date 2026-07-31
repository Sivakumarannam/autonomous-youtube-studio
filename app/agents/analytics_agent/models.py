from pydantic import BaseModel, Field


class AnalyticsAgentOutput(BaseModel):
    topic_title: str = Field(default="")
    summary: str = Field(default="")
    recommendations: list[str] = Field(default_factory=list)
    engagement_rate: float = Field(default=0.0)
    score: float = Field(default=0.0)
    success: bool = Field(default=True)
