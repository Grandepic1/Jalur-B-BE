from typing import TypeVar

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.core.database import get_db
from app.api.auth import get_verified_user
from app.models.master import (
    Industry,
    IndustryRead,
    Page,
    Role,
    RoleRead,
    Skill,
    SkillRead,
    Tool,
    ToolRead,
)


router = APIRouter(
    prefix="/api/master",
    tags=["master data"],
    dependencies=[Depends(get_verified_user)],
)
SchemaT = TypeVar("SchemaT", bound=BaseModel)


async def _paginate(
    db: AsyncSession,
    query: Select,
    count_query: Select,
    schema: type[SchemaT],
    limit: int,
    offset: int,
) -> Page[SchemaT]:
    total_column = count_query.correlate(None).scalar_subquery().label("_total")
    rows = (await db.execute(query.add_columns(total_column).limit(limit).offset(offset))).all()
    records = [row[0] for row in rows]
    total = int(rows[0][1]) if rows else int(await db.scalar(count_query) or 0)
    return Page[SchemaT](
        items=[schema.model_validate(record) for record in records],
        total=total,
        limit=limit,
        offset=offset,
    )


def _contains(column, value: str):
    escaped = value.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return column.ilike(f"%{escaped}%", escape="\\")


@router.get("/industries", response_model=Page[IndustryRead])
async def list_industries(
    q: str | None = Query(None, max_length=100),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> Page[IndustryRead]:
    filters = [_contains(Industry.name, q)] if q and q.strip() else []
    return await _paginate(
        db,
        select(Industry).where(*filters).order_by(func.lower(Industry.name), Industry.id),
        select(func.count()).select_from(Industry).where(*filters),
        IndustryRead,
        limit,
        offset,
    )


@router.get("/roles", response_model=Page[RoleRead])
async def list_roles(
    q: str | None = Query(None, max_length=100),
    industry_id: int | None = Query(None, ge=1),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> Page[RoleRead]:
    filters = []
    if q and q.strip():
        filters.append(_contains(Role.name, q))
    if industry_id is not None:
        filters.append(Role.industry_id == industry_id)
    return await _paginate(
        db,
        select(Role).where(*filters).order_by(func.lower(Role.name), Role.id),
        select(func.count()).select_from(Role).where(*filters),
        RoleRead,
        limit,
        offset,
    )


@router.get("/skills", response_model=Page[SkillRead])
async def list_skills(
    q: str | None = Query(None, max_length=100),
    category: str | None = Query(None, max_length=50),
    market_trend: str | None = Query(None, max_length=20),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> Page[SkillRead]:
    filters = []
    if q and q.strip():
        filters.append(_contains(Skill.name, q))
    if category and category.strip():
        filters.append(func.lower(Skill.category) == category.strip().lower())
    if market_trend and market_trend.strip():
        filters.append(func.lower(Skill.market_trend) == market_trend.strip().lower())
    return await _paginate(
        db,
        select(Skill).where(*filters).order_by(func.lower(Skill.name), Skill.id),
        select(func.count()).select_from(Skill).where(*filters),
        SkillRead,
        limit,
        offset,
    )


@router.get("/tools", response_model=Page[ToolRead])
async def list_tools(
    q: str | None = Query(None, max_length=100),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> Page[ToolRead]:
    filters = [_contains(Tool.name, q)] if q and q.strip() else []
    return await _paginate(
        db,
        select(Tool).where(*filters).order_by(func.lower(Tool.name), Tool.id),
        select(func.count()).select_from(Tool).where(*filters),
        ToolRead,
        limit,
        offset,
    )
