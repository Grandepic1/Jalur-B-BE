from datetime import UTC, date, datetime
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import case, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_verified_user
from app.core.database import get_db
from app.models.master import Page, Skill
from app.models.missions import (
    MissionProgressResponse,
    MissionStatus,
    SkillMission,
    SkillMissionCreate,
    SkillMissionResponse,
    SkillMissionUpdate,
)
from app.models.pivot import PivotAnalysis, PivotSkillGap
from app.models.user import User


router = APIRouter(prefix="/api/missions", tags=["missions"])


async def _get_mission(
    db: AsyncSession, user_id: int, mission_id: int
) -> SkillMission:
    mission = await db.scalar(
        select(SkillMission).where(
            SkillMission.id == mission_id,
            SkillMission.user_id == user_id,
        )
    )
    if mission is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mission not found",
        )
    return mission


async def _validate_links(
    db: AsyncSession,
    user_id: int,
    skill_id: int | None,
    pivot_skill_gap_id: int | None,
) -> tuple[int | None, int | None]:
    if skill_id is not None and await db.get(Skill, skill_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found")
    if pivot_skill_gap_id is None:
        return skill_id, None

    gap = await db.scalar(
        select(PivotSkillGap)
        .join(PivotAnalysis, PivotAnalysis.id == PivotSkillGap.analysis_id)
        .where(
            PivotSkillGap.id == pivot_skill_gap_id,
            PivotAnalysis.user_id == user_id,
        )
    )
    if gap is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pivot skill gap not found",
        )
    if skill_id is not None and skill_id != gap.skill_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Mission skill does not match pivot skill gap",
        )
    return gap.skill_id, gap.id


@router.get("", response_model=Page[SkillMissionResponse])
async def list_missions(
    mission_status: MissionStatus | None = Query(None, alias="status"),
    skill_id: int | None = Query(None, ge=1),
    due_before: date | None = None,
    due_after: date | None = None,
    overdue: bool | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> Page[SkillMissionResponse]:
    if due_after and due_before and due_after > due_before:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="due_after cannot be after due_before",
        )
    filters = [SkillMission.user_id == user.id]
    if mission_status is not None:
        filters.append(SkillMission.status == mission_status)
    if skill_id is not None:
        filters.append(SkillMission.skill_id == skill_id)
    if due_before is not None:
        filters.append(SkillMission.due_date <= due_before)
    if due_after is not None:
        filters.append(SkillMission.due_date >= due_after)
    if overdue is not None:
        overdue_filter = (
            (SkillMission.due_date < datetime.now(UTC).date())
            & (SkillMission.status != MissionStatus.completed)
        )
        filters.append(
            overdue_filter
            if overdue
            else or_(
                SkillMission.due_date.is_(None),
                SkillMission.due_date >= datetime.now(UTC).date(),
                SkillMission.status == MissionStatus.completed,
            )
        )

    total = await db.scalar(
        select(func.count()).select_from(SkillMission).where(*filters)
    )
    items = list(
        (
            await db.scalars(
                select(SkillMission)
                .where(*filters)
                .order_by(
                    case((SkillMission.status == MissionStatus.completed, 1), else_=0),
                    SkillMission.due_date.asc().nulls_last(),
                    SkillMission.created_at.desc(),
                    SkillMission.id.desc(),
                )
                .limit(limit)
                .offset(offset)
            )
        ).all()
    )
    return Page[SkillMissionResponse](
        items=[SkillMissionResponse.model_validate(item) for item in items],
        total=total or 0,
        limit=limit,
        offset=offset,
    )


@router.get("/progress", response_model=MissionProgressResponse)
async def get_mission_progress(
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> MissionProgressResponse:
    rows = (
        await db.execute(
            select(SkillMission.status, func.count())
            .where(SkillMission.user_id == user.id)
            .group_by(SkillMission.status)
        )
    ).all()
    counts = {mission_status: count for mission_status, count in rows}
    total = sum(counts.values())
    completed = counts.get(MissionStatus.completed, 0)
    overdue = await db.scalar(
        select(func.count())
        .select_from(SkillMission)
        .where(
            SkillMission.user_id == user.id,
            SkillMission.due_date < datetime.now(UTC).date(),
            SkillMission.status != MissionStatus.completed,
        )
    )
    percentage = (
        (Decimal(completed) * Decimal("100") / Decimal(total)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if total
        else Decimal("0")
    )
    return MissionProgressResponse(
        total=total,
        todo=counts.get(MissionStatus.todo, 0),
        in_progress=counts.get(MissionStatus.in_progress, 0),
        completed=completed,
        overdue=overdue or 0,
        completion_percentage=percentage,
    )


@router.post("", response_model=SkillMissionResponse, status_code=status.HTTP_201_CREATED)
async def create_mission(
    payload: SkillMissionCreate,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> SkillMission:
    values = payload.model_dump()
    skill_id, gap_id = await _validate_links(
        db, user.id, values["skill_id"], values["pivot_skill_gap_id"]
    )
    values["skill_id"] = skill_id
    values["pivot_skill_gap_id"] = gap_id
    mission = SkillMission(user_id=user.id, **values)
    db.add(mission)
    await db.commit()
    await db.refresh(mission)
    return mission


@router.get("/{mission_id}", response_model=SkillMissionResponse)
async def get_mission(
    mission_id: int,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> SkillMission:
    return await _get_mission(db, user.id, mission_id)


@router.patch("/{mission_id}", response_model=SkillMissionResponse)
async def update_mission(
    mission_id: int,
    payload: SkillMissionUpdate,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> SkillMission:
    mission = await _get_mission(db, user.id, mission_id)
    changes = payload.model_dump(exclude_unset=True)
    resulting_skill_id = changes.get("skill_id", mission.skill_id)
    resulting_gap_id = changes.get("pivot_skill_gap_id", mission.pivot_skill_gap_id)
    skill_id, gap_id = await _validate_links(
        db, user.id, resulting_skill_id, resulting_gap_id
    )
    changes["skill_id"] = skill_id
    changes["pivot_skill_gap_id"] = gap_id
    for field, value in changes.items():
        setattr(mission, field, value)
    await db.commit()
    await db.refresh(mission)
    return mission


@router.delete("/{mission_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mission(
    mission_id: int,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await _get_mission(db, user.id, mission_id)
    await db.execute(
        delete(SkillMission).where(
            SkillMission.id == mission_id,
            SkillMission.user_id == user.id,
        )
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
