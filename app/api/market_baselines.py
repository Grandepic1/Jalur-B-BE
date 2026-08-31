import secrets
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.auth import get_verified_user
from app.core.ai import (
    AIProviderError,
    AIProviderUnavailable,
    StructuredAIProvider,
    get_ai_provider,
)
from app.core.config import settings
from app.core.database import get_db
from app.models.market_baseline import (
    MarketBaseline,
    MarketBaselineAIResult,
    MarketBaselineRefreshRequest,
    MarketBaselineResponse,
    MarketBaselineSignal,
    MarketBaselineStatus,
)
from app.models.user import User


router = APIRouter(prefix="/api/market-baselines", tags=["market baselines"])
MARKET_BASELINE_PROMPT_VERSION = "market-baseline-v1"

MARKET_BASELINE_INSTRUCTION = """
Research current Indonesian labor-market conditions. Prefer official
government, primary research, and established labor-market sources. Classify every supplied
subject exactly once and preserve each subject name and type verbatim. For roles classify
market_demand as weak, moderate, or strong. For industries classify industry_stability as
weak, moderate, or strong. For skills classify skill_relevance as declining, stable, or
rising. Base every rationale only on the retrieved sources, avoid unsupported statistics,
and keep the summary and rationales concise in Indonesian. Numeric scores are forbidden.
"""


def require_market_baseline_admin(
    key: str = Header("", alias="X-Market-Baseline-Key"),
) -> None:
    configured = settings.market_baseline_admin_key
    if not configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Market baseline administration is not configured",
        )
    if not secrets.compare_digest(key, configured):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid market baseline administration key",
        )


async def _baseline_response(
    db: AsyncSession, baseline: MarketBaseline
) -> MarketBaselineResponse:
    item = await db.scalar(
        select(MarketBaseline)
        .options(selectinload(MarketBaseline.signals))
        .where(MarketBaseline.id == baseline.id)
    )
    return MarketBaselineResponse.model_validate(item)


@router.post(
    "/refresh",
    response_model=MarketBaselineResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_market_baseline_admin)],
)
async def refresh_market_baseline(
    payload: MarketBaselineRefreshRequest,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
    provider: StructuredAIProvider = Depends(get_ai_provider),
) -> MarketBaselineResponse:
    subjects = [item.model_dump(mode="json") for item in payload.subjects]
    try:
        grounded = await provider.generate_grounded_structured(
            response_type=MarketBaselineAIResult,
            system_instruction=MARKET_BASELINE_INSTRUCTION,
            input_data={"country": "Indonesia", "subjects": subjects},
        )
    except AIProviderError as exc:
        code = 503 if isinstance(exc, AIProviderUnavailable) else 502
        raise HTTPException(status_code=code, detail=str(exc)) from None

    requested = {
        (item.subject_type.value, item.name.lower()): item.name
        for item in payload.subjects
    }
    generated = {
        (item.subject_type.value, item.subject_name.lower()): item
        for item in grounded.value.signals
    }
    if set(generated) != set(requested):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI provider did not classify every requested market subject exactly once",
        )

    now = datetime.now(UTC)
    baseline = MarketBaseline(
        version=f"market-{now:%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}",
        status=MarketBaselineStatus.draft,
        summary=grounded.value.summary,
        provider_model=provider.model,
        prompt_version=MARKET_BASELINE_PROMPT_VERSION,
        search_queries=grounded.search_queries,
        citations=grounded.citations,
        grounding_metadata=grounded.metadata,
        created_by=user.id,
    )
    db.add(baseline)
    await db.flush()
    for key, item in generated.items():
        db.add(
            MarketBaselineSignal(
                baseline_id=baseline.id,
                subject_type=item.subject_type,
                subject_name=requested[key],
                signal_type=item.signal_type,
                classification=item.classification,
                rationale=item.rationale,
            )
        )
    await db.commit()
    return await _baseline_response(db, baseline)


@router.get(
    "",
    response_model=list[MarketBaselineResponse],
    dependencies=[Depends(require_market_baseline_admin)],
)
async def list_market_baselines(
    baseline_status: MarketBaselineStatus | None = Query(None, alias="status"),
    limit: int = Query(20, ge=1, le=100),
    _: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> list[MarketBaselineResponse]:
    statement = select(MarketBaseline).options(selectinload(MarketBaseline.signals))
    if baseline_status is not None:
        statement = statement.where(MarketBaseline.status == baseline_status)
    items = list(
        (
            await db.scalars(
                statement.order_by(MarketBaseline.generated_at.desc()).limit(limit)
            )
        ).all()
    )
    return [MarketBaselineResponse.model_validate(item) for item in items]


@router.get("/current", response_model=MarketBaselineResponse)
async def get_current_market_baseline(
    _: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> MarketBaselineResponse:
    item = await db.scalar(
        select(MarketBaseline)
        .options(selectinload(MarketBaseline.signals))
        .where(MarketBaseline.status == MarketBaselineStatus.approved)
        .order_by(MarketBaseline.approved_at.desc(), MarketBaseline.id.desc())
        .limit(1)
    )
    if item is None:
        raise HTTPException(
            status_code=404, detail="Approved market baseline not found"
        )
    return MarketBaselineResponse.model_validate(item)


@router.post(
    "/{baseline_id}/approve",
    response_model=MarketBaselineResponse,
    dependencies=[Depends(require_market_baseline_admin)],
)
async def approve_market_baseline(
    baseline_id: int,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> MarketBaselineResponse:
    await db.execute(select(MarketBaseline.id).with_for_update())
    baseline = await db.get(MarketBaseline, baseline_id)
    if baseline is None:
        raise HTTPException(status_code=404, detail="Market baseline not found")
    if baseline.status != MarketBaselineStatus.draft:
        raise HTTPException(
            status_code=409, detail="Only draft baselines can be approved"
        )
    await db.execute(
        update(MarketBaseline)
        .where(MarketBaseline.status == MarketBaselineStatus.approved)
        .values(status=MarketBaselineStatus.archived)
    )
    baseline.status = MarketBaselineStatus.approved
    baseline.approved_by = user.id
    baseline.approved_at = datetime.now(UTC)
    await db.commit()
    return await _baseline_response(db, baseline)


@router.post(
    "/{baseline_id}/reject",
    response_model=MarketBaselineResponse,
    dependencies=[Depends(require_market_baseline_admin)],
)
async def reject_market_baseline(
    baseline_id: int,
    _: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> MarketBaselineResponse:
    baseline = await db.get(MarketBaseline, baseline_id)
    if baseline is None:
        raise HTTPException(status_code=404, detail="Market baseline not found")
    if baseline.status != MarketBaselineStatus.draft:
        raise HTTPException(
            status_code=409, detail="Only draft baselines can be rejected"
        )
    baseline.status = MarketBaselineStatus.rejected
    await db.commit()
    return await _baseline_response(db, baseline)
