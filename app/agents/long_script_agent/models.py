from pydantic import BaseModel, Field


class ScriptSection(BaseModel):
    title: str
    content: str
    duration_seconds: int = 60


class ChapterTimestamp(BaseModel):
    time: str = "00:00"   # e.g. "01:30"
    title: str = ""       # e.g. "Introduction"


class LongScriptAgentOutput(BaseModel):
    introduction: str
    sections: list[ScriptSection]
    conclusion: str
    cta: str
    full_script: str
    word_count: int = 0
    estimated_duration_seconds: int = 490  # floor = 8 min 10 s → clears 8:05 mid-roll threshold
    hook: str = ""
    seo_title: str = ""
    seo_description: str = ""
    tags: list[str] = Field(default_factory=list)
    hashtags: list[str] = Field(default_factory=list)
    thumbnail_concept: str = ""
    chapter_timestamps: list[ChapterTimestamp] = Field(default_factory=list)