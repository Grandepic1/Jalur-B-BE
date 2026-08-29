# ── User ─────────────────────────────────────────────────────────────
from app.models.user import UserCreate, UserResponse
from app.models.auth import (
    AuthTokenPurpose,
    AuthTokenResponse,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    GoogleCodeExchange,
    LoginRequest,
    MessageResponse,
    ResetPasswordRequest,
    TokenActionRequest,
)
from app.models.profile import (
    CareerGoal,
    OnboardingCreate,
    OnboardingOptionsResponse,
    OnboardingResponse,
    OnboardingSkillResponse,
    ProfileResponse,
    UserProfileCreate,
    UserProfileResponse,
    UserProfileUpdate,
)

# ── Master data ──────────────────────────────────────────────────────
from app.models.master import (
    IndustryRead,
    RoleRead,
    RoleReadWithIndustry,
    SkillRead,
    ToolRead,
    Page,
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
    FinancialAssetCreate,
    FinancialAssetResponse,
    FinancialAssetType,
    FinancialAssetUpdate,
    FinancialProfileCreate,
    FinancialProfileResponse,
    LiquidityLevel,
    RunwayCalculationResponse,
)

# ── F7: What If I Get Fired ─────────────────────────────────────────
from app.models.layoff import (
    ActionPhase,
    LayoffScenario,
    LayoffSimulationCreate,
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
    "LoginRequest",
    "GoogleCodeExchange",
    "AuthTokenResponse",
    "AuthTokenPurpose",
    "TokenActionRequest",
    "ForgotPasswordRequest",
    "ResetPasswordRequest",
    "ChangePasswordRequest",
    "MessageResponse",
    "CareerGoal",
    "OnboardingCreate",
    "OnboardingResponse",
    "OnboardingSkillResponse",
    "OnboardingOptionsResponse",
    "ProfileResponse",
    "UserProfileCreate",
    "UserProfileUpdate",
    "UserProfileResponse",
    # Master
    "IndustryRead",
    "RoleRead",
    "RoleReadWithIndustry",
    "SkillRead",
    "ToolRead",
    "Page",
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
    "FinancialAssetType",
    "LiquidityLevel",
    "FinancialAssetCreate",
    "FinancialAssetUpdate",
    "FinancialAssetResponse",
    # F7
    "ActionPhase",
    "LayoffScenario",
    "LayoffSimulationCreate",
    "LayoffSimulationResponse",
    "LayoffSimulationWithActionItems",
    "SimulationActionItemResponse",
    # Missions
    "MissionStatus",
    "SkillMissionCreate",
    "SkillMissionResponse",
]
