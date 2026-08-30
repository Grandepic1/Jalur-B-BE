from decimal import Decimal
from math import ceil

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.auth import get_verified_user
from app.api.financial import TARGET_RUNWAY_MONTHS, _asset_totals, _runway_preview
from app.core.ai import (
    AIProviderError,
    AIProviderUnavailable,
    StructuredAIProvider,
    get_ai_provider,
)
from app.core.database import get_db
from app.core.scoring import (
    EXPOSURE_SCORES,
    PROMPT_VERSION,
    RELEVANCE_SCORES,
    SCORE_VERSION,
    SIGNAL_SCORES,
    average,
    career_health,
    exposure_level,
    health_level,
    risk_level,
    score,
    weighted,
)
from app.models.ai_exposure import (
    AiExposureAssessment,
    AiExposureSkill,
    ExposureLevel,
    ExposedActivity,
    SkillRelevance,
    SkillRelevanceStatus,
)
from app.models.ai_features import (
    CareerAnalysisAIResult,
    CareerAssessmentBundleResponse,
    CareerAssessmentRequest,
    ExposureAssessmentResult,
    HealthAssessmentResult,
    PivotAssessmentResult,
    PivotRoleResponse,
    RiskAssessmentResult,
    ScoreExplanation,
)
from app.models.evidence import EvidenceItem
from app.models.financial import FinancialProfile
from app.models.health import HealthAssessment, HealthLevel, HealthScoreBreakdown
from app.models.master import Skill
from app.models.market_baseline import (
    MarketBaseline,
    MarketBaselineSignal,
    MarketBaselineStatus,
    MarketSubjectType,
)
from app.models.pivot import GapLevel, PivotAnalysis, PivotPreferredRole, PivotSkillGap
from app.models.profile import UserProfile
from app.models.risk import RiskFactor, RiskLevel, RiskScan, RiskScanSkill
from app.models.user import User
from app.models.user_skills import UserSkill


router = APIRouter(tags=["AI assessments"])

FACTOR_TITLES = {
    "performance_growth": "Performa & Perkembangan",
    "skill_relevance": "Relevansi Skill",
    "adaptability": "Adaptasi Perubahan",
    "mobility": "Kesiapan Berpindah",
    "financial_readiness": "Financial Readiness",
    "ai_advancement": "AI Disruption",
    "market_demand": "Market Demand",
    "skill_dependency": "Skill Dependency",
    "industry_shift": "Industry Volatility",
}
HEALTH_STATUS = {
    "low": "Perlu Perhatian",
    "medium": "Cukup Sehat",
    "high": "Sehat",
}

CAREER_ANALYSIS_INSTRUCTION = """
Analyze the supplied career profile for an Indonesian career-resilience application.
Classify signals only into the enums in the schema; never assign numeric scores.
Use the user's supplied facts as the source of truth. General labor-market knowledge may
inform qualitative classifications, but do not invent statistics, employers, credentials,
achievements, dates, or skills. Keep explanations concise and in Indonesian.

Activities must reflect the supplied responsibilities. Skills must preserve supplied skill
names. performance_growth assesses documented outcomes and progression; adaptability
assesses breadth, learning, and handling change. market_demand means demand for the current
role (strong is favorable). industry_stability means stability of the industry (strong is
favorable). skill_dependency means concentration risk (strong means high dependency/risk).
When market_baseline is present, its classifications and rationales are reviewed and
authoritative; reproduce those classifications for matching subjects.
Propose up to three realistic adjacent roles. Missing skills must be concrete skill names.
Do not recommend senior/architect roles unless the supplied experience supports them.
"""


def _provider_error(exc: AIProviderError) -> HTTPException:
    code = (
        status.HTTP_503_SERVICE_UNAVAILABLE
        if isinstance(exc, AIProviderUnavailable)
        else status.HTTP_502_BAD_GATEWAY
    )
    return HTTPException(status_code=code, detail=str(exc))


async def _load_context(
    db: AsyncSession,
    user_id: int,
    payload: CareerAssessmentRequest,
) -> tuple[dict[str, object], list[Skill], Decimal, Decimal, int]:
    profile = await db.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Complete onboarding before running career assessments",
        )
    role_name = payload.role_name or profile.current_role_name
    industry_name = payload.industry_name or profile.industry_name
    responsibilities = payload.responsibilities or profile.daily_activities
    if not responsibilities:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Career responsibilities are required for analysis",
        )
    skills = list(
        (
            await db.scalars(
                select(Skill)
                .join(UserSkill, UserSkill.skill_id == Skill.id)
                .where(UserSkill.user_id == user_id)
                .order_by(func.lower(Skill.name))
            )
        ).all()
    )
    if not skills:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Add at least one skill before running career assessments",
        )
    evidence_rows = list(
        (
            await db.scalars(
                select(EvidenceItem)
                .where(EvidenceItem.user_id == user_id)
                .order_by(EvidenceItem.created_at.desc(), EvidenceItem.id.desc())
                .limit(10)
            )
        ).all()
    )
    financial_profile = await db.scalar(
        select(FinancialProfile).where(FinancialProfile.user_id == user_id)
    )
    runway_months = Decimal("0")
    readiness = Decimal("0")
    if financial_profile is not None:
        total_assets, liquid_assets = await _asset_totals(db, user_id)
        runway = _runway_preview(financial_profile, total_assets, liquid_assets)
        runway_months = runway.financial_runway_months
        readiness = score(financial_profile.financial_readiness_score)

    snapshot: dict[str, object] = {
        "role_name": role_name,
        "industry_name": industry_name,
        "work_duration_months": payload.work_duration_months
        if payload.work_duration_months is not None
        else profile.work_duration_months,
        "responsibilities": responsibilities,
        "skills": [skill.name for skill in skills],
        "achievements": payload.achievements,
        "performance_feedback": payload.performance_feedback,
        "career_progression": payload.career_progression,
        "job_description": payload.job_description,
        "tools_and_methods": payload.tools_and_methods,
        "evidence": [
            {
                "type": item.evidence_type.value,
                "title": item.title,
                "description": item.description,
                "impact": item.impact,
                "date": item.evidence_date.isoformat() if item.evidence_date else None,
            }
            for item in evidence_rows
        ],
        "financial": {
            "runway_months": str(runway_months),
            "target_months": str(TARGET_RUNWAY_MONTHS),
        }
        if financial_profile is not None
        else None,
    }
    confidence_parts = [
        bool(role_name and industry_name),
        bool(responsibilities),
        bool(skills),
        bool(evidence_rows or payload.achievements or payload.performance_feedback),
        financial_profile is not None,
    ]
    confidence = score(sum(confidence_parts) * 20)
    return snapshot, skills, readiness, confidence, len(evidence_rows)


async def _apply_market_baseline(
    db: AsyncSession,
    snapshot: dict[str, object],
    skills: list[Skill],
) -> tuple[str | None, dict[tuple[str, str], MarketBaselineSignal]]:
    baseline = await db.scalar(
        select(MarketBaseline)
        .options(selectinload(MarketBaseline.signals))
        .where(MarketBaseline.status == MarketBaselineStatus.approved)
        .order_by(MarketBaseline.approved_at.desc(), MarketBaseline.id.desc())
        .limit(1)
    )
    if baseline is None:
        return None, {}
    wanted = {
        (MarketSubjectType.role.value, str(snapshot["role_name"]).lower()),
        (MarketSubjectType.industry.value, str(snapshot["industry_name"]).lower()),
        *((MarketSubjectType.skill.value, skill.name.lower()) for skill in skills),
    }
    signals = {
        (item.subject_type.value, item.subject_name.lower()): item
        for item in baseline.signals
        if (item.subject_type.value, item.subject_name.lower()) in wanted
    }
    if not signals:
        return None, {}
    snapshot["market_baseline"] = {
        "version": baseline.version,
        "summary": baseline.summary,
        "citations": baseline.citations,
        "signals": [
            {
                "subject_type": item.subject_type.value,
                "subject_name": item.subject_name,
                "signal_type": item.signal_type.value,
                "classification": item.classification,
                "rationale": item.rationale,
            }
            for item in signals.values()
        ],
    }
    return baseline.version, signals


def _pivot_scores(ai_result: CareerAnalysisAIResult) -> list[tuple[object, Decimal]]:
    results: list[tuple[object, Decimal]] = []
    for role in ai_result.pivot_roles:
        match = weighted(
            [
                (SIGNAL_SCORES[role.skill_fit.value], Decimal("0.55")),
                (SIGNAL_SCORES[role.activity_fit.value], Decimal("0.20")),
                (SIGNAL_SCORES[role.experience_fit.value], Decimal("0.15")),
                (SIGNAL_SCORES[role.industry_fit.value], Decimal("0.10")),
            ]
        )
        results.append((role, match))
    return sorted(results, key=lambda item: item[1], reverse=True)


async def _ensure_skills(db: AsyncSession, names: list[str]) -> dict[str, Skill]:
    normalized = list(
        dict.fromkeys(" ".join(name.split()) for name in names if name.strip())
    )
    if not normalized:
        return {}
    await db.execute(
        insert(Skill)
        .values([{"name": name, "market_trend": "stable"} for name in normalized])
        .on_conflict_do_nothing(index_elements=[func.lower(Skill.name)])
    )
    rows = list(
        (
            await db.scalars(
                select(Skill).where(
                    func.lower(Skill.name).in_([name.lower() for name in normalized])
                )
            )
        ).all()
    )
    return {row.name.lower(): row for row in rows}


async def _create_bundle(
    *,
    db: AsyncSession,
    user_id: int,
    skills: list[Skill],
    snapshot: dict[str, object],
    ai_result: CareerAnalysisAIResult,
    provider_model: str,
    financial_score: Decimal,
    data_confidence: Decimal,
    market_baseline_version: str | None,
    market_signals: dict[tuple[str, str], MarketBaselineSignal],
) -> CareerAssessmentBundleResponse:
    activity_scores = [
        EXPOSURE_SCORES[activity.exposure.value] for activity in ai_result.activities
    ]
    exposure_score = average(activity_scores)
    skill_by_name = {skill.name.lower(): skill for skill in skills}
    matched_skill_results = [
        item for item in ai_result.skills if item.name.lower() in skill_by_name
    ]
    skill_classifications = {
        item.name.lower(): (
            market_signals.get((MarketSubjectType.skill.value, item.name.lower()))
        )
        for item in matched_skill_results
    }
    relevance_score = average(
        [
            RELEVANCE_SCORES[
                signal.classification if signal is not None else item.relevance.value
            ]
            for item in matched_skill_results
            for signal in [skill_classifications[item.name.lower()]]
        ]
    )
    pivots = _pivot_scores(ai_result)
    mobility_score = pivots[0][1] if pivots else Decimal("0")

    role_signal = market_signals.get(
        (MarketSubjectType.role.value, str(snapshot["role_name"]).lower())
    )
    industry_signal = market_signals.get(
        (MarketSubjectType.industry.value, str(snapshot["industry_name"]).lower())
    )
    market_demand_level = (
        role_signal.classification
        if role_signal is not None
        else ai_result.market_demand.level.value
    )
    industry_stability_level = (
        industry_signal.classification
        if industry_signal is not None
        else ai_result.industry_stability.level.value
    )
    market_risk = score(100 - SIGNAL_SCORES[market_demand_level])
    dependency_risk = SIGNAL_SCORES[ai_result.skill_dependency.level.value]
    industry_risk = score(100 - SIGNAL_SCORES[industry_stability_level])
    overall_risk = weighted(
        [
            (exposure_score, Decimal("0.40")),
            (market_risk, Decimal("0.25")),
            (dependency_risk, Decimal("0.20")),
            (industry_risk, Decimal("0.15")),
        ]
    )
    performance_score = SIGNAL_SCORES[ai_result.performance_growth.level.value]
    adaptability_score = SIGNAL_SCORES[ai_result.adaptability.level.value]
    health_score = career_health(
        performance_growth=performance_score,
        skill_relevance=relevance_score,
        adaptability=adaptability_score,
        mobility=mobility_score,
        financial_readiness_score=financial_score,
    )
    provenance = {
        "provider": "gemini",
        "model": provider_model,
        "prompt_version": PROMPT_VERSION,
        "scoring_version": SCORE_VERSION,
    }

    exposure = AiExposureAssessment(
        user_id=user_id,
        role_name=str(snapshot["role_name"]),
        responsibilities=str(snapshot["responsibilities"]),
        work_experience=str(snapshot.get("work_duration_months") or "") or None,
        job_description=snapshot.get("job_description"),
        overall_exposure_level=ExposureLevel(exposure_level(exposure_score)),
        overall_exposure_score=exposure_score,
        skill_relevance_score=relevance_score,
        summary=ai_result.exposure_summary,
        data_confidence=data_confidence,
        provider_model=provider_model,
        prompt_version=PROMPT_VERSION,
        scoring_version=SCORE_VERSION,
        market_baseline_version=market_baseline_version,
        input_snapshot={**snapshot, "provenance": provenance},
    )
    db.add(exposure)
    await db.flush()
    exposure_activities: list[ScoreExplanation] = []
    for activity in ai_result.activities:
        activity_score = EXPOSURE_SCORES[activity.exposure.value]
        db.add(
            ExposedActivity(
                assessment_id=exposure.id,
                activity_name=activity.name,
                exposure_level=ExposureLevel(activity.exposure.value),
                exposure_score=activity_score,
                ai_impact_note=activity.note,
            )
        )
        exposure_activities.append(
            ScoreExplanation(
                key=activity.name,
                title=activity.name,
                score=activity_score,
                level=activity.exposure.value,
                explanation=activity.note,
            )
        )
    for skill in skills:
        db.add(AiExposureSkill(assessment_id=exposure.id, skill_id=skill.id))
    for item in matched_skill_results:
        signal = skill_classifications[item.name.lower()]
        db.add(
            SkillRelevance(
                assessment_id=exposure.id,
                skill_id=skill_by_name[item.name.lower()].id,
                status=SkillRelevanceStatus(
                    signal.classification
                    if signal is not None
                    else item.relevance.value
                ),
                recommendation=item.recommendation,
            )
        )

    risk_factor_values = [
        ("ai_advancement", exposure_score, ai_result.exposure_summary),
        (
            "market_demand",
            market_risk,
            role_signal.rationale
            if role_signal is not None
            else ai_result.market_demand.reason,
        ),
        ("skill_dependency", dependency_risk, ai_result.skill_dependency.reason),
        (
            "industry_shift",
            industry_risk,
            industry_signal.rationale
            if industry_signal is not None
            else ai_result.industry_stability.reason,
        ),
    ]
    risk = RiskScan(
        user_id=user_id,
        role_name=str(snapshot["role_name"]),
        industry_name=str(snapshot["industry_name"]),
        responsibilities=str(snapshot["responsibilities"]),
        work_changes=snapshot.get("career_progression"),
        job_description=snapshot.get("job_description"),
        overall_risk_level=RiskLevel(risk_level(overall_risk)),
        overall_score=overall_risk,
        summary=ai_result.risk_summary,
        analysis_description=ai_result.risk_analysis,
        early_warning=ai_result.early_warning,
        data_confidence=data_confidence,
        provider_model=provider_model,
        prompt_version=PROMPT_VERSION,
        scoring_version=SCORE_VERSION,
        market_baseline_version=market_baseline_version,
        input_snapshot={**snapshot, "provenance": provenance},
    )
    db.add(risk)
    await db.flush()
    risk_factors: list[ScoreExplanation] = []
    for source, factor_score, explanation in risk_factor_values:
        level = risk_level(factor_score)
        db.add(
            RiskFactor(
                scan_id=risk.id,
                source=source,
                severity=RiskLevel(level),
                score=factor_score,
                description=explanation,
            )
        )
        risk_factors.append(
            ScoreExplanation(
                key=source,
                title=FACTOR_TITLES[source],
                score=factor_score,
                level=level,
                explanation=explanation,
            )
        )
    for skill in skills:
        db.add(RiskScanSkill(scan_id=risk.id, skill_id=skill.id))

    pivot = PivotAnalysis(
        user_id=user_id,
        current_role_name=str(snapshot["role_name"]),
        industry_name=str(snapshot["industry_name"]),
        work_experience=str(snapshot.get("work_duration_months") or "0 months"),
        responsibilities=str(snapshot["responsibilities"]),
        skills_text=", ".join(skill.name for skill in skills),
        tools_and_methods=snapshot.get("tools_and_methods"),
        job_description=snapshot.get("job_description"),
        achievements=snapshot.get("achievements"),
        target_role_id=None,
        match_score=mobility_score,
        shared_skills_count=len(skills),
        missing_skills_count=len(pivots[0][0].missing_skills) if pivots else 0,
        summary=ai_result.pivot_summary,
        data_confidence=data_confidence,
        provider_model=provider_model,
        prompt_version=PROMPT_VERSION,
        scoring_version=SCORE_VERSION,
        market_baseline_version=market_baseline_version,
        input_snapshot={**snapshot, "provenance": provenance},
    )
    db.add(pivot)
    await db.flush()
    all_missing = [name for role, _ in pivots for name in role.missing_skills]
    missing_skills = await _ensure_skills(db, all_missing)
    pivot_responses: list[PivotRoleResponse] = []
    for role, match in pivots:
        preparation_months = max(1, min(12, ceil(len(role.missing_skills) * 1.5)))
        description = role.reason
        preferred_role = PivotPreferredRole(
            analysis_id=pivot.id,
            role_name=role.role_name,
            match_score=match,
            preparation_time_months=preparation_months,
            preparation_description=description,
        )
        db.add(preferred_role)
        await db.flush()
        pivot_responses.append(
            PivotRoleResponse(
                role_name=role.role_name,
                match_score=match,
                preparation_time_months=preparation_months,
                preparation_description=description,
                missing_skills=role.missing_skills,
            )
        )
        for name in role.missing_skills:
            skill = missing_skills.get(name.lower())
            if skill is None:
                continue
            db.add(
                PivotSkillGap(
                    analysis_id=pivot.id,
                    preferred_role_id=preferred_role.id,
                    skill_id=skill.id,
                    current_level=None,
                    required_level=3,
                    gap_level=GapLevel.medium,
                    recommended_action=f"Pelajari dan praktikkan {skill.name}",
                )
            )

    health_factor_values = [
        ("performance_growth", performance_score, ai_result.performance_growth.reason),
        ("skill_relevance", relevance_score, ai_result.exposure_summary),
        ("adaptability", adaptability_score, ai_result.adaptability.reason),
        ("mobility", mobility_score, ai_result.pivot_summary),
        (
            "financial_readiness",
            financial_score,
            "Kemajuan terhadap target runway enam bulan.",
        ),
    ]
    health = HealthAssessment(
        user_id=user_id,
        role_name=str(snapshot["role_name"]),
        industry_name=str(snapshot["industry_name"]),
        work_duration_months=int(snapshot.get("work_duration_months") or 0),
        responsibilities=str(snapshot["responsibilities"]),
        achievements=snapshot.get("achievements"),
        performance_feedback=snapshot.get("performance_feedback"),
        career_progression=snapshot.get("career_progression"),
        overall_score=health_score,
        level=HealthLevel(health_level(health_score)),
        summary=ai_result.health_summary,
        data_confidence=data_confidence,
        provider_model=provider_model,
        prompt_version=PROMPT_VERSION,
        scoring_version=SCORE_VERSION,
        market_baseline_version=market_baseline_version,
        input_snapshot={**snapshot, "provenance": provenance},
    )
    db.add(health)
    await db.flush()
    health_factors: list[ScoreExplanation] = []
    for dimension, factor_score, explanation in health_factor_values:
        level = health_level(factor_score)
        db.add(
            HealthScoreBreakdown(
                assessment_id=health.id,
                dimension=dimension,
                score=factor_score,
                note=explanation[:255],
            )
        )
        health_factors.append(
            ScoreExplanation(
                key=dimension,
                title=FACTOR_TITLES[dimension],
                score=factor_score,
                level=level,
                explanation=explanation,
            )
        )

    await db.commit()
    for item in (exposure, risk, pivot, health):
        await db.refresh(item)

    def relevance(item) -> str:
        signal = skill_classifications[item.name.lower()]
        return signal.classification if signal is not None else item.relevance.value

    strong_skills = [
        item.name for item in matched_skill_results if relevance(item) == "rising"
    ]
    stable_skills = [
        item.name for item in matched_skill_results if relevance(item) == "stable"
    ]
    improve_skills = [
        item.name for item in matched_skill_results if relevance(item) == "declining"
    ]
    return CareerAssessmentBundleResponse(
        exposure=ExposureAssessmentResult(
            id=exposure.id,
            assessed_at=exposure.assessed_at,
            score=exposure_score,
            level=exposure.overall_exposure_level.value,
            skill_relevance_score=relevance_score,
            summary=ai_result.exposure_summary,
            data_confidence=data_confidence,
            activities=exposure_activities,
            strong_skills=strong_skills or stable_skills,
            rising_skills=strong_skills,
            skills_to_improve=improve_skills,
            model=provider_model,
            scoring_version=SCORE_VERSION,
            market_baseline_version=market_baseline_version,
        ),
        risk=RiskAssessmentResult(
            id=risk.id,
            scanned_at=risk.scanned_at,
            score=overall_risk,
            level=risk.overall_risk_level.value,
            summary=ai_result.risk_summary,
            analysis=ai_result.risk_analysis,
            early_warning=ai_result.early_warning,
            data_confidence=data_confidence,
            factors=risk_factors,
            model=provider_model,
            scoring_version=SCORE_VERSION,
            market_baseline_version=market_baseline_version,
        ),
        pivot=PivotAssessmentResult(
            id=pivot.id,
            analyzed_at=pivot.analyzed_at,
            current_role_name=pivot.current_role_name,
            summary=ai_result.pivot_summary,
            data_confidence=data_confidence,
            roles=pivot_responses,
            model=provider_model,
            scoring_version=SCORE_VERSION,
            market_baseline_version=market_baseline_version,
        ),
        health=HealthAssessmentResult(
            id=health.id,
            assessed_at=health.assessed_at,
            score=health_score,
            level=health.level.value,
            status=HEALTH_STATUS[health.level.value],
            summary=ai_result.health_summary,
            data_confidence=data_confidence,
            factors=health_factors,
            model=provider_model,
            scoring_version=SCORE_VERSION,
            market_baseline_version=market_baseline_version,
        ),
    )


@router.post(
    "/api/ai/assessments",
    response_model=CareerAssessmentBundleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_career_assessments(
    payload: CareerAssessmentRequest,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
    provider: StructuredAIProvider = Depends(get_ai_provider),
) -> CareerAssessmentBundleResponse:
    snapshot, skills, financial_score, confidence, _ = await _load_context(
        db, user.id, payload
    )
    market_baseline_version, market_signals = await _apply_market_baseline(
        db, snapshot, skills
    )
    try:
        ai_result = await provider.generate_structured(
            response_type=CareerAnalysisAIResult,
            system_instruction=CAREER_ANALYSIS_INSTRUCTION,
            input_data=snapshot,
        )
    except AIProviderError as exc:
        raise _provider_error(exc) from None
    expected_skills = {skill.name.lower() for skill in skills}
    generated_skills = {skill.name.lower() for skill in ai_result.skills}
    if generated_skills != expected_skills:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Gemini did not classify every supplied skill exactly once",
        )
    return await _create_bundle(
        db=db,
        user_id=user.id,
        skills=skills,
        snapshot=snapshot,
        ai_result=ai_result,
        provider_model=provider.model,
        financial_score=financial_score,
        data_confidence=confidence,
        market_baseline_version=market_baseline_version,
        market_signals=market_signals,
    )


async def _latest_owned(db: AsyncSession, model, user_id: int, timestamp):
    item = await db.scalar(
        select(model)
        .where(model.user_id == user_id)
        .order_by(timestamp.desc(), model.id.desc())
        .limit(1)
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return item


async def _exposure_response(
    db: AsyncSession, assessment: AiExposureAssessment
) -> ExposureAssessmentResult:
    activities = list(
        (
            await db.scalars(
                select(ExposedActivity)
                .where(ExposedActivity.assessment_id == assessment.id)
                .order_by(ExposedActivity.id)
            )
        ).all()
    )
    relevance_rows = (
        await db.execute(
            select(Skill.name, SkillRelevance.status)
            .join(SkillRelevance, SkillRelevance.skill_id == Skill.id)
            .where(SkillRelevance.assessment_id == assessment.id)
            .order_by(func.lower(Skill.name))
        )
    ).all()
    rising = [
        name for name, item_status in relevance_rows if item_status.value == "rising"
    ]
    stable = [
        name for name, item_status in relevance_rows if item_status.value == "stable"
    ]
    declining = [
        name for name, item_status in relevance_rows if item_status.value == "declining"
    ]
    return ExposureAssessmentResult(
        id=assessment.id,
        assessed_at=assessment.assessed_at,
        score=assessment.overall_exposure_score or Decimal("0"),
        level=assessment.overall_exposure_level.value,
        skill_relevance_score=assessment.skill_relevance_score or Decimal("0"),
        summary=assessment.summary or "",
        data_confidence=assessment.data_confidence or Decimal("0"),
        activities=[
            ScoreExplanation(
                key=item.activity_name,
                title=item.activity_name,
                score=item.exposure_score or EXPOSURE_SCORES[item.exposure_level.value],
                level=item.exposure_level.value,
                explanation=item.ai_impact_note or "",
            )
            for item in activities
        ],
        strong_skills=rising or stable,
        rising_skills=rising,
        skills_to_improve=declining,
        model=assessment.provider_model or "legacy",
        scoring_version=assessment.scoring_version or "legacy",
        market_baseline_version=assessment.market_baseline_version,
    )


async def _risk_response(db: AsyncSession, scan: RiskScan) -> RiskAssessmentResult:
    factors = list(
        (
            await db.scalars(
                select(RiskFactor)
                .where(RiskFactor.scan_id == scan.id)
                .order_by(RiskFactor.id)
            )
        ).all()
    )
    return RiskAssessmentResult(
        id=scan.id,
        scanned_at=scan.scanned_at,
        score=scan.overall_score or Decimal("0"),
        level=scan.overall_risk_level.value,
        summary=scan.summary or "",
        analysis=scan.analysis_description or "",
        early_warning=scan.early_warning or "",
        data_confidence=scan.data_confidence or Decimal("0"),
        factors=[
            ScoreExplanation(
                key=item.source,
                title=FACTOR_TITLES.get(item.source, item.source),
                score=item.score or Decimal("0"),
                level=item.severity.value,
                explanation=item.description,
            )
            for item in factors
        ],
        model=scan.provider_model or "legacy",
        scoring_version=scan.scoring_version or "legacy",
        market_baseline_version=scan.market_baseline_version,
    )


async def _pivot_response(
    db: AsyncSession, analysis: PivotAnalysis
) -> PivotAssessmentResult:
    roles = list(
        (
            await db.scalars(
                select(PivotPreferredRole)
                .where(PivotPreferredRole.analysis_id == analysis.id)
                .order_by(PivotPreferredRole.match_score.desc(), PivotPreferredRole.id)
            )
        ).all()
    )
    missing_rows = (
        await db.execute(
            select(PivotSkillGap.preferred_role_id, Skill.name)
            .join(Skill, PivotSkillGap.skill_id == Skill.id)
            .where(PivotSkillGap.analysis_id == analysis.id)
            .order_by(func.lower(Skill.name))
        )
    ).all()
    missing_by_role: dict[int | None, list[str]] = {}
    for preferred_role_id, name in missing_rows:
        missing_by_role.setdefault(preferred_role_id, []).append(name)
    return PivotAssessmentResult(
        id=analysis.id,
        analyzed_at=analysis.analyzed_at,
        current_role_name=analysis.current_role_name,
        summary=analysis.summary or "",
        data_confidence=analysis.data_confidence or Decimal("0"),
        roles=[
            PivotRoleResponse(
                role_name=item.role_name,
                match_score=item.match_score or Decimal("0"),
                preparation_time_months=item.preparation_time_months or 0,
                preparation_description=item.preparation_description or "",
                missing_skills=(
                    missing_by_role.get(item.id, []) + missing_by_role.get(None, [])
                ),
            )
            for item in roles
        ],
        model=analysis.provider_model or "legacy",
        scoring_version=analysis.scoring_version or "legacy",
        market_baseline_version=analysis.market_baseline_version,
    )


async def _health_response(
    db: AsyncSession, assessment: HealthAssessment
) -> HealthAssessmentResult:
    factors = list(
        (
            await db.scalars(
                select(HealthScoreBreakdown)
                .where(HealthScoreBreakdown.assessment_id == assessment.id)
                .order_by(HealthScoreBreakdown.id)
            )
        ).all()
    )
    factor_scores = {item.dimension: item.score for item in factors}
    financial_profile = await db.scalar(
        select(FinancialProfile).where(FinancialProfile.user_id == assessment.user_id)
    )
    if financial_profile is not None and "financial_readiness" in factor_scores:
        factor_scores["financial_readiness"] = score(
            financial_profile.financial_readiness_score
        )
    required_dimensions = {
        "performance_growth",
        "skill_relevance",
        "adaptability",
        "mobility",
        "financial_readiness",
    }
    current_score = assessment.overall_score
    if required_dimensions.issubset(factor_scores):
        current_score = career_health(
            performance_growth=factor_scores["performance_growth"],
            skill_relevance=factor_scores["skill_relevance"],
            adaptability=factor_scores["adaptability"],
            mobility=factor_scores["mobility"],
            financial_readiness_score=factor_scores["financial_readiness"],
        )
    current_level = health_level(current_score)
    return HealthAssessmentResult(
        id=assessment.id,
        assessed_at=assessment.assessed_at,
        score=current_score,
        level=current_level,
        status=HEALTH_STATUS[current_level],
        summary=assessment.summary or "",
        data_confidence=assessment.data_confidence or Decimal("0"),
        factors=[
            ScoreExplanation(
                key=item.dimension,
                title=FACTOR_TITLES.get(item.dimension, item.dimension),
                score=factor_scores[item.dimension],
                level=health_level(factor_scores[item.dimension]),
                explanation=item.note or "",
            )
            for item in factors
        ],
        model=assessment.provider_model or "legacy",
        scoring_version=assessment.scoring_version or "legacy",
        market_baseline_version=assessment.market_baseline_version,
    )


@router.post(
    "/api/ai-exposure", response_model=ExposureAssessmentResult, status_code=201
)
async def create_ai_exposure(
    payload: CareerAssessmentRequest,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
    provider: StructuredAIProvider = Depends(get_ai_provider),
) -> ExposureAssessmentResult:
    return (await create_career_assessments(payload, user, db, provider)).exposure


@router.get("/api/ai-exposure/latest", response_model=ExposureAssessmentResult)
async def get_latest_ai_exposure(
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> ExposureAssessmentResult:
    item = await _latest_owned(
        db, AiExposureAssessment, user.id, AiExposureAssessment.assessed_at
    )
    return await _exposure_response(db, item)


@router.post("/api/career-risk", response_model=RiskAssessmentResult, status_code=201)
async def create_career_risk(
    payload: CareerAssessmentRequest,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
    provider: StructuredAIProvider = Depends(get_ai_provider),
) -> RiskAssessmentResult:
    return (await create_career_assessments(payload, user, db, provider)).risk


@router.get("/api/career-risk/latest", response_model=RiskAssessmentResult)
async def get_latest_career_risk(
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> RiskAssessmentResult:
    item = await _latest_owned(db, RiskScan, user.id, RiskScan.scanned_at)
    return await _risk_response(db, item)


@router.post("/api/career-pivot", response_model=PivotAssessmentResult, status_code=201)
async def create_career_pivot(
    payload: CareerAssessmentRequest,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
    provider: StructuredAIProvider = Depends(get_ai_provider),
) -> PivotAssessmentResult:
    return (await create_career_assessments(payload, user, db, provider)).pivot


@router.get("/api/career-pivot/latest", response_model=PivotAssessmentResult)
async def get_latest_career_pivot(
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> PivotAssessmentResult:
    item = await _latest_owned(db, PivotAnalysis, user.id, PivotAnalysis.analyzed_at)
    return await _pivot_response(db, item)


@router.post(
    "/api/career-health", response_model=HealthAssessmentResult, status_code=201
)
async def create_career_health(
    payload: CareerAssessmentRequest,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
    provider: StructuredAIProvider = Depends(get_ai_provider),
) -> HealthAssessmentResult:
    return (await create_career_assessments(payload, user, db, provider)).health


@router.get("/api/career-health/latest", response_model=HealthAssessmentResult)
async def get_latest_career_health(
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> HealthAssessmentResult:
    item = await _latest_owned(
        db, HealthAssessment, user.id, HealthAssessment.assessed_at
    )
    return await _health_response(db, item)
