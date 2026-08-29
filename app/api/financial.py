from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_verified_user
from app.core.database import get_db
from app.models.financial import (
    FinancialAsset,
    FinancialAssetCreate,
    FinancialAssetResponse,
    FinancialAssetUpdate,
    FinancialProfile,
    FinancialProfileCreate,
    FinancialProfileResponse,
    FinancialRunwayPreview,
    FinancialSummaryResponse,
    LiquidityLevel,
    RunwayCalculation,
    RunwayCalculationResponse,
)
from app.models.master import Page
from app.models.user import User


router = APIRouter(prefix="/api/financial", tags=["financial"])
TARGET_RUNWAY_MONTHS = Decimal("6.00")


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


async def _sync_liquid_assets(
    db: AsyncSession, profile: FinancialProfile
) -> tuple[Decimal, Decimal]:
    total, liquid = await _asset_totals(db, profile.user_id)
    profile.available_savings = liquid
    profile.other_liquid_funds = Decimal("0")
    return total, liquid


def _runway_preview(
    profile: FinancialProfile, total_assets: Decimal, liquid_assets: Decimal
) -> FinancialRunwayPreview:
    monthly_burn = profile.monthly_essential_expenses + (
        profile.monthly_debt_payment or Decimal("0")
    )
    runway = (liquid_assets / monthly_burn).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return FinancialRunwayPreview(
        total_assets=total_assets,
        liquid_assets=liquid_assets,
        monthly_burn=monthly_burn,
        financial_runway_months=runway,
        target_runway_months=TARGET_RUNWAY_MONTHS,
        runway_gap_months=max(TARGET_RUNWAY_MONTHS - runway, Decimal("0")),
        currency=profile.currency,
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
    return FinancialSummaryResponse(
        profile=FinancialProfileResponse.model_validate(profile),
        assets=[FinancialAssetResponse.model_validate(asset) for asset in assets],
        runway=_runway_preview(profile, total, liquid),
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
    await _sync_liquid_assets(db, profile)
    await db.commit()
    await db.refresh(profile)
    return profile


@router.get("/assets", response_model=list[FinancialAssetResponse])
async def list_financial_assets(
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> list[FinancialAsset]:
    await _get_profile(db, user.id)
    return await _assets(db, user.id)


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
    await _sync_liquid_assets(db, profile)
    await db.commit()
    await db.refresh(asset)
    return asset


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
    await _sync_liquid_assets(db, profile)
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
    await _sync_liquid_assets(db, profile)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/runway", response_model=FinancialRunwayPreview)
async def preview_runway(
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> FinancialRunwayPreview:
    profile = await _get_profile(db, user.id)
    total, liquid = await _asset_totals(db, user.id)
    return _runway_preview(profile, total, liquid)


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
    total, liquid = await _sync_liquid_assets(db, profile)
    preview = _runway_preview(profile, total, liquid)
    calculation = RunwayCalculation(
        user_id=user.id,
        available_savings_snapshot=liquid,
        essential_expenses_snapshot=profile.monthly_essential_expenses,
        debt_payment_snapshot=profile.monthly_debt_payment,
        dependents_snapshot=profile.dependents,
        liquid_funds_snapshot=Decimal("0"),
        financial_runway_months=preview.financial_runway_months,
    )
    db.add(calculation)
    await db.commit()
    await db.refresh(calculation)
    return calculation


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
