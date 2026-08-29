from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_verified_user
from app.core.database import get_db
from app.models.master import Page, Skill, SkillRead
from app.models.profile import (
    OnboardingSkillResponse,
    ProfileResponse,
    UserProfile,
    UserProfileResponse,
    UserProfileUpdate,
)
from app.models.user import User, UserResponse
from app.models.user_skills import UserSkill, UserSkillDetailResponse, UserSkillUpdate


router = APIRouter(prefix="/api/profile", tags=["profile"])


async def _profile_response(
    db: AsyncSession,
    user: User,
    profile: UserProfile,
) -> ProfileResponse:
    skills = list(
        (
            await db.scalars(
                select(Skill)
                .join(UserSkill, UserSkill.skill_id == Skill.id)
                .where(UserSkill.user_id == user.id)
                .order_by(func.lower(Skill.name))
            )
        ).all()
    )
    return ProfileResponse(
        user=UserResponse.model_validate(user),
        profile=UserProfileResponse.model_validate(profile),
        skills=[OnboardingSkillResponse.model_validate(skill) for skill in skills],
    )


async def _get_profile_or_404(db: AsyncSession, user_id: int) -> UserProfile:
    profile = await db.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found; complete onboarding first",
        )
    return profile


def _skill_response(user_skill: UserSkill, skill: Skill) -> UserSkillDetailResponse:
    return UserSkillDetailResponse(
        id=user_skill.id,
        user_id=user_skill.user_id,
        skill_id=user_skill.skill_id,
        proficiency_level=user_skill.proficiency_level,
        years_experience=user_skill.years_experience,
        skill=SkillRead.model_validate(skill),
    )


@router.get("", response_model=ProfileResponse)
async def get_profile(
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    profile = await _get_profile_or_404(db, user.id)
    return await _profile_response(db, user, profile)


@router.patch("", response_model=ProfileResponse)
async def update_profile(
    payload: UserProfileUpdate,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    profile = await db.scalar(
        select(UserProfile)
        .where(UserProfile.user_id == user.id)
        .with_for_update()
    )
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found; complete onboarding first",
        )
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    await db.commit()
    await db.refresh(profile)
    return await _profile_response(db, user, profile)


@router.get("/skills", response_model=Page[UserSkillDetailResponse])
async def list_profile_skills(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> Page[UserSkillDetailResponse]:
    total = await db.scalar(
        select(func.count()).select_from(UserSkill).where(UserSkill.user_id == user.id)
    )
    rows = (
        await db.execute(
            select(UserSkill, Skill)
            .join(Skill, Skill.id == UserSkill.skill_id)
            .where(UserSkill.user_id == user.id)
            .order_by(func.lower(Skill.name), Skill.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return Page[UserSkillDetailResponse](
        items=[_skill_response(user_skill, skill) for user_skill, skill in rows],
        total=total or 0,
        limit=limit,
        offset=offset,
    )


@router.put("/skills/{skill_id}", response_model=UserSkillDetailResponse)
async def upsert_profile_skill(
    skill_id: int,
    payload: UserSkillUpdate,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> UserSkillDetailResponse:
    skill = await db.get(Skill, skill_id)
    if skill is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found")
    values = payload.model_dump()
    await db.execute(
        insert(UserSkill)
        .values(user_id=user.id, skill_id=skill_id, **values)
        .on_conflict_do_update(
            constraint="uq_user_skill",
            set_=values,
        )
    )
    await db.commit()
    user_skill = await db.scalar(
        select(UserSkill).where(
            UserSkill.user_id == user.id,
            UserSkill.skill_id == skill_id,
        )
    )
    return _skill_response(user_skill, skill)


@router.delete("/skills/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile_skill(
    skill_id: int,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    result = await db.execute(
        delete(UserSkill).where(
            UserSkill.user_id == user.id,
            UserSkill.skill_id == skill_id,
        )
    )
    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User skill not found",
        )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
