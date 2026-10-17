import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.ai_assessments import _health_response
from app.api.auth import get_verified_user
from app.api.financial import (
    REFERENCE_RUNWAY_MONTHS,
    _asset_totals,
    _get_employment_terms,
    _personal_target_months,
    _runway_preview,
)
from app.core.ai import AIProviderError, StructuredAIProvider, get_ai_provider
from app.core.database import get_db
from app.core.entitlements import (
    REGULATION_VERSION,
    ExitTerms,
    ExitType,
    compute_exit_entitlements,
    exit_type_consistency_error,
    runway_months,
)
from app.core.scoring import (
    PROMPT_VERSION,
    SCORE_VERSION,
    overall_resilience,
    score,
)
from app.core.transition import (
    horizon_months_until,
    select_preparation_role,
    transition_gap,
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
from app.models.layoff import (
    LayoffScenario,
    LayoffSimulation,
    SimulationActionItem,
    SimulationRoleTransition,
    TransitionGapStatus,
)
from app.models.master import Skill
from app.models.pivot import PivotAnalysis, PivotPreferredRole, PivotSkillGap
from app.models.risk import RiskScan
from app.models.user import User

router = APIRouter(prefix="/api/layoff-simulations", tags=["layoff simulations"])

# The action-item schedule is derived from the exit ground. This is the only thing the
# old tomorrow / one_month / three_months choice still influences; it no longer
# (mis)represents the financial scenario, which the exit ground now fully determines.
SCHEDULING_SCENARIO: dict[ExitType, LayoffScenario] = {
    ExitType.bankruptcy: LayoffScenario.tomorrow,
    ExitType.efficiency_due_to_loss: LayoffScenario.tomorrow,
    ExitType.efficiency_prevent_loss: LayoffScenario.one_month,
    ExitType.closure_not_loss: LayoffScenario.one_month,
    ExitType.pkwt_ends_on_schedule: LayoffScenario.three_months,
    ExitType.resign: LayoffScenario.three_months,
}

SIMULATION_INSTRUCTION = """
Write a concise Indonesian layoff-scenario explanation and a practical emergency action
plan using only the calculated values, roles, and skill gaps supplied. Do not
recalculate or change scores. Do not promise employment outcomes or invent financial
values. Produce between three and six ordered actions spanning immediate, short_term,
and long_term phases.

Write for an end user, not a developer. Never repeat JSON keys, enum values, snake_case
identifiers, or English implementation labels. Integrate the facts into natural
Use natural Indonesian sentences instead of listing raw fields. For example, say
"satu bulan" rather than
"one_month", "ketahanan keseluruhan" rather than "overall_resilience", "kesiapan
finansial" rather than "financial_readiness", and "masa aman finansial" rather than
"runway_months".
"""

NARRATIVE_TERMS = {
    "tomorrow": "besok",
    "one_month": "satu bulan",
    "three_months": "tiga bulan",
    "overall_resilience": "ketahanan keseluruhan",
    "financial_readiness": "kesiapan finansial",
    "career_readiness": "kesiapan karier",
    "skill_relevance": "relevansi keterampilan",
    "job_mobility": "mobilitas karier",
    "career_risk": "risiko karier",
    "runway_months": "masa aman finansial",
    "target_months": "target masa aman",
    "gap_amount": "kekurangan dana",
    "currency": "mata uang",
    "evidence_count": "jumlah bukti karier",
    "pivot_roles": "pilihan peran transisi",
    "role_name": "nama peran",
    "match_score": "skor kecocokan",
    "preparation_time_months": "waktu persiapan dalam bulan",
    "search_time_months": "asumsi waktu mencari kerja",
    "transition_gap_months": "selisih waktu transisi",
    "transition_gap_status": "status selisih waktu transisi",
    "surplus": "surplus",
    "deficit": "defisit",
    "skill_gaps": "kesenjangan keterampilan",
    "short_term": "jangka pendek",
    "long_term": "jangka panjang",
    "immediate": "segera",
}


def _naturalize_narrative(value: str) -> str:
    for identifier, label in NARRATIVE_TERMS.items():
        value = re.sub(
            rf"\b{re.escape(identifier)}\b", label, value, flags=re.IGNORECASE
        )
    return re.sub(
        r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b",
        lambda match: match.group().replace("_", " "),
        value,
        flags=re.IGNORECASE,
    )


async def _latest(db: AsyncSession, model, user_id: int, timestamp):
    return await db.scalar(
        select(model)
        .where(model.user_id == user_id)
        .order_by(timestamp.desc(), model.id.desc())
        .limit(1)
    )


async def _load_transitions(
    db: AsyncSession, simulation_id: int
) -> list[SimulationRoleTransition]:
    return list(
        (
            await db.scalars(
                select(SimulationRoleTransition)
                .where(SimulationRoleTransition.simulation_id == simulation_id)
                .order_by(SimulationRoleTransition.match_score.desc())
            )
        ).all()
    )


def _response(
    simulation: LayoffSimulation,
    items: list[SimulationActionItem],
    transitions: list[SimulationRoleTransition],
) -> LayoffSimulationResult:
    snapshot = simulation.input_snapshot or {}
    raw_insufficient = snapshot.get("insufficient_data")
    insufficient = [str(item) for item in raw_insufficient] if isinstance(raw_insufficient, list) else []
    if simulation.skill_relevance_score is None and "skill_relevance" not in insufficient:
        insufficient.append("skill_relevance")
    if simulation.job_mobility_score is None and "mobility" not in insufficient:
        insufficient.append("mobility")
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
        target_runway_months=(
            simulation.target_runway_months or REFERENCE_RUNWAY_MONTHS
        ),
        financial_gap=simulation.financial_gap or Decimal("0"),
        evidence_count=simulation.evidence_count,
        summary=_naturalize_narrative(simulation.summary or ""),
        action_items=[
            {
                "id": item.id,
                "step_order": item.step_order,
                "phase": item.phase.value,
                "title": _naturalize_narrative(item.title),
                "description": _naturalize_narrative(item.description),
                "due_date": item.due_date,
                "is_completed": item.is_completed,
            }
            for item in items
        ],
        model=simulation.provider_model or "legacy",
        scoring_version=simulation.scoring_version or "legacy",
        exit_type=simulation.exit_type,
        regulation_version=simulation.regulation_version,
        search_time_months=simulation.search_time_months,
        preparation_time_months=(
            Decimal(simulation.estimated_preparation_time_months)
            if simulation.estimated_preparation_time_months is not None
            else None
        ),
        transition_role_name=simulation.transition_role_name,
        transition_gap_months=simulation.transition_gap_months,
        transition_gap_status=simulation.transition_gap_status,
        role_transitions=[
            {
                "role_name": row.role_name,
                "match_score": str(row.match_score),
                "preparation_time_months": str(row.preparation_time_months),
                "search_time_months": str(row.search_time_months),
                "transition_months": str(row.transition_months),
                "transition_gap_months": str(row.transition_gap_months),
                "status": row.status.value,
                "recommended_monthly_saving": str(row.recommended_monthly_saving),
                "months_saved_by_closing_one_gap": str(
                    row.months_saved_by_closing_one_gap
                ),
                "note": row.note,
            }
            for row in transitions
        ],
        insufficient_data=insufficient,
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
    terms = await _get_employment_terms(db, user.id)
    missing = [
        name
        for name, value in (
            ("career_health", health),
            ("ai_exposure", exposure),
            ("career_pivot", pivot),
            ("career_risk", risk),
            ("financial_profile", financial_profile),
            # An exit-aware simulation needs wage and contract facts: without them the
            # statutory entitlements that drive the runway cannot be computed at all.
            ("employment_terms", terms),
        )
        if value is None
    ]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "simulation_prerequisites_missing", "missing": missing},
        )
    assert terms is not None  # narrowed by the prerequisite check above

    inconsistency = exit_type_consistency_error(
        payload.exit_type, terms.employment_type
    )
    if inconsistency is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "exit_type_contract_mismatch", "message": inconsistency},
        )

    total_assets, liquid_assets = await _asset_totals(db, user.id)
    target_months, target_basis, _ = await _personal_target_months(db, user.id)
    runway = await _runway_preview(
        financial_profile,
        total_assets,
        liquid_assets,
        target_months,
        target_basis=target_basis,
        terms=terms,
    )
    entitlements = compute_exit_entitlements(
        ExitTerms(
            exit_type=payload.exit_type,
            monthly_wage_base=terms.monthly_wage_base,
            tenure_months=int(terms.tenure_months or 0),
            employment_type=terms.employment_type,
            bpjs_tk_active=terms.bpjs_tk_active,
            bpjs_contributions_last_24_months=terms.bpjs_contribution_months_last_24,
            bpjs_consecutive_months=terms.bpjs_consecutive_months,
            age_years=terms.age_years or 0,
            jkn_active=terms.jkn_active,
            jht_balance=terms.jht_balance or Decimal("0"),
            unused_leave_days=terms.unused_leave_days,
            normative_rights_collectable=payload.normative_rights_collectable,
        )
    )
    # Exit-aware runway: the statutory layers depend on how the job actually ends.
    exit_runway = runway_months(
        liquid_assets=liquid_assets + entitlements.liquid_normative,
        monthly_burn=runway.monthly_burn,
        jkp_monthly=entitlements.jkp.monthly_benefit,
        jkp_months=entitlements.jkp.months,
    )
    financial_score = score(financial_profile.financial_readiness_score)
    career_score = score((await _health_response(db, health)).score)
    # Descriptive only. Skill relevance and mobility are already inside Career Readiness,
    # so they are reported but carry no weight in Overall Resilience.
    skill_score = exposure.skill_relevance_score
    mobility_score = score(pivot.match_score)
    resilience_score = overall_resilience(
        career_readiness_score=career_score,
        financial_readiness_score=financial_score,
    )
    if resilience_score is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "resilience_unavailable",
                "message": "Career readiness and financial readiness are both required",
            },
        )
    insufficient_data: list[str] = []
    if skill_score is None:
        insufficient_data.append("skill_relevance")
    if pivot.match_score is None:
        insufficient_data.append("mobility")
    # Deficit against the personal target, measured in money rather than months.
    financial_gap = max(
        (target_months - exit_runway) * runway.monthly_burn, Decimal("0")
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
    today = datetime.now(UTC).date()
    gap_counts = {
        role_id: count
        for role_id, count in (
            await db.execute(
                select(PivotSkillGap.preferred_role_id, func.count())
                .where(PivotSkillGap.analysis_id == pivot.id)
                .group_by(PivotSkillGap.preferred_role_id)
            )
        ).all()
        if role_id is not None
    }
    role_rows = [
        (
            role,
            role.role_name,
            Decimal(role.match_score or 0),
            Decimal(int(role.preparation_time_months or 0)),
        )
        for role in roles
    ]
    # T_prep comes from the role the user chooses, defaulting to the highest match score.
    # Taking the maximum across every role made one slow option define the whole outlook.
    selected_role_name: str | None = None
    if role_rows:
        selected_role_name, _, _ = select_preparation_role(
            [(name, match, int(prep)) for _, name, match, prep in role_rows],
            preferred_role_name=payload.preferred_role_name,
        )
    horizon = horizon_months_until(today, today)
    transitions = [
        (
            role,
            transition_gap(
                role_name=name,
                match_score=match,
                preparation_time_months=prep,
                exit_runway_months=exit_runway,
                monthly_burn=runway.monthly_burn,
                search_time_months=payload.search_time_months,
                horizon_months=horizon,
                gap_count=gap_counts.get(role.id, 0),
            ),
        )
        for role, name, match, prep in role_rows
    ]
    selected = next(
        (
            (role, result)
            for role, result in transitions
            if result.role_name == selected_role_name
        ),
        transitions[0] if transitions else None,
    )

    input_snapshot = {
        "exit_type": payload.exit_type.value,
        "regulation_version": REGULATION_VERSION,
        "search_time_months": str(payload.search_time_months),
        "scores": {
            "career_readiness": str(career_score),
            "financial_readiness": str(financial_score),
            "skill_relevance": None if skill_score is None else str(skill_score),
            "job_mobility": str(mobility_score),
            "overall_resilience": str(resilience_score),
            "career_risk": str(risk.overall_score or 0),
        },
        "financial": {
            "runway_months": str(runway.financial_runway_months),
            "exit_runway_months": str(exit_runway),
            "target_months": str(target_months),
            "target_basis": target_basis,
            "reference_months": str(REFERENCE_RUNWAY_MONTHS),
            "gap_amount": str(financial_gap),
            "currency": runway.currency,
        },
        "entitlements": {
            "pesangon_months": str(entitlements.pesangon_months),
            "upmk_months": str(entitlements.upmk_months),
            "gross_lump_sum": str(entitlements.gross_lump_sum),
            "severance_tax": str(entitlements.severance_tax),
            "net_lump_sum": str(entitlements.net_lump_sum),
            "normative_collectable": entitlements.normative_collectable,
            "jkp_eligible": entitlements.jkp.eligible,
            "jkp_monthly_benefit": str(entitlements.jkp.monthly_benefit),
        },
        "transition": None
        if selected is None
        else {
            "role_name": selected[1].role_name,
            "preparation_time_months": str(selected[1].preparation_time_months),
            "search_time_months": str(selected[1].search_time_months),
            "transition_months": str(selected[1].transition_months),
            "transition_gap_months": str(selected[1].transition_gap_months),
            "transition_gap_status": selected[1].status,
        },
        "role_transitions": [
            {
                "role_name": result.role_name,
                "match_score": str(result.match_score),
                "preparation_time_months": str(result.preparation_time_months),
                "transition_gap_months": str(result.transition_gap_months),
                "status": result.status,
                "recommended_monthly_saving": str(result.recommended_monthly_saving),
                "months_saved_by_closing_one_gap": str(
                    result.months_saved_by_closing_one_gap
                ),
            }
            for _, result in transitions
        ],
        "evidence_count": evidence_count,
        "pivot_roles": [
            {
                "role_name": name,
                "match_score": str(match),
                "preparation_time_months": int(prep),
            }
            for _, name, match, prep in role_rows
        ],
        "skill_gaps": gap_names,
        "insufficient_data": insufficient_data,
    }
    try:
        narrative = await provider.generate_structured(
            response_type=SimulationAIResult,
            system_instruction=SIMULATION_INSTRUCTION,
            input_data=input_snapshot,
        )
    except AIProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None

    simulation = LayoffSimulation(
        user_id=user.id,
        scenario=SCHEDULING_SCENARIO[payload.exit_type],
        exit_type=payload.exit_type,
        regulation_version=REGULATION_VERSION,
        search_time_months=payload.search_time_months,
        best_pivot_analysis_id=pivot.id,
        career_readiness_score=career_score,
        financial_readiness_score=financial_score,
        skill_relevance_score=skill_score,
        job_mobility_score=mobility_score,
        overall_resilience_score=resilience_score,
        financial_runway_months=exit_runway,
        target_runway_months=target_months,
        financial_gap=financial_gap,
        estimated_preparation_time_months=(
            int(selected[1].preparation_time_months) if selected else None
        ),
        transition_role_name=selected[1].role_name if selected else None,
        transition_gap_months=selected[1].transition_gap_months if selected else None,
        transition_gap_status=selected[1].status if selected else None,
        evidence_count=evidence_count,
        summary=_naturalize_narrative(narrative.summary),
        provider_model=provider.model,
        prompt_version=PROMPT_VERSION,
        scoring_version=SCORE_VERSION,
        input_snapshot=input_snapshot,
    )
    db.add(simulation)
    await db.flush()
    saved_transitions: list[SimulationRoleTransition] = []
    for _, result in transitions:
        row = SimulationRoleTransition(
            simulation_id=simulation.id,
            role_name=result.role_name,
            match_score=result.match_score,
            preparation_time_months=result.preparation_time_months,
            search_time_months=result.search_time_months,
            transition_months=result.transition_months,
            transition_gap_months=result.transition_gap_months,
            status=TransitionGapStatus(result.status),
            recommended_monthly_saving=result.recommended_monthly_saving,
            months_saved_by_closing_one_gap=result.months_saved_by_closing_one_gap,
            note=result.note,
        )
        db.add(row)
        saved_transitions.append(row)
    scenario_delay = {
        LayoffScenario.tomorrow: 1,
        LayoffScenario.one_month: 30,
        LayoffScenario.three_months: 90,
    }[SCHEDULING_SCENARIO[payload.exit_type]]
    items: list[SimulationActionItem] = []
    for order, generated in enumerate(narrative.action_items, start=1):
        item = SimulationActionItem(
            simulation_id=simulation.id,
            step_order=order,
            phase=generated.phase,
            title=_naturalize_narrative(generated.title),
            description=_naturalize_narrative(generated.description),
            due_date=today + timedelta(days=scenario_delay + generated.due_in_days),
            is_completed=False,
        )
        db.add(item)
        items.append(item)
    await db.commit()
    await db.refresh(simulation)
    for item in items:
        await db.refresh(item)
    for row in saved_transitions:
        await db.refresh(row)
    return _response(simulation, items, saved_transitions)


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
    return _response(simulation, items, await _load_transitions(db, simulation.id))


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
    return _response(simulation, items, await _load_transitions(db, simulation.id))
