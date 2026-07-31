from pydantic import BaseModel, Field


class QualityAgentInput(BaseModel):
    script_id: str
    script_content: str
    script_type: str = "long"   # "short" | "long"
    topic_title: str = ""
    niche: str = "technology"
    word_count: int = 0


class QualityScores(BaseModel):
    grammar_score: float = Field(default=0.0, ge=0.0, le=100.0)
    fact_consistency_score: float = Field(default=0.0, ge=0.0, le=100.0)
    engagement_score: float = Field(default=0.0, ge=0.0, le=100.0)
    retention_score: float = Field(default=0.0, ge=0.0, le=100.0)
    seo_score: float = Field(default=0.0, ge=0.0, le=100.0)
    uniqueness_score: float = Field(default=0.0, ge=0.0, le=100.0)
    readability_score: float = Field(default=0.0, ge=0.0, le=100.0)

    def overall(self) -> float:
        scores = [
            self.grammar_score,
            self.fact_consistency_score,
            self.engagement_score,
            self.retention_score,
            self.seo_score,
            self.uniqueness_score,
            self.readability_score,
        ]
        return round(sum(scores) / len(scores), 1)


class QualityAgentOutput(BaseModel):
    scores: QualityScores
    overall_score: float = Field(default=0.0, ge=0.0, le=100.0)
    passed: bool = False
    feedback: str = ""
    improvement_suggestions: list[str] = Field(default_factory=list)
    rejection_reason: str | None = None