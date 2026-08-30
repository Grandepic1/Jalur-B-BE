from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_verified_user
from app.core.ai import AIProviderError, StructuredAIProvider, get_ai_provider
from app.core.database import get_db
from app.core.scoring import PROMPT_VERSION
from app.models.ai_exposure import AiExposureAssessment
from app.models.ai_features import DashboardInsightAIResult, DashboardInsightResponse
from app.models.evidence import EvidenceItem
from app.models.health import HealthAssessment
from app.models.insights import WeeklyCareerInsight
from app.models.pivot import PivotAnalysis
from app.models.profile import UserProfile
from app.models.risk import RiskScan
from app.models.user import User


router = APIRouter(prefix="/api/ai/insights", tags=["AI insights"])

INSIGHT_INSTRUCTION = """
Write two concise Indonesian messages from the supplied factual assessment state. The
weekly insight explains one meaningful observation. The next action explains the supplied
server-selected action and must not suggest or mention a different destination or URL. Do not invent scores,
market statistics, deadlines, or facts. Do not include markdown.
"""


async def _latest(db: AsyncSession, model, user_id: int, timestamp):
    return await db.scalar(
        select(model)
        .where(model.user_id == user_id)
        .order_by(timestamp.desc(), model.id.desc())
        .limit(1)
    )


def _response(item: WeeklyCareerInsight) -> DashboardInsightResponse:
    return DashboardInsightResponse(
        weekly_insight=item.weekly_insight,
        next_action=item.next_action,
        next_action_path=item.next_action_path,
        model=item.provider_model,
    )


@router.get("", response_model=DashboardInsightResponse)
async def get_weekly_insight(
    refresh: bool = Query(False),
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
    provider: StructuredAIProvider = Depends(get_ai_provider),
) -> DashboardInsightResponse:
    today = datetime.now(UTC).date()
    week_start = today - timedelta(days=today.weekday())
    existing = await db.scalar(
        select(WeeklyCareerInsight).where(
            WeeklyCareerInsight.user_id == user.id,
            WeeklyCareerInsight.week_start == week_start,
        )
    )
    if existing is not None and not refresh:
        return _response(existing)

    profile = await db.scalar(select(UserProfile).where(UserProfile.user_id == user.id))
    if profile is None:
        raise HTTPException(status_code=409, detail="Complete onboarding first")
    health = await _latest(db, HealthAssessment, user.id, HealthAssessment.assessed_at)
    risk = await _latest(db, RiskScan, user.id, RiskScan.scanned_at)
    exposure = await _latest(
        db, AiExposureAssessment, user.id, AiExposureAssessment.assessed_at
    )
    pivot = await _latest(db, PivotAnalysis, user.id, PivotAnalysis.analyzed_at)
    evidence_count = (
        await db.scalar(
            select(func.count())
            .select_from(EvidenceItem)
            .where(EvidenceItem.user_id == user.id)
        )
    ) or 0

    if health is None:
        action_type = "complete_career_assessment"
        action_path = "/dashboard/kesehatan-karier"
    elif exposure is None:
        action_type = "analyze_skill_and_ai_exposure"
        action_path = "/dashboard/skill"
    elif pivot is None:
        action_type = "analyze_career_pivot"
        action_path = "/dashboard/jalur-karier"
    elif risk is None:
        action_type = "scan_career_risk"
        action_path = "/dashboard/risiko-karier"
    elif evidence_count == 0:
        action_type = "add_career_evidence"
        action_path = "/dashboard/bukti-karier"
    else:
        action_type = "review_lowest_assessment_dimension"
        action_path = "/dashboard/kesehatan-karier"

    facts = {
        "role": profile.current_role_name,
        "industry": profile.industry_name,
        "career_health_score": str(health.overall_score) if health else None,
        "career_risk_score": str(risk.overall_score) if risk else None,
        "ai_exposure_score": str(exposure.overall_exposure_score) if exposure else None,
        "skill_relevance_score": str(exposure.skill_relevance_score)
        if exposure
        else None,
        "best_pivot_match": str(pivot.match_score) if pivot else None,
        "evidence_count": evidence_count,
        "selected_action": action_type,
        "selected_action_path": action_path,
    }
    try:
        generated = await provider.generate_structured(
            response_type=DashboardInsightAIResult,
            system_instruction=INSIGHT_INSTRUCTION,
            input_data=facts,
        )
    except AIProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None

    if existing is not None:
        await db.delete(existing)
        await db.flush()
    item = WeeklyCareerInsight(
        user_id=user.id,
        week_start=week_start,
        weekly_insight=generated.weekly_insight,
        next_action=generated.next_action,
        next_action_path=action_path,
        provider_model=provider.model,
        prompt_version=PROMPT_VERSION,
    )
    db.add(item)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        winner = await db.scalar(
            select(WeeklyCareerInsight).where(
                WeeklyCareerInsight.user_id == user.id,
                WeeklyCareerInsight.week_start == week_start,
            )
        )
        if winner is None:
            raise
        return _response(winner)
    await db.refresh(item)
    return _response(item)
