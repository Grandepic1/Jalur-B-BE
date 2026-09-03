# ── Master data ──────────────────────────────────────────────────────
from app.models.master import Industry, Role, Skill, Tool
from app.models.user import User
from app.models.auth import AuthActionToken, OAuthLoginCode
from app.models.profile import UserProfile
from app.models.user_skills import UserSkill
from app.models.cv import CVConfirmationReceipt, UserCV
from app.models.storage import StorageDeletionJob

# ── F1: Career Health Score ──────────────────────────────────────────
from app.models.health import HealthAssessment, HealthScoreBreakdown

# ── F2: Career Risk Scanner ──────────────────────────────────────────
from app.models.risk import RiskFactor, RiskScan, RiskScanSkill

# ── F3: AI Exposure + Skill Relevance ────────────────────────────────
from app.models.ai_exposure import (
    AiExposureAssessment,
    AiExposureSkill,
    AiExposureTool,
    ExposedActivity,
    SkillRelevance,
)

# ── F4: Career Pivot Map ────────────────────────────────────────────
from app.models.pivot import PivotAnalysis, PivotPreferredRole, PivotSkillGap

# ── F5: Career Evidence Vault ────────────────────────────────────────
from app.models.evidence import EvidenceItem
from app.models.insights import WeeklyCareerInsight
from app.models.market_baseline import MarketBaseline, MarketBaselineSignal

# ── F6: Personal Runway ─────────────────────────────────────────────
from app.models.financial import FinancialAsset, FinancialProfile, RunwayCalculation

# ── F7: What If I Get Fired ─────────────────────────────────────────
from app.models.layoff import LayoffSimulation, SimulationActionItem

# ── Skill Missions ──────────────────────────────────────────────────
from app.models.missions import SkillMission

__all__ = [
    # User
    "User",
    "OAuthLoginCode",
    "AuthActionToken",
    "UserProfile",
    "UserCV",
    "CVConfirmationReceipt",
    "StorageDeletionJob",
    # Master data
    "Industry",
    "Role",
    "Skill",
    "Tool",
    # Junction
    "UserSkill",
    # F1
    "HealthAssessment",
    "HealthScoreBreakdown",
    # F2
    "RiskScan",
    "RiskFactor",
    "RiskScanSkill",
    # F3
    "AiExposureAssessment",
    "ExposedActivity",
    "SkillRelevance",
    "AiExposureSkill",
    "AiExposureTool",
    # F4
    "PivotAnalysis",
    "PivotPreferredRole",
    "PivotSkillGap",
    # F5
    "EvidenceItem",
    "WeeklyCareerInsight",
    "MarketBaseline",
    "MarketBaselineSignal",
    # F6
    "FinancialProfile",
    "FinancialAsset",
    "RunwayCalculation",
    # F7
    "LayoffSimulation",
    "SimulationActionItem",
    # Missions
    "SkillMission",
]
