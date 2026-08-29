from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_verified_user
from app.core.database import get_db
from app.models.master import Skill
from app.models.profile import (
    OnboardingSkillResponse,
    ProfileResponse,
    UserProfile,
    UserProfileResponse,
    UserProfileUpdate,
)
from app.models.user import User, UserResponse
from app.models.user_skills import UserSkill


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
