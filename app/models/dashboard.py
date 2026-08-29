from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.evidence import EvidenceItemResponse, EvidenceType
from app.models.missions import SkillMissionResponse
from app.models.user import UserResponse


class DashboardProfileSummary(BaseModel):
    full_name: str
    current_role_name: str
    industry_name: str


class DashboardSkillsSummary(BaseModel):
    total: int
    rated: int


class DashboardEvidenceSummary(BaseModel):
    total: int
    by_type: dict[EvidenceType, int]
    recent: list[EvidenceItemResponse]


class DashboardMissionSummary(BaseModel):
    total: int
    todo: int
    in_progress: int
    completed: int
    overdue: int
    completion_percentage: Decimal
    next_mission: SkillMissionResponse | None


class DashboardFinancialSummary(BaseModel):
    total_assets: Decimal
    liquid_assets: Decimal
    monthly_burn: Decimal
    runway_months: Decimal
    currency: str
    latest_saved_at: datetime | None


class DashboardResponse(BaseModel):
    generated_at: datetime
    account: UserResponse
    onboarding_completed: bool
    profile: DashboardProfileSummary | None
    skills: DashboardSkillsSummary
    evidence: DashboardEvidenceSummary
    missions: DashboardMissionSummary
    financial: DashboardFinancialSummary | None
