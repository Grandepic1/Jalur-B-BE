from datetime import date, datetime
from decimal import Decimal
from enum import Enum as PyEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.evidence import EvidenceType
from app.models.layoff import ActionPhase, LayoffScenario


class SignalLevel(str, PyEnum):
    weak = "weak"
    moderate = "moderate"
    strong = "strong"


class ExposureBand(str, PyEnum):
    low = "low"
    medium = "medium"
    high = "high"


class RelevanceBand(str, PyEnum):
    declining = "declining"
    stable = "stable"
    rising = "rising"


class SignalResult(BaseModel):
    level: SignalLevel
    reason: str = Field(..., min_length=1, max_length=500)

    model_config = ConfigDict(extra="forbid")


class ActivityResult(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    exposure: ExposureBand
    note: str = Field(..., min_length=1, max_length=1000)

    model_config = ConfigDict(extra="forbid")


class SkillResult(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    relevance: RelevanceBand
    recommendation: str = Field(..., min_length=1, max_length=500)

    model_config = ConfigDict(extra="forbid")


class PivotRoleResult(BaseModel):
    role_name: str = Field(..., min_length=1, max_length=100)
    skill_fit: SignalLevel
    activity_fit: SignalLevel
    experience_fit: SignalLevel
    industry_fit: SignalLevel
    missing_skills: list[str] = Field(default_factory=list, max_length=5)
    reason: str = Field(..., min_length=1, max_length=1000)

    model_config = ConfigDict(extra="forbid")

    @field_validator("missing_skills")
    @classmethod
    def normalize_missing_skills(cls, values: list[str]) -> list[str]:
        return list(
            dict.fromkeys(" ".join(value.split()) for value in values if value.strip())
        )


class CareerAnalysisAIResult(BaseModel):
    activities: list[ActivityResult] = Field(..., min_length=1, max_length=8)
    skills: list[SkillResult] = Field(..., min_length=1, max_length=12)
    performance_growth: SignalResult
    adaptability: SignalResult
    market_demand: SignalResult
    industry_stability: SignalResult
    skill_dependency: SignalResult
    pivot_roles: list[PivotRoleResult] = Field(..., min_length=1, max_length=3)
    exposure_summary: str = Field(..., min_length=1, max_length=2000)
    risk_summary: str = Field(..., min_length=1, max_length=2000)
    risk_analysis: str = Field(..., min_length=1, max_length=2000)
    early_warning: str = Field(..., min_length=1, max_length=1000)
    health_summary: str = Field(..., min_length=1, max_length=2000)
    pivot_summary: str = Field(..., min_length=1, max_length=2000)

    model_config = ConfigDict(extra="forbid")

    @field_validator("activities")
    @classmethod
    def reject_duplicate_activities(
        cls, values: list[ActivityResult]
    ) -> list[ActivityResult]:
        if len({item.name.lower() for item in values}) != len(values):
            raise ValueError("activity names must be unique")
        return values

    @field_validator("skills")
    @classmethod
    def reject_duplicate_skills(cls, values: list[SkillResult]) -> list[SkillResult]:
        if len({item.name.lower() for item in values}) != len(values):
            raise ValueError("skill names must be unique")
        return values

    @field_validator("pivot_roles")
    @classmethod
    def reject_duplicate_pivot_roles(
        cls, values: list[PivotRoleResult]
    ) -> list[PivotRoleResult]:
        if len({item.role_name.lower() for item in values}) != len(values):
            raise ValueError("pivot role names must be unique")
        return values

    @field_validator("early_warning", mode="before")
    @classmethod
    def normalize_early_warning(cls, value: object) -> object:
        if isinstance(value, dict):
            for key in ("reason", "description", "warning", "title"):
                item = value.get(key)
                if isinstance(item, str) and item.strip():
                    return item
            for item in value.values():
                if (
                    isinstance(item, str)
                    and item.strip()
                    and item
                    not in {"weak", "moderate", "strong", "low", "medium", "high"}
                ):
                    return item
        return value


class CareerAssessmentRequest(BaseModel):
    role_name: str | None = Field(None, min_length=1, max_length=100)
    industry_name: str | None = Field(None, min_length=1, max_length=100)
    work_duration_months: int | None = Field(None, ge=0, le=960)
    responsibilities: str | None = Field(None, min_length=1, max_length=10000)
    achievements: str | None = Field(None, max_length=10000)
    performance_feedback: str | None = Field(None, max_length=10000)
    career_progression: str | None = Field(None, max_length=10000)
    job_description: str | None = Field(None, max_length=20000)
    tools_and_methods: str | None = Field(None, max_length=5000)

    model_config = ConfigDict(extra="forbid")


class ScoreExplanation(BaseModel):
    key: str
    title: str
    score: Decimal
    level: str
    explanation: str


class ExposureAssessmentResult(BaseModel):
    id: int
    assessed_at: datetime
    score: Decimal
    level: str
    skill_relevance_score: Decimal
    summary: str
    data_confidence: Decimal
    activities: list[ScoreExplanation]
    strong_skills: list[str]
    rising_skills: list[str]
    skills_to_improve: list[str]
    model: str
    scoring_version: str
    market_baseline_version: str | None


class RiskAssessmentResult(BaseModel):
    id: int
    scanned_at: datetime
    score: Decimal
    level: str
    summary: str
    analysis: str
    early_warning: str
    data_confidence: Decimal
    factors: list[ScoreExplanation]
    model: str
    scoring_version: str
    market_baseline_version: str | None


class PivotRoleResponse(BaseModel):
    role_name: str
    match_score: Decimal
    preparation_time_months: int
    preparation_description: str
    missing_skills: list[str]


class PivotAssessmentResult(BaseModel):
    id: int
    analyzed_at: datetime
    current_role_name: str
    summary: str
    data_confidence: Decimal
    roles: list[PivotRoleResponse]
    model: str
    scoring_version: str
    market_baseline_version: str | None


class HealthAssessmentResult(BaseModel):
    id: int
    assessed_at: datetime
    score: Decimal
    level: str
    status: str
    summary: str
    data_confidence: Decimal
    factors: list[ScoreExplanation]
    model: str
    scoring_version: str
    market_baseline_version: str | None


class CareerAssessmentBundleResponse(BaseModel):
    exposure: ExposureAssessmentResult
    risk: RiskAssessmentResult
    pivot: PivotAssessmentResult
    health: HealthAssessmentResult


class EvidenceAssistantDraftRequest(BaseModel):
    evidence_type: EvidenceType
    story: str = Field(..., min_length=1, max_length=10000)
    impact: str | None = Field(None, max_length=5000)
    evidence_date: date | None = None

    model_config = ConfigDict(extra="forbid")


class EvidenceAssistantDraft(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=10000)
    impact: str | None = Field(None, min_length=1, max_length=5000)

    model_config = ConfigDict(extra="forbid")


class EvidenceAssistantDraftResponse(EvidenceAssistantDraft):
    evidence_type: EvidenceType
    user_role: str
    evidence_date: date | None
    model: str
    prompt_version: str


class InsightRequest(BaseModel):
    refresh: bool = False


class DashboardInsightAIResult(BaseModel):
    weekly_insight: str = Field(..., min_length=1, max_length=500)
    next_action: str = Field(..., min_length=1, max_length=500)

    model_config = ConfigDict(extra="forbid")


class DashboardInsightResponse(BaseModel):
    weekly_insight: str
    next_action: str
    next_action_path: str
    model: str


class SimulationPlanItem(BaseModel):
    phase: ActionPhase
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=1000)
    due_in_days: int = Field(..., ge=0, le=365)

    model_config = ConfigDict(extra="forbid")


class SimulationAIResult(BaseModel):
    summary: str = Field(..., min_length=1, max_length=2000)
    action_items: list[SimulationPlanItem] = Field(..., min_length=1, max_length=8)

    model_config = ConfigDict(extra="forbid")


class LayoffSimulationRequest(BaseModel):
    scenario: LayoffScenario = LayoffScenario.tomorrow

    model_config = ConfigDict(extra="forbid")


class LayoffSimulationResult(BaseModel):
    id: int
    scenario: LayoffScenario
    simulated_at: datetime
    career_readiness_score: Decimal
    financial_readiness_score: Decimal
    skill_relevance_score: Decimal
    job_mobility_score: Decimal
    overall_resilience_score: Decimal
    financial_runway_months: Decimal
    target_runway_months: Decimal
    financial_gap: Decimal
    evidence_count: int
    summary: str
    action_items: list[dict[str, object]]
    model: str
    scoring_version: str
