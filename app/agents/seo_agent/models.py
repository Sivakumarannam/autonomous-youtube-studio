from pydantic import BaseModel, Field


class SEOAgentInput(BaseModel):
    script_id: str
    topic_title: str
    script_content: str
    script_type: str = "long"  # "short" | "long"
    niche: str = "technology"
    language: str = "en"


class SEOAgentOutput(BaseModel):
    title: str = Field(..., description="SEO-optimized YouTube title")
    description: str = Field(..., description="Full YouTube description with keywords")
    tags: list[str] = Field(default_factory=list, description="YouTube tags (max 500 chars total)")
    hashtags: list[str] = Field(default_factory=list, description="Hashtags for description footer")
    primary_keyword: str = Field(default="", description="Main target keyword")
    secondary_keywords: list[str] = Field(default_factory=list)
    title_score: float = Field(default=0.0, ge=0.0, le=100.0)
    description_score: float = Field(default=0.0, ge=0.0, le=100.0)
    tags_score: float = Field(default=0.0, ge=0.0, le=100.0)
    overall_seo_score: float = Field(default=0.0, ge=0.0, le=100.0)