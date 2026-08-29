from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_verified_user
from app.api.evidence import evidence_response
from app.api.financial import _asset_totals, _runway_preview
from app.core.database import get_db
from app.models.dashboard import (
    DashboardEvidenceSummary,
    DashboardFinancialSummary,
    DashboardMissionSummary,
    DashboardProfileSummary,
    DashboardResponse,
    DashboardSkillsSummary,
)
from app.models.evidence import EvidenceItem
from app.models.financial import FinancialProfile, RunwayCalculation
from app.models.missions import MissionStatus, SkillMission, SkillMissionResponse
from app.models.profile import UserProfile
from app.models.user import User, UserResponse
from app.models.user_skills import UserSkill


router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
async def get_dashboard(
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> DashboardResponse:
    today = datetime.now(UTC).date()
    profile = await db.scalar(
        select(UserProfile).where(UserProfile.user_id == user.id)
    )

    skill_total, rated_skills = (
        await db.execute(
            select(
                func.count(),
                func.count().filter(UserSkill.proficiency_level.is_not(None)),
            ).where(UserSkill.user_id == user.id)
        )
    ).one()

    evidence_rows = (
        await db.execute(
            select(EvidenceItem.evidence_type, func.count())
            .where(EvidenceItem.user_id == user.id)
            .group_by(EvidenceItem.evidence_type)
        )
    ).all()
    evidence_by_type = {
        evidence_type: count for evidence_type, count in evidence_rows
    }
    recent_evidence = list(
        (
            await db.scalars(
                select(EvidenceItem)
                .where(EvidenceItem.user_id == user.id)
                .order_by(EvidenceItem.created_at.desc(), EvidenceItem.id.desc())
                .limit(3)
            )
        ).all()
    )

    mission_rows = (
        await db.execute(
            select(SkillMission.status, func.count())
            .where(SkillMission.user_id == user.id)
            .group_by(SkillMission.status)
        )
    ).all()
    mission_counts = {
        mission_status: count for mission_status, count in mission_rows
    }
    mission_total = sum(mission_counts.values())
    mission_completed = mission_counts.get(MissionStatus.completed, 0)
    mission_overdue = await db.scalar(
        select(func.count())
        .select_from(SkillMission)
        .where(
            SkillMission.user_id == user.id,
            SkillMission.due_date < today,
            SkillMission.status != MissionStatus.completed,
        )
    )
    next_mission = await db.scalar(
        select(SkillMission)
        .where(
            SkillMission.user_id == user.id,
            SkillMission.status != MissionStatus.completed,
        )
        .order_by(
            case((SkillMission.due_date.is_(None), 1), else_=0),
            SkillMission.due_date.asc(),
            SkillMission.created_at.asc(),
            SkillMission.id.asc(),
        )
        .limit(1)
    )
    completion_percentage = (
        (Decimal(mission_completed) * Decimal("100") / Decimal(mission_total)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if mission_total
        else Decimal("0")
    )

    financial_profile = await db.scalar(
        select(FinancialProfile).where(FinancialProfile.user_id == user.id)
    )
    financial = None
    if financial_profile is not None:
        total_assets, liquid_assets = await _asset_totals(db, user.id)
        runway = _runway_preview(financial_profile, total_assets, liquid_assets)
        latest_saved_at = await db.scalar(
            select(RunwayCalculation.calculated_at)
            .where(RunwayCalculation.user_id == user.id)
            .order_by(
                RunwayCalculation.calculated_at.desc(),
                RunwayCalculation.id.desc(),
            )
            .limit(1)
        )
        financial = DashboardFinancialSummary(
            total_assets=runway.total_assets,
            liquid_assets=runway.liquid_assets,
            monthly_burn=runway.monthly_burn,
            runway_months=runway.financial_runway_months,
            currency=runway.currency,
            latest_saved_at=latest_saved_at,
        )

    return DashboardResponse(
        generated_at=datetime.now(UTC),
        account=UserResponse.model_validate(user),
        onboarding_completed=bool(
            profile is not None and profile.onboarding_completed_at is not None
        ),
        profile=(
            DashboardProfileSummary(
                full_name=profile.full_name,
                current_role_name=profile.current_role_name,
                industry_name=profile.industry_name,
            )
            if profile is not None
            else None
        ),
        skills=DashboardSkillsSummary(total=skill_total, rated=rated_skills),
        evidence=DashboardEvidenceSummary(
            total=sum(evidence_by_type.values()),
            by_type=evidence_by_type,
            recent=[evidence_response(item) for item in recent_evidence],
        ),
        missions=DashboardMissionSummary(
            total=mission_total,
            todo=mission_counts.get(MissionStatus.todo, 0),
            in_progress=mission_counts.get(MissionStatus.in_progress, 0),
            completed=mission_completed,
            overdue=mission_overdue or 0,
            completion_percentage=completion_percentage,
            next_mission=(
                SkillMissionResponse.model_validate(next_mission)
                if next_mission is not None
                else None
            ),
        ),
        financial=financial,
    )
