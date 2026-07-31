from pydantic import BaseModel, Field


class ShortScriptAgentInput(BaseModel):
    topic_id: str
    topic_title: str
    research_summary: str | None = None
    key_facts: list[str] = Field(default_factory=list)
    channel_niche: str = "technology"
    language: str = "en"


class ShortScriptAgentOutput(BaseModel):
    hook: str = Field(..., description="Opening 1-2 sentences to hook viewers")
    body: str = Field(..., description="Main content — fast paced, punchy")
    cta: str = Field(..., description="Call to action at the end")
    full_script: str = Field(..., description="Complete formatted script")
    word_count: int = Field(default=0)
    estimated_duration_seconds: int = Field(default=30)
    seo_title: str = Field(default="")
    seo_description: str = Field(default="")
    tags: list[str] = Field(default_factory=list)
    hashtags: list[str] = Field(default_factory=list)