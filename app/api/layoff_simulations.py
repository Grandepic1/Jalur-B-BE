from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.ai_assessments import _health_response
from app.api.auth import get_verified_user
from app.api.financial import TARGET_RUNWAY_MONTHS, _asset_totals, _runway_preview
from app.core.ai import AIProviderError, StructuredAIProvider, get_ai_provider
from app.core.database import get_db
from app.core.scoring import (
    SCORE_VERSION,
    PROMPT_VERSION,
    score,
    weighted,
)
from app.models.ai_exposure import AiExposureAssessment
from app.models.ai_features import (
    LayoffSimulationRequest,
    LayoffSimulationResult,
    SimulationAIResult,
)
from app.models.evidence import EvidenceItem
from app.models.financial import FinancialProfile
from app.models.health import HealthAssessment
from app.models.layoff import LayoffSimulation, SimulationActionItem
from app.models.pivot import PivotAnalysis, PivotPreferredRole, PivotSkillGap
from app.models.master import Skill
from app.models.risk import RiskScan
from app.models.user import User


router = APIRouter(prefix="/api/layoff-simulations", tags=["layoff simulations"])

SIMULATION_INSTRUCTION = """
Write a concise Indonesian layoff-scenario explanation and a practical emergency action
plan using only the calculated values, roles, and skill gaps supplied. Do not recalculate
or change scores. Do not promise employment outcomes or invent financial values. Produce
between three and six ordered actions spanning immediate, short_term, and long_term phases.
"""


async def _latest(db: AsyncSession, model, user_id: int, timestamp):
    return await db.scalar(
        select(model)
        .where(model.user_id == user_id)
        .order_by(timestamp.desc(), model.id.desc())
        .limit(1)
    )


def _response(
    simulation: LayoffSimulation, items: list[SimulationActionItem]
) -> LayoffSimulationResult:
    return LayoffSimulationResult(
        id=simulation.id,
        scenario=simulation.scenario,
        simulated_at=simulation.simulated_at,
        career_readiness_score=simulation.career_readiness_score or Decimal("0"),
        financial_readiness_score=simulation.financial_readiness_score or Decimal("0"),
        skill_relevance_score=simulation.skill_relevance_score or Decimal("0"),
        job_mobility_score=simulation.job_mobility_score or Decimal("0"),
        overall_resilience_score=simulation.overall_resilience_score or Decimal("0"),
        financial_runway_months=simulation.financial_runway_months or Decimal("0"),
        target_runway_months=simulation.target_runway_months or TARGET_RUNWAY_MONTHS,
        financial_gap=simulation.financial_gap or Decimal("0"),
        evidence_count=simulation.evidence_count,
        summary=simulation.summary or "",
        action_items=[
            {
                "id": item.id,
                "step_order": item.step_order,
                "phase": item.phase.value,
                "title": item.title,
                "description": item.description,
                "due_date": item.due_date,
                "is_completed": item.is_completed,
            }
            for item in items
        ],
        model=simulation.provider_model or "legacy",
        scoring_version=simulation.scoring_version or "legacy",
    )


@router.post(
    "", response_model=LayoffSimulationResult, status_code=status.HTTP_201_CREATED
)
async def create_layoff_simulation(
    payload: LayoffSimulationRequest,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
    provider: StructuredAIProvider = Depends(get_ai_provider),
) -> LayoffSimulationResult:
    health = await _latest(db, HealthAssessment, user.id, HealthAssessment.assessed_at)
    exposure = await _latest(
        db, AiExposureAssessment, user.id, AiExposureAssessment.assessed_at
    )
    pivot = await _latest(db, PivotAnalysis, user.id, PivotAnalysis.analyzed_at)
    risk = await _latest(db, RiskScan, user.id, RiskScan.scanned_at)
    financial_profile = await db.scalar(
        select(FinancialProfile).where(FinancialProfile.user_id == user.id)
    )
    missing = [
        name
        for name, value in (
            ("career_health", health),
            ("ai_exposure", exposure),
            ("career_pivot", pivot),
            ("career_risk", risk),
            ("financial_profile", financial_profile),
        )
        if value is None
    ]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "simulation_prerequisites_missing", "missing": missing},
        )

    total_assets, liquid_assets = await _asset_totals(db, user.id)
    runway = _runway_preview(financial_profile, total_assets, liquid_assets)
    financial_score = score(financial_profile.financial_readiness_score)
    career_score = score((await _health_response(db, health)).score)
    skill_score = score(exposure.skill_relevance_score or 0)
    mobility_score = score(pivot.match_score)
    resilience_score = weighted(
        [
            (financial_score, Decimal("0.30")),
            (career_score, Decimal("0.30")),
            (skill_score, Decimal("0.20")),
            (mobility_score, Decimal("0.20")),
        ]
    )
    financial_gap = max(
        TARGET_RUNWAY_MONTHS * runway.monthly_burn - runway.liquid_assets,
        Decimal("0"),
    )
    evidence_count = (
        await db.scalar(
            select(func.count())
            .select_from(EvidenceItem)
            .where(EvidenceItem.user_id == user.id)
        )
    ) or 0
    roles = list(
        (
            await db.scalars(
                select(PivotPreferredRole)
                .where(PivotPreferredRole.analysis_id == pivot.id)
                .order_by(PivotPreferredRole.match_score.desc())
            )
        ).all()
    )
    gap_names = list(
        (
            await db.scalars(
                select(Skill.name)
                .join(PivotSkillGap, PivotSkillGap.skill_id == Skill.id)
                .where(PivotSkillGap.analysis_id == pivot.id)
                .order_by(func.lower(Skill.name))
            )
        ).all()
    )
    input_snapshot = {
        "scenario": payload.scenario.value,
        "scores": {
            "career_readiness": str(career_score),
            "financial_readiness": str(financial_score),
            "skill_relevance": str(skill_score),
            "job_mobility": str(mobility_score),
            "overall_resilience": str(resilience_score),
            "career_risk": str(risk.overall_score or 0),
        },
        "financial": {
            "runway_months": str(runway.financial_runway_months),
            "target_months": str(TARGET_RUNWAY_MONTHS),
            "gap_amount": str(financial_gap),
            "currency": runway.currency,
        },
        "evidence_count": evidence_count,
        "pivot_roles": [
            {
                "role_name": role.role_name,
                "match_score": str(role.match_score or 0),
                "preparation_time_months": role.preparation_time_months,
            }
            for role in roles
        ],
        "skill_gaps": gap_names,
    }
    try:
        narrative = await provider.generate_structured(
            response_type=SimulationAIResult,
            system_instruction=SIMULATION_INSTRUCTION,
            input_data=input_snapshot,
        )
    except AIProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None

    preparation_months = max(
        (role.preparation_time_months or 0 for role in roles), default=0
    )
    simulation = LayoffSimulation(
        user_id=user.id,
        scenario=payload.scenario,
        best_pivot_analysis_id=pivot.id,
        career_readiness_score=career_score,
        financial_readiness_score=financial_score,
        skill_relevance_score=skill_score,
        job_mobility_score=mobility_score,
        overall_resilience_score=resilience_score,
        financial_runway_months=runway.financial_runway_months,
        target_runway_months=TARGET_RUNWAY_MONTHS,
        financial_gap=financial_gap,
        estimated_preparation_time_months=preparation_months,
        evidence_count=evidence_count,
        summary=narrative.summary,
        provider_model=provider.model,
        prompt_version=PROMPT_VERSION,
        scoring_version=SCORE_VERSION,
        input_snapshot=input_snapshot,
    )
    db.add(simulation)
    await db.flush()
    scenario_delay = {
        "tomorrow": 1,
        "one_month": 30,
        "three_months": 90,
    }[payload.scenario.value]
    today = datetime.now(UTC).date()
    items: list[SimulationActionItem] = []
    for order, generated in enumerate(narrative.action_items, start=1):
        item = SimulationActionItem(
            simulation_id=simulation.id,
            step_order=order,
            phase=generated.phase,
            title=generated.title,
            description=generated.description,
            due_date=today + timedelta(days=scenario_delay + generated.due_in_days),
            is_completed=False,
        )
        db.add(item)
        items.append(item)
    await db.commit()
    await db.refresh(simulation)
    for item in items:
        await db.refresh(item)
    return _response(simulation, items)


@router.get("/latest", response_model=LayoffSimulationResult)
async def get_latest_layoff_simulation(
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> LayoffSimulationResult:
    simulation = await _latest(
        db, LayoffSimulation, user.id, LayoffSimulation.simulated_at
    )
    if simulation is None:
        raise HTTPException(status_code=404, detail="Simulation not found")
    items = list(
        (
            await db.scalars(
                select(SimulationActionItem)
                .where(SimulationActionItem.simulation_id == simulation.id)
                .order_by(SimulationActionItem.step_order)
            )
        ).all()
    )
    return _response(simulation, items)


@router.get("/{simulation_id}", response_model=LayoffSimulationResult)
async def get_layoff_simulation(
    simulation_id: int,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> LayoffSimulationResult:
    simulation = await db.scalar(
        select(LayoffSimulation).where(
            LayoffSimulation.id == simulation_id,
            LayoffSimulation.user_id == user.id,
        )
    )
    if simulation is None:
        raise HTTPException(status_code=404, detail="Simulation not found")
    items = list(
        (
            await db.scalars(
                select(SimulationActionItem)
                .where(SimulationActionItem.simulation_id == simulation.id)
                .order_by(SimulationActionItem.step_order)
            )
        ).all()
    )
    return _response(simulation, items)
