from pydantic import BaseModel, Field


class ModerationFlags(BaseModel):
    copyright_risk: bool = False
    duplicate_content: bool = False
    spam_risk: bool = False
    policy_violation: bool = False
    monetization_unsafe: bool = False

    def any_flagged(self) -> bool:
        return any([
            self.copyright_risk,
            self.duplicate_content,
            self.spam_risk,
            self.policy_violation,
            self.monetization_unsafe,
        ])

    def flagged_list(self) -> list[str]:
        result = []
        if self.copyright_risk:
            result.append("copyright_risk")
        if self.duplicate_content:
            result.append("duplicate_content")
        if self.spam_risk:
            result.append("spam_risk")
        if self.policy_violation:
            result.append("policy_violation")
        if self.monetization_unsafe:
            result.append("monetization_unsafe")
        return result


class ModerationRisk(BaseModel):
    copyright_risk_score: float = Field(default=0.0, ge=0.0, le=100.0)
    duplicate_risk_score: float = Field(default=0.0, ge=0.0, le=100.0)
    spam_risk_score: float = Field(default=0.0, ge=0.0, le=100.0)
    policy_risk_score: float = Field(default=0.0, ge=0.0, le=100.0)
    monetization_risk_score: float = Field(default=0.0, ge=0.0, le=100.0)

    def overall_risk(self) -> float:
        scores = [
            self.copyright_risk_score,
            self.duplicate_risk_score,
            self.spam_risk_score,
            self.policy_risk_score,
            self.monetization_risk_score,
        ]
        return round(max(scores), 1)  # worst-case risk drives the decision


class ModerationAgentInput(BaseModel):
    script_id: str
    script_content: str
    script_type: str = "long"
    topic_title: str = ""
    niche: str = "technology"
    seo_title: str = ""
    seo_description: str = ""
    tags: list[str] = Field(default_factory=list)


class ModerationAgentOutput(BaseModel):
    approved: bool = False
    flags: ModerationFlags = Field(default_factory=ModerationFlags)
    risk_scores: ModerationRisk = Field(default_factory=ModerationRisk)
    overall_risk_score: float = Field(default=0.0, ge=0.0, le=100.0)
    rejection_reasons: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    reviewer_notes: str = ""