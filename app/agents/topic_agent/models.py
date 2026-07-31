from typing import Optional
from pydantic import BaseModel, Field


class GeneratedTopic(BaseModel):
    """A single topic produced by the Topic Agent."""
    topic: str = Field(..., description="The topic title")
    score: float = Field(..., ge=0.0, le=100.0, description="Trending score 0-100")
    reason: str = Field(..., description="Why this topic is trending")
    keywords: list[str] = Field(default_factory=list)
    content_type: str = Field(default="long", pattern="^(short|long|both)$")


class TopicAgentInput(BaseModel):
    channel_id: str
    niche: str
    language: str = "en"
    count: int = Field(default=5, ge=1, le=20)
    sources: list[str] = Field(default_factory=lambda: ["google_trends", "youtube_trends"])
    content_type: str = Field(default="long", pattern="^(short|long|both)$")


class TopicAgentOutput(BaseModel):
    topics: list[GeneratedTopic]
    source_used: list[str]
    total_generated: int