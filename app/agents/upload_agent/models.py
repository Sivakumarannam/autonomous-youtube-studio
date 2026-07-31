from pydantic import BaseModel, Field


class UploadSettings(BaseModel):
    provider: str = Field(default="mock")
    title: str = Field(default="")
    description: str = Field(default="")
    tags: list[str] = Field(default_factory=list)
    # Privacy: "private" keeps it hidden until manually published;
    # "public" goes live immediately; "unlisted" is accessible by link only.
    privacy_status: str = Field(default="private")
    # YouTube category ID — "27" = Education, "28" = Science & Technology,
    # "22" = People & Blogs.  Full list: developers.google.com/youtube/v3/docs/videoCategories
    category_id: str = Field(default="")
    # Notify channel subscribers when the video goes public.
    notify_subscribers: bool = Field(default=True)
    # Must be False for videos not specifically aimed at children under 13.
    made_for_kids: bool = Field(default=False)
    # AI disclosure — required by YouTube policy for AI-generated visuals,
    # voice, or scripts.  Set to True for all content from this pipeline.
    ai_generated: bool = Field(default=True)


class UploadAgentOutput(BaseModel):
    video_title: str = Field(default="")
    description: str = Field(default="")
    tags: list[str] = Field(default_factory=list)
    # A short question-style comment posted automatically after upload to
    # seed engagement. Still needs one manual pin in YouTube Studio — the
    # Data API has no endpoint to pin a comment programmatically.
    pinned_comment: str = Field(default="")
    status: str = Field(default="queued")
    upload_url: str | None = Field(default=None)
    video_id: str | None = Field(default=None)
    provider_used: str = Field(default="mock")
    success: bool = Field(default=True)
