from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_verified_user
from app.core.database import get_db
from app.core.entitlements import (
    BPS_POVERTY_LINE_VERSION,
    DEFAULT_SEARCH_TIME_MONTHS,
    REGULATION_VERSION,
    ExitTerms,
    JKP_CLAIM_WINDOW_MONTHS,
    add_months,
    compute_exit_entitlements,
    contract_duration_months,
    cost_of_living_warning,
    exit_type_consistency_error,
    runway_layers,
    runway_months,
)
from app.core.scoring import financial_readiness
from app.core.transition import (
    savings_horizon,
    select_preparation_role,
    transition_gap,
)
from app.models.employment import (
    EmploymentTerms,
    EmploymentTermsResponse,
    EmploymentTermsUpsert,
    ExitRunwayCalculation,
    ExitRunwayRequest,
    ExitRunwayResponse,
    RunwayLayerResponse,
    TransitionGapResponse,
)
from app.models.financial import (
    FinancialAsset,
    FinancialAssetBreakdown,
    FinancialAssetCreate,
    FinancialAssetResponse,
    FinancialAssetType,
    FinancialAssetUpdate,
    FinancialProfile,
    FinancialProfileCreate,
    FinancialProfileResponse,
    FinancialRunwayPreview,
    FinancialSummaryResponse,
    LiquidityLevel,
    RunwayCalculation,
    RunwayCalculationResponse,
    RunwayScenarioRequest,
    RunwayTrendResponse,
)
from app.models.master import Page
from app.models.pivot import PivotAnalysis, PivotPreferredRole, PivotSkillGap
from app.models.user import User


router = APIRouter(prefix="/api/financial", tags=["financial"])

# Kept only as the visible six-month reference line. It is deliberately never used as the
# denominator for Financial Readiness any more.
REFERENCE_RUNWAY_MONTHS = Decimal("6.00")

TARGET_BASIS_PERSONAL = "pivot_preparation_plus_search"
TARGET_BASIS_REFERENCE = "reference_default_no_pivot_analysis"


async def _lock_user(db: AsyncSession, user_id: int) -> None:
    await db.execute(select(func.pg_advisory_xact_lock(user_id)))


async def _get_profile(db: AsyncSession, user_id: int) -> FinancialProfile:
    profile = await db.scalar(
        select(FinancialProfile).where(FinancialProfile.user_id == user_id)
    )
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Financial profile not found",
        )
    return profile


async def _get_asset(db: AsyncSession, user_id: int, asset_id: int) -> FinancialAsset:
    asset = await db.scalar(
        select(FinancialAsset).where(
            FinancialAsset.id == asset_id,
            FinancialAsset.user_id == user_id,
        )
    )
    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Financial asset not found",
        )
    return asset


async def _asset_totals(db: AsyncSession, user_id: int) -> tuple[Decimal, Decimal]:
    total, liquid = (
        await db.execute(
            select(
                func.coalesce(func.sum(FinancialAsset.amount), 0),
                func.coalesce(
                    func.sum(FinancialAsset.amount).filter(
                        FinancialAsset.liquidity == LiquidityLevel.liquid
                    ),
                    0,
                ),
            ).where(FinancialAsset.user_id == user_id)
        )
    ).one()
    return Decimal(total), Decimal(liquid)


async def _get_employment_terms(
    db: AsyncSession, user_id: int
) -> EmploymentTerms | None:
    return await db.scalar(
        select(EmploymentTerms).where(EmploymentTerms.user_id == user_id)
    )


def _monthly_burn(profile: FinancialProfile) -> Decimal:
    return profile.monthly_essential_expenses + (
        profile.monthly_debt_payment or Decimal("0")
    )


def _plain_runway_months(profile: FinancialProfile, liquid_assets: Decimal) -> Decimal:
    return runway_months(
        liquid_assets=liquid_assets, monthly_burn=_monthly_burn(profile)
    )


async def _pivot_roles(
    db: AsyncSession, user_id: int
) -> list[tuple[int, str, Decimal, int]]:
    """(id, role_name, match_score, preparation_months) for the latest pivot analysis."""
    analysis = await db.scalar(
        select(PivotAnalysis)
        .where(PivotAnalysis.user_id == user_id)
        .order_by(PivotAnalysis.analyzed_at.desc(), PivotAnalysis.id.desc())
        .limit(1)
    )
    if analysis is None:
        return []
    rows = list(
        (
            await db.scalars(
                select(PivotPreferredRole)
                .where(PivotPreferredRole.analysis_id == analysis.id)
                .order_by(PivotPreferredRole.match_score.desc())
            )
        ).all()
    )
    return [
        (
            row.id,
            row.role_name,
            Decimal(row.match_score or 0),
            int(row.preparation_time_months or 0),
        )
        for row in rows
    ]


async def _personal_target_months(
    db: AsyncSession,
    user_id: int,
    search_time_months: Decimal = DEFAULT_SEARCH_TIME_MONTHS,
    preferred_role_name: str | None = None,
) -> tuple[Decimal, str, str | None]:
    """Personal runway target: chosen role's preparation time plus search time.

    Falls back to the six-month reference line only when no pivot analysis exists yet, and
    says so in ``target_basis`` instead of presenting the fallback as a real target.
    """
    roles = await _pivot_roles(db, user_id)
    if not roles:
        return (
            REFERENCE_RUNWAY_MONTHS,
            TARGET_BASIS_REFERENCE,
            None,
        )
    role_name, _, preparation = select_preparation_role(
        [(name, match, prep) for _, name, match, prep in roles],
        preferred_role_name=preferred_role_name,
    )
    target = Decimal(preparation) + search_time_months
    if target <= 0:
        target = REFERENCE_RUNWAY_MONTHS
        basis = TARGET_BASIS_REFERENCE
    else:
        basis = TARGET_BASIS_PERSONAL
    return target, basis, role_name


def _exit_aware_runway_months(
    *,
    profile: FinancialProfile,
    liquid_assets: Decimal,
    terms: EmploymentTerms | None,
) -> tuple[Decimal, Decimal]:
    """Headline runway months and the effective monthly burn behind it.

    With employment terms on file the runway becomes exit-aware, so leaving under
    resignation and being made redundant no longer produce the same number.
    """
    burn = _monthly_burn(profile)
    if terms is None:
        return runway_months(liquid_assets=liquid_assets, monthly_burn=burn), burn
    entitlements = compute_exit_entitlements(
        ExitTerms(
            exit_type=terms.assumed_exit_type,
            monthly_wage_base=terms.monthly_wage_base,
            tenure_months=_effective_tenure(terms),
            contract_months=contract_duration_months(
                terms.contract_start_date, terms.contract_end_date
            ),
            employment_type=terms.employment_type,
            bpjs_tk_active=terms.bpjs_tk_active,
            bpjs_contributions_last_24_months=terms.bpjs_contribution_months_last_24,
            bpjs_consecutive_months=terms.bpjs_consecutive_months,
            age_years=terms.age_years or 0,
            jkn_active=terms.jkn_active,
            jht_balance=terms.jht_balance or Decimal("0"),
        )
    )
    return (
        runway_months(
            liquid_assets=liquid_assets + entitlements.liquid_normative,
            monthly_burn=burn,
            jkp_monthly=entitlements.jkp.monthly_benefit,
            jkp_months=entitlements.jkp.months,
        ),
        burn,
    )


def _effective_tenure(terms: EmploymentTerms) -> int:
    return int(terms.tenure_months or 0)


def _financial_readiness_for(
    profile: FinancialProfile,
    liquid_assets: Decimal,
    target_months: Decimal,
    terms: EmploymentTerms | None,
) -> Decimal:
    """Financial Readiness measured against the personal target.

    The denominator is the user's own preparation-plus-search target, not a flat six
    months, and the numerator is the exit-aware runway.
    """
    runway, _ = _exit_aware_runway_months(
        profile=profile, liquid_assets=liquid_assets, terms=terms
    )
    return financial_readiness(runway, target_months)


async def _sync_financial_state(
    db: AsyncSession, profile: FinancialProfile
) -> tuple[Decimal, Decimal]:
    total, liquid = await _asset_totals(db, profile.user_id)
    terms = await _get_employment_terms(db, profile.user_id)
    target_months, _, _ = await _personal_target_months(db, profile.user_id)
    profile.available_savings = liquid
    profile.other_liquid_funds = Decimal("0")
    profile.financial_readiness_score = _financial_readiness_for(
        profile, liquid, target_months, terms
    )
    profile.financial_readiness_updated_at = datetime.now(UTC)
    return total, liquid


async def _runway_preview(
    profile: FinancialProfile,
    total_assets: Decimal,
    liquid_assets: Decimal,
    target_months: Decimal,
    *,
    target_basis: str = TARGET_BASIS_REFERENCE,
    terms: EmploymentTerms | None = None,
) -> FinancialRunwayPreview:
    runway, burn = _exit_aware_runway_months(
        profile=profile, liquid_assets=liquid_assets, terms=terms
    )
    return FinancialRunwayPreview(
        total_assets=total_assets,
        liquid_assets=liquid_assets,
        monthly_burn=burn,
        financial_runway_months=runway,
        target_runway_months=target_months,
        reference_runway_months=REFERENCE_RUNWAY_MONTHS,
        target_basis=target_basis,
        runway_gap_months=max(target_months - runway, Decimal("0")),
        currency=profile.currency,
        cost_of_living_warning=cost_of_living_warning(
            profile.monthly_essential_expenses, profile.dependents or 0
        ),
        poverty_line_version=BPS_POVERTY_LINE_VERSION,
    )


async def _assets(db: AsyncSession, user_id: int) -> list[FinancialAsset]:
    return list(
        (
            await db.scalars(
                select(FinancialAsset)
                .where(FinancialAsset.user_id == user_id)
                .order_by(FinancialAsset.created_at.asc(), FinancialAsset.id.asc())
            )
        ).all()
    )


@router.get("", response_model=FinancialSummaryResponse)
async def get_financial_summary(
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> FinancialSummaryResponse:
    profile = await _get_profile(db, user.id)
    assets = await _assets(db, user.id)
    total, liquid = await _asset_totals(db, user.id)
    target, basis, _ = await _personal_target_months(db, user.id)
    terms = await _get_employment_terms(db, user.id)
    return FinancialSummaryResponse(
        profile=FinancialProfileResponse.model_validate(profile),
        assets=[FinancialAssetResponse.model_validate(asset) for asset in assets],
        runway=await _runway_preview(
            profile, total, liquid, target, target_basis=basis, terms=terms
        ),
    )


@router.put("", response_model=FinancialProfileResponse)
async def upsert_financial_profile(
    payload: FinancialProfileCreate,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> FinancialProfile:
    await _lock_user(db, user.id)
    profile = await db.scalar(
        select(FinancialProfile).where(FinancialProfile.user_id == user.id)
    )
    if profile is None:
        profile = FinancialProfile(
            user_id=user.id,
            available_savings=Decimal("0"),
            other_liquid_funds=Decimal("0"),
            **payload.model_dump(),
        )
        db.add(profile)
    else:
        if profile.currency != payload.currency:
            asset_count = await db.scalar(
                select(func.count())
                .select_from(FinancialAsset)
                .where(FinancialAsset.user_id == user.id)
            )
            if asset_count:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Delete existing assets before changing currency",
                )
        for field, value in payload.model_dump().items():
            setattr(profile, field, value)

    await db.flush()
    await _sync_financial_state(db, profile)
    await db.commit()
    await db.refresh(profile)
    return profile


@router.get("/assets", response_model=list[FinancialAssetResponse])
async def list_financial_assets(
    asset_type: FinancialAssetType | None = None,
    liquidity: LiquidityLevel | None = None,
    q: str | None = Query(None, max_length=100),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> list[FinancialAsset]:
    await _get_profile(db, user.id)
    filters = [FinancialAsset.user_id == user.id]
    if asset_type is not None:
        filters.append(FinancialAsset.asset_type == asset_type)
    if liquidity is not None:
        filters.append(FinancialAsset.liquidity == liquidity)
    if q and q.strip():
        escaped = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        filters.append(FinancialAsset.name.ilike(f"%{escaped}%", escape="\\"))
    return list(
        (
            await db.scalars(
                select(FinancialAsset)
                .where(*filters)
                .order_by(FinancialAsset.created_at.desc(), FinancialAsset.id.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
    )


@router.post(
    "/assets",
    response_model=FinancialAssetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_financial_asset(
    payload: FinancialAssetCreate,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> FinancialAsset:
    await _lock_user(db, user.id)
    profile = await _get_profile(db, user.id)
    if payload.currency != profile.currency:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Asset currency must match financial profile currency",
        )

    asset = FinancialAsset(user_id=user.id, **payload.model_dump())
    db.add(asset)
    await db.flush()
    await _sync_financial_state(db, profile)
    await db.commit()
    await db.refresh(asset)
    return asset


@router.get("/assets/summary", response_model=FinancialAssetBreakdown)
async def get_financial_asset_breakdown(
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> FinancialAssetBreakdown:
    profile = await _get_profile(db, user.id)
    type_rows = (
        await db.execute(
            select(FinancialAsset.asset_type, func.sum(FinancialAsset.amount))
            .where(FinancialAsset.user_id == user.id)
            .group_by(FinancialAsset.asset_type)
        )
    ).all()
    liquidity_rows = (
        await db.execute(
            select(FinancialAsset.liquidity, func.sum(FinancialAsset.amount))
            .where(FinancialAsset.user_id == user.id)
            .group_by(FinancialAsset.liquidity)
        )
    ).all()
    by_type = {asset_type: Decimal(amount) for asset_type, amount in type_rows}
    by_liquidity = {
        liquidity: Decimal(amount) for liquidity, amount in liquidity_rows
    }
    return FinancialAssetBreakdown(
        total_assets=sum(by_type.values(), Decimal("0")),
        liquid_assets=by_liquidity.get(LiquidityLevel.liquid, Decimal("0")),
        by_type=by_type,
        by_liquidity=by_liquidity,
        asset_count=await db.scalar(
            select(func.count())
            .select_from(FinancialAsset)
            .where(FinancialAsset.user_id == user.id)
        )
        or 0,
        currency=profile.currency,
    )


@router.get("/assets/{asset_id}", response_model=FinancialAssetResponse)
async def get_financial_asset(
    asset_id: int,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> FinancialAsset:
    return await _get_asset(db, user.id, asset_id)


@router.patch("/assets/{asset_id}", response_model=FinancialAssetResponse)
async def update_financial_asset(
    asset_id: int,
    payload: FinancialAssetUpdate,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> FinancialAsset:
    await _lock_user(db, user.id)
    profile = await _get_profile(db, user.id)
    asset = await _get_asset(db, user.id, asset_id)
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("currency", profile.currency) != profile.currency:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Asset currency must match financial profile currency",
        )
    for field, value in changes.items():
        setattr(asset, field, value)

    await db.flush()
    await _sync_financial_state(db, profile)
    await db.commit()
    await db.refresh(asset)
    return asset


@router.delete("/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_financial_asset(
    asset_id: int,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await _lock_user(db, user.id)
    profile = await _get_profile(db, user.id)
    await _get_asset(db, user.id, asset_id)
    await db.execute(
        delete(FinancialAsset).where(
            FinancialAsset.id == asset_id,
            FinancialAsset.user_id == user.id,
        )
    )
    await db.flush()
    await _sync_financial_state(db, profile)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── Employment terms ────────────────────────────────────────────────


@router.get("/employment-terms", response_model=EmploymentTermsResponse)
async def get_employment_terms(
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> EmploymentTerms:
    terms = await _get_employment_terms(db, user.id)
    if terms is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employment terms not found",
        )
    return terms


@router.put("/employment-terms", response_model=EmploymentTermsResponse)
async def upsert_employment_terms(
    payload: EmploymentTermsUpsert,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> EmploymentTerms:
    await _lock_user(db, user.id)
    terms = await _get_employment_terms(db, user.id)
    if terms is None:
        terms = EmploymentTerms(user_id=user.id, **payload.model_dump())
        db.add(terms)
    else:
        for field, value in payload.model_dump().items():
            setattr(terms, field, value)

    await db.flush()
    profile = await db.scalar(
        select(FinancialProfile).where(FinancialProfile.user_id == user.id)
    )
    if profile is not None:
        # Readiness depends on the exit ground, so it has to be recomputed here too.
        await _sync_financial_state(db, profile)
    await db.commit()
    await db.refresh(terms)
    return terms


# ─── Exit-aware runway ───────────────────────────────────────────────


async def _gap_counts(db: AsyncSession, user_id: int) -> dict[int, int]:
    analysis = await db.scalar(
        select(PivotAnalysis)
        .where(PivotAnalysis.user_id == user_id)
        .order_by(PivotAnalysis.analyzed_at.desc(), PivotAnalysis.id.desc())
        .limit(1)
    )
    if analysis is None:
        return {}
    rows = (
        await db.execute(
            select(PivotSkillGap.preferred_role_id, func.count())
            .where(PivotSkillGap.analysis_id == analysis.id)
            .group_by(PivotSkillGap.preferred_role_id)
        )
    ).all()
    return {role_id: count for role_id, count in rows if role_id is not None}


async def _role_transitions(
    db: AsyncSession,
    *,
    user_id: int,
    exit_runway: Decimal,
    monthly_burn: Decimal,
    search_time_months: Decimal,
    horizon_months: Decimal,
) -> list[TransitionGapResponse]:
    """Deterministic Transition Gap for every pivot role the user has."""
    roles = await _pivot_roles(db, user_id)
    if not roles:
        return []
    gap_counts = await _gap_counts(db, user_id)
    results: list[TransitionGapResponse] = []
    for role_id, role_name, match_score, preparation in roles:
        gap_count = gap_counts.get(role_id, 0)
        result = transition_gap(
            role_name=role_name,
            match_score=match_score,
            preparation_time_months=Decimal(preparation or 0),
            exit_runway_months=exit_runway,
            monthly_burn=monthly_burn,
            search_time_months=search_time_months,
            horizon_months=horizon_months,
            gap_count=gap_count,
        )
        results.append(
            TransitionGapResponse(
                role_name=result.role_name,
                match_score=result.match_score,
                preparation_time_months=result.preparation_time_months,
                search_time_months=result.search_time_months,
                transition_months=result.transition_months,
                transition_gap_months=result.transition_gap_months,
                status=result.status,
                recommended_monthly_saving=result.recommended_monthly_saving,
                months_saved_by_closing_one_gap=result.months_saved_by_closing_one_gap,
                note=result.note,
            )
        )
    return results


@router.post(
    "/exit-runway",
    response_model=ExitRunwayResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_exit_runway(
    payload: ExitRunwayRequest,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> ExitRunwayResponse:
    await _lock_user(db, user.id)
    profile = await _get_profile(db, user.id)
    terms = await _get_employment_terms(db, user.id)
    if terms is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "employment_terms_required",
                "message": (
                    "Set employment terms (wage, contract type, BPJS) before computing an "
                    "exit-aware runway, because statutory entitlements depend on them."
                ),
            },
        )

    inconsistency = exit_type_consistency_error(
        payload.exit_type, terms.employment_type
    )
    if inconsistency is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "exit_type_contract_mismatch", "message": inconsistency},
        )

    _, liquid_assets = await _asset_totals(db, user.id)
    burn = _monthly_burn(profile)
    tenure = _effective_tenure(terms)
    entitlements = compute_exit_entitlements(
        ExitTerms(
            exit_type=payload.exit_type,
            monthly_wage_base=terms.monthly_wage_base,
            tenure_months=tenure,
            contract_months=contract_duration_months(
                terms.contract_start_date, terms.contract_end_date
            ),
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
    layers = runway_layers(
        liquid_assets=liquid_assets,
        monthly_burn=burn,
        entitlements=entitlements,
    )
    headline = next(layer for layer in layers if layer.key == "with_jkp")

    today = datetime.now(UTC).date()
    day_of_layoff = payload.day_of_layoff or today
    money_runs_out_on = add_months(day_of_layoff, headline.runway_months)
    jkp_claim_deadline = (
        add_months(day_of_layoff, Decimal(JKP_CLAIM_WINDOW_MONTHS))
        if entitlements.jkp.eligible
        else None
    )
    warning = cost_of_living_warning(
        profile.monthly_essential_expenses, profile.dependents or 0
    )
    # If the layoff date is unknown (or already past) horizon_months_until returns zero,
    # which transition_gap treats as "unset" and would fall back to the runway. Use the
    # request's explicit horizon instead, so the saving target stays a monthly figure.
    horizon = savings_horizon(day_of_layoff, today, payload.horizon_months)
    transitions = await _role_transitions(
        db,
        user_id=user.id,
        exit_runway=headline.runway_months,
        monthly_burn=burn,
        search_time_months=payload.search_time_months,
        horizon_months=horizon,
    )

    calculation = ExitRunwayCalculation(
        user_id=user.id,
        exit_type=payload.exit_type,
        employment_type=terms.employment_type,
        regulation_version=REGULATION_VERSION,
        monthly_wage_base_snapshot=terms.monthly_wage_base,
        tenure_months_snapshot=tenure,
        essential_expenses_snapshot=profile.monthly_essential_expenses,
        debt_payment_snapshot=profile.monthly_debt_payment,
        liquid_assets_snapshot=liquid_assets,
        jht_balance_snapshot=terms.jht_balance,
        currency_snapshot=profile.currency,
        pesangon_months=entitlements.pesangon_months,
        upmk_months=entitlements.upmk_months,
        gross_lump_sum=entitlements.gross_lump_sum,
        severance_tax=entitlements.severance_tax,
        net_lump_sum=entitlements.net_lump_sum,
        normative_collectable=entitlements.normative_collectable,
        liquid_normative=entitlements.liquid_normative,
        jkp_eligible=entitlements.jkp.eligible,
        jkp_monthly_benefit=entitlements.jkp.monthly_benefit,
        jkp_months=entitlements.jkp.months,
        jkp_ineligible_reasons=list(entitlements.jkp.reasons),
        savings_only_runway_months=layers[0].runway_months,
        with_normative_rights_runway_months=layers[1].runway_months,
        with_jkp_runway_months=layers[2].runway_months,
        with_jht_runway_months=layers[3].runway_months,
        day_of_layoff=day_of_layoff,
        money_runs_out_on=money_runs_out_on,
        jkp_claim_deadline=jkp_claim_deadline,
        cost_of_living_warning=warning,
        notes=list(entitlements.notes),
    )
    db.add(calculation)
    await db.commit()
    await db.refresh(calculation)

    return ExitRunwayResponse(
        exit_type=payload.exit_type,
        regulation_version=REGULATION_VERSION,
        employment_type=terms.employment_type,
        currency=profile.currency,
        monthly_wage_base=terms.monthly_wage_base,
        tenure_months=tenure,
        monthly_burn=burn,
        pesangon_months=entitlements.pesangon_months,
        upmk_months=entitlements.upmk_months,
        gross_lump_sum=entitlements.gross_lump_sum,
        severance_tax=entitlements.severance_tax,
        net_lump_sum=entitlements.net_lump_sum,
        normative_collectable=entitlements.normative_collectable,
        liquid_normative=entitlements.liquid_normative,
        jkp_eligible=entitlements.jkp.eligible,
        jkp_monthly_benefit=entitlements.jkp.monthly_benefit,
        jkp_months=entitlements.jkp.months,
        jkp_total_benefit=entitlements.jkp.total_benefit,
        jkp_ineligible_reasons=list(entitlements.jkp.reasons),
        runway_months=headline.runway_months,
        layers=[
            RunwayLayerResponse(
                key=layer.key,
                label=layer.label,
                runway_months=layer.runway_months,
                liquid_funds=layer.liquid_funds,
                monthly_benefit=layer.monthly_benefit,
                uses_retirement_savings=layer.key == "with_jht",
            )
            for layer in layers
        ],
        day_of_layoff=day_of_layoff,
        money_runs_out_on=money_runs_out_on,
        jkp_claim_deadline=jkp_claim_deadline,
        cost_of_living_warning=warning,
        poverty_line_version=BPS_POVERTY_LINE_VERSION,
        notes=list(entitlements.notes),
        role_transitions=transitions,
        calculated_at=calculation.calculated_at,
    )


@router.get("/exit-runway/latest", response_model=ExitRunwayResponse)
async def get_latest_exit_runway(
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> ExitRunwayResponse:
    calculation = await db.scalar(
        select(ExitRunwayCalculation)
        .where(ExitRunwayCalculation.user_id == user.id)
        .order_by(
            ExitRunwayCalculation.calculated_at.desc(),
            ExitRunwayCalculation.id.desc(),
        )
        .limit(1)
    )
    if calculation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No saved exit-runway calculation found",
        )
    profile = await _get_profile(db, user.id)
    burn = _monthly_burn(profile)
    transitions = await _role_transitions(
        db,
        user_id=user.id,
        exit_runway=calculation.with_jkp_runway_months,
        monthly_burn=burn,
        search_time_months=DEFAULT_SEARCH_TIME_MONTHS,
        day_of_layoff=calculation.day_of_layoff,
        today=datetime.now(UTC).date(),
    )
    return _exit_runway_response_from_row(calculation, burn, transitions)


def _exit_runway_response_from_row(
    calculation: ExitRunwayCalculation,
    monthly_burn: Decimal,
    transitions: list[TransitionGapResponse],
) -> ExitRunwayResponse:
    jkp_total = calculation.jkp_monthly_benefit * calculation.jkp_months
    return ExitRunwayResponse(
        exit_type=calculation.exit_type,
        regulation_version=calculation.regulation_version,
        employment_type=calculation.employment_type,
        currency=calculation.currency_snapshot,
        monthly_wage_base=calculation.monthly_wage_base_snapshot,
        tenure_months=calculation.tenure_months_snapshot,
        monthly_burn=monthly_burn,
        pesangon_months=calculation.pesangon_months,
        upmk_months=calculation.upmk_months,
        gross_lump_sum=calculation.gross_lump_sum,
        severance_tax=calculation.severance_tax,
        net_lump_sum=calculation.net_lump_sum,
        normative_collectable=calculation.normative_collectable,
        liquid_normative=calculation.liquid_normative,
        jkp_eligible=calculation.jkp_eligible,
        jkp_monthly_benefit=calculation.jkp_monthly_benefit,
        jkp_months=calculation.jkp_months,
        jkp_total_benefit=jkp_total,
        jkp_ineligible_reasons=list(calculation.jkp_ineligible_reasons or []),
        runway_months=calculation.with_jkp_runway_months,
        layers=[
            RunwayLayerResponse(
                key="savings_only",
                label="Tabungan saja",
                runway_months=calculation.savings_only_runway_months,
                liquid_funds=calculation.liquid_assets_snapshot,
                monthly_benefit=Decimal("0"),
            ),
            RunwayLayerResponse(
                key="with_normative_rights",
                label="+ hak normatif",
                runway_months=calculation.with_normative_rights_runway_months,
                liquid_funds=calculation.liquid_assets_snapshot
                + calculation.liquid_normative,
                monthly_benefit=Decimal("0"),
            ),
            RunwayLayerResponse(
                key="with_jkp",
                label="+ JKP",
                runway_months=calculation.with_jkp_runway_months,
                liquid_funds=calculation.liquid_assets_snapshot
                + calculation.liquid_normative,
                monthly_benefit=calculation.jkp_monthly_benefit,
            ),
            RunwayLayerResponse(
                key="with_jht",
                label="+ JHT (menggunakan dana pensiun)",
                runway_months=calculation.with_jht_runway_months,
                liquid_funds=calculation.liquid_assets_snapshot
                + calculation.liquid_normative
                + (calculation.jht_balance_snapshot or Decimal("0")),
                monthly_benefit=calculation.jkp_monthly_benefit,
                uses_retirement_savings=True,
            ),
        ],
        day_of_layoff=calculation.day_of_layoff,
        money_runs_out_on=calculation.money_runs_out_on,
        jkp_claim_deadline=calculation.jkp_claim_deadline,
        cost_of_living_warning=calculation.cost_of_living_warning,
        poverty_line_version=BPS_POVERTY_LINE_VERSION,
        notes=list(calculation.notes or []),
        role_transitions=transitions,
        calculated_at=calculation.calculated_at,
    )


# ─── Runway history ──────────────────────────────────────────────────


@router.get("/runway", response_model=FinancialRunwayPreview)
async def preview_runway(
    search_time_months: Decimal = Query(
        DEFAULT_SEARCH_TIME_MONTHS, ge=0, le=24
    ),
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> FinancialRunwayPreview:
    profile = await _get_profile(db, user.id)
    total, liquid = await _asset_totals(db, user.id)
    target, basis, _ = await _personal_target_months(
        db, user.id, search_time_months=search_time_months
    )
    terms = await _get_employment_terms(db, user.id)
    return await _runway_preview(
        profile, total, liquid, target, target_basis=basis, terms=terms
    )


@router.post(
    "/runway",
    response_model=RunwayCalculationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def save_runway_calculation(
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> RunwayCalculation:
    await _lock_user(db, user.id)
    profile = await _get_profile(db, user.id)
    total, liquid = await _sync_financial_state(db, profile)
    terms = await _get_employment_terms(db, user.id)
    target, basis, _ = await _personal_target_months(db, user.id)
    preview = await _runway_preview(
        profile, total, liquid, target, target_basis=basis, terms=terms
    )
    calculation = RunwayCalculation(
        user_id=user.id,
        available_savings_snapshot=liquid,
        essential_expenses_snapshot=profile.monthly_essential_expenses,
        debt_payment_snapshot=profile.monthly_debt_payment,
        dependents_snapshot=profile.dependents,
        liquid_funds_snapshot=Decimal("0"),
        financial_runway_months=preview.financial_runway_months,
        total_assets_snapshot=total,
        currency_snapshot=profile.currency,
    )
    db.add(calculation)
    await db.commit()
    await db.refresh(calculation)
    return calculation


@router.post("/runway/preview", response_model=FinancialRunwayPreview)
async def preview_runway_scenario(
    payload: RunwayScenarioRequest,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> FinancialRunwayPreview:
    profile = await _get_profile(db, user.id)
    total, current_liquid = await _asset_totals(db, user.id)
    liquid = payload.liquid_assets if payload.liquid_assets is not None else current_liquid
    scenario_total = total - current_liquid + liquid
    target, basis, _ = await _personal_target_months(db, user.id)
    terms = await _get_employment_terms(db, user.id)

    scenario_profile = FinancialProfile(
        user_id=profile.user_id,
        available_savings=liquid,
        monthly_essential_expenses=payload.monthly_essential_expenses,
        monthly_debt_payment=payload.monthly_debt_payment,
        dependents=profile.dependents,
        other_liquid_funds=Decimal("0"),
        currency=profile.currency,
    )
    return await _runway_preview(
        scenario_profile,
        scenario_total,
        liquid,
        target,
        target_basis=basis,
        terms=terms,
    )


@router.get("/runway/latest", response_model=RunwayCalculationResponse)
async def get_latest_runway_calculation(
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> RunwayCalculation:
    calculation = await db.scalar(
        select(RunwayCalculation)
        .where(RunwayCalculation.user_id == user.id)
        .order_by(
            RunwayCalculation.calculated_at.desc(), RunwayCalculation.id.desc()
        )
        .limit(1)
    )
    if calculation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No saved runway calculation found",
        )
    return calculation


@router.get("/runway/history", response_model=Page[RunwayCalculationResponse])
async def list_runway_history(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> Page[RunwayCalculationResponse]:
    where = RunwayCalculation.user_id == user.id
    total = await db.scalar(
        select(func.count()).select_from(RunwayCalculation).where(where)
    )
    calculations = list(
        (
            await db.scalars(
                select(RunwayCalculation)
                .where(where)
                .order_by(
                    RunwayCalculation.calculated_at.desc(),
                    RunwayCalculation.id.desc(),
                )
                .offset(offset)
                .limit(limit)
            )
        ).all()
    )
    return Page[RunwayCalculationResponse](
        items=[
            RunwayCalculationResponse.model_validate(calculation)
            for calculation in calculations
        ],
        total=total or 0,
        limit=limit,
        offset=offset,
    )


@router.get("/runway/trend", response_model=RunwayTrendResponse)
async def get_runway_trend(
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> RunwayTrendResponse:
    calculations = list(
        (
            await db.scalars(
                select(RunwayCalculation)
                .where(RunwayCalculation.user_id == user.id)
                .order_by(
                    RunwayCalculation.calculated_at.desc(),
                    RunwayCalculation.id.desc(),
                )
                .limit(2)
            )
        ).all()
    )
    latest = calculations[0] if calculations else None
    previous = calculations[1] if len(calculations) > 1 else None
    return RunwayTrendResponse(
        latest=(RunwayCalculationResponse.model_validate(latest) if latest else None),
        previous=(
            RunwayCalculationResponse.model_validate(previous) if previous else None
        ),
        delta_months=(
            latest.financial_runway_months - previous.financial_runway_months
            if latest and previous
            else None
        ),
    )
