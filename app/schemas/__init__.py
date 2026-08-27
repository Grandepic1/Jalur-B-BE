# ── User ─────────────────────────────────────────────────────────────
from app.models.user import UserCreate, UserResponse

# ── Master data ──────────────────────────────────────────────────────
from app.models.master import (
    IndustryRead,
    RoleRead,
    RoleReadWithIndustry,
    SkillRead,
    ToolRead,
)

# ── User Skills ──────────────────────────────────────────────────────
from app.models.user_skills import UserSkillCreate, UserSkillResponse

# ── F1: Career Health Score ──────────────────────────────────────────
from app.models.health import (
    HealthAssessmentCreate,
    HealthAssessmentResponse,
    HealthAssessmentWithBreakdowns,
    HealthLevel,
    HealthScoreBreakdownResponse,
)

# ── F2: Career Risk Scanner ──────────────────────────────────────────
from app.models.risk import (
    RiskLevel,
    RiskFactorResponse,
    RiskScanCreate,
    RiskScanResponse,
    RiskScanWithFactors,
)

# ── F3: AI Exposure + Skill Relevance ────────────────────────────────
from app.models.ai_exposure import (
    AiExposureAssessmentCreate,
    AiExposureAssessmentResponse,
    AiExposureAssessmentWithDetails,
    ExposedActivityResponse,
    ExposureLevel,
    SkillRelevanceResponse,
    SkillRelevanceStatus,
)

# ── F4: Career Pivot Map ────────────────────────────────────────────
from app.models.pivot import (
    GapLevel,
    PivotAnalysisCreate,
    PivotAnalysisResponse,
    PivotAnalysisWithDetails,
    PivotPreferredRoleResponse,
    PivotSkillGapResponse,
)

# ── F5: Career Evidence Vault ────────────────────────────────────────
from app.models.evidence import (
    EvidenceItemCreate,
    EvidenceItemResponse,
    EvidenceType,
)

# ── F6: Personal Runway ─────────────────────────────────────────────
from app.models.financial import (
    FinancialProfileCreate,
    FinancialProfileResponse,
    RunwayCalculationResponse,
)

# ── F7: What If I Get Fired ─────────────────────────────────────────
from app.models.layoff import (
    ActionPhase,
    LayoffSimulationResponse,
    LayoffSimulationWithActionItems,
    SimulationActionItemResponse,
)

# ── Skill Missions ──────────────────────────────────────────────────
from app.models.missions import (
    MissionStatus,
    SkillMissionCreate,
    SkillMissionResponse,
)

__all__ = [
    # User
    "UserCreate",
    "UserResponse",
    # Master
    "IndustryRead",
    "RoleRead",
    "RoleReadWithIndustry",
    "SkillRead",
    "ToolRead",
    # User Skills
    "UserSkillCreate",
    "UserSkillResponse",
    # F1
    "HealthLevel",
    "HealthAssessmentCreate",
    "HealthAssessmentResponse",
    "HealthAssessmentWithBreakdowns",
    "HealthScoreBreakdownResponse",
    # F2
    "RiskLevel",
    "RiskScanCreate",
    "RiskScanResponse",
    "RiskScanWithFactors",
    "RiskFactorResponse",
    # F3
    "ExposureLevel",
    "SkillRelevanceStatus",
    "AiExposureAssessmentCreate",
    "AiExposureAssessmentResponse",
    "AiExposureAssessmentWithDetails",
    "ExposedActivityResponse",
    "SkillRelevanceResponse",
    # F4
    "GapLevel",
    "PivotAnalysisCreate",
    "PivotAnalysisResponse",
    "PivotAnalysisWithDetails",
    "PivotPreferredRoleResponse",
    "PivotSkillGapResponse",
    # F5
    "EvidenceType",
    "EvidenceItemCreate",
    "EvidenceItemResponse",
    # F6
    "FinancialProfileCreate",
    "FinancialProfileResponse",
    "RunwayCalculationResponse",
    # F7
    "ActionPhase",
    "LayoffSimulationResponse",
    "LayoffSimulationWithActionItems",
    "SimulationActionItemResponse",
    # Missions
    "MissionStatus",
    "SkillMissionCreate",
    "SkillMissionResponse",
]
