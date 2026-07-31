from pydantic import BaseModel, Field


class ThumbnailAgentInput(BaseModel):
    script_id: str
    topic_title: str
    script_type: str = "long"   # "short" | "long"
    niche: str = "technology"
    seo_title: str = ""
    script_excerpt: str = ""


class ThumbnailElement(BaseModel):
    text: str = Field(default="", description="Text overlay on thumbnail")
    position: str = Field(default="center", description="Text position: top, center, bottom")
    font_size: str = Field(default="large", description="Font size: small, medium, large")
    color: str = Field(default="#FFFFFF", description="Hex color for text")


class ThumbnailDesign(BaseModel):
    background_color: str = Field(default="#1A1A2E", description="Primary background hex color")
    accent_color: str = Field(default="#E94560", description="Accent / highlight hex color")
    text_color: str = Field(default="#FFFFFF", description="Main text hex color")
    layout: str = Field(
        default="split",
        description="Layout style: split, centered, left-heavy, right-heavy",
    )
    subject: str = Field(default="", description="Main visual subject description")
    background_style: str = Field(
        default="gradient",
        description="Background style: gradient, solid, image, dark",
    )
    text_elements: list[ThumbnailElement] = Field(default_factory=list)
    style_notes: str = Field(default="", description="Additional design notes for the renderer")


class ThumbnailAgentOutput(BaseModel):
    concept: str = Field(..., description="Full thumbnail concept description")
    design: ThumbnailDesign = Field(default_factory=ThumbnailDesign)
    title_text: str = Field(default="", description="Bold title text for thumbnail overlay")
    subtitle_text: str = Field(default="", description="Smaller subtitle or subheading")
    emoji: str = Field(default="", description="Optional emoji to add visual punch")
    file_path: str | None = Field(default=None, description="Path to generated thumbnail file")
    ctr_score: float = Field(
        default=0.0, ge=0.0, le=100.0,
        description="Predicted CTR score 0-100",
    )