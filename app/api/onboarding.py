from datetime import UTC, datetime
from hashlib import sha256

from fastapi import APIRouter, Depends
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_verified_user
from app.core.database import get_db
from app.models.master import Industry, Skill
from app.models.profile import (
    CareerGoal,
    OnboardingCreate,
    OnboardingOptionsResponse,
    OnboardingResponse,
    OnboardingSkillResponse,
    UserProfile,
    UserProfileResponse,
)
from app.models.user import User
from app.models.user_skills import UserSkill


router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


async def _lock_user_onboarding(db: AsyncSession, user_id: int) -> None:
    material = f"onboarding:{user_id}".encode("utf-8")
    lock_key = int.from_bytes(sha256(material).digest()[:8], signed=True)
    await db.execute(select(func.pg_advisory_xact_lock(lock_key)))


async def _get_onboarding_response(db: AsyncSession, user_id: int) -> OnboardingResponse:
    profile = await db.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
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
    return OnboardingResponse(
        completed=bool(profile and profile.onboarding_completed_at),
        profile=UserProfileResponse.model_validate(profile) if profile else None,
        skills=[OnboardingSkillResponse.model_validate(skill) for skill in skills],
    )


@router.get("", response_model=OnboardingResponse)
async def get_onboarding(
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> OnboardingResponse:
    return await _get_onboarding_response(db, user.id)


@router.put("", response_model=OnboardingResponse)
async def complete_onboarding(
    payload: OnboardingCreate,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> OnboardingResponse:
    await _lock_user_onboarding(db, user.id)
    profile = await db.scalar(
        select(UserProfile)
        .where(UserProfile.user_id == user.id)
        .with_for_update()
    )
    profile_values = payload.model_dump(exclude={"skills"})
    if profile is None:
        profile = UserProfile(user_id=user.id, **profile_values)
        db.add(profile)
    else:
        for field, value in profile_values.items():
            setattr(profile, field, value)
    if profile.onboarding_completed_at is None:
        profile.onboarding_completed_at = datetime.now(UTC)

    skill_rows = [{"name": name, "market_trend": "stable"} for name in payload.skills]
    await db.execute(
        insert(Skill)
        .values(skill_rows)
        .on_conflict_do_nothing(index_elements=[func.lower(Skill.name)])
    )
    skill_keys = [name.lower() for name in payload.skills]
    skills = list(
        (
            await db.scalars(
                select(Skill).where(func.lower(Skill.name).in_(skill_keys))
            )
        ).all()
    )

    selected_skill_ids = {skill.id for skill in skills}
    existing_skill_ids = set(
        (
            await db.scalars(
                select(UserSkill.skill_id).where(UserSkill.user_id == user.id)
            )
        ).all()
    )
    await db.execute(
        delete(UserSkill).where(
            UserSkill.user_id == user.id,
            UserSkill.skill_id.not_in(selected_skill_ids),
        )
    )
    db.add_all(
        [
            UserSkill(user_id=user.id, skill_id=skill_id)
            for skill_id in selected_skill_ids - existing_skill_ids
        ]
    )
    await db.commit()
    return await _get_onboarding_response(db, user.id)


@router.get("/options", response_model=OnboardingOptionsResponse)
async def get_onboarding_options(
    _: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> OnboardingOptionsResponse:
    industries = list((await db.scalars(select(Industry.name).order_by(Industry.name))).all())
    skills = list((await db.scalars(select(Skill).order_by(func.lower(Skill.name)))).all())
    return OnboardingOptionsResponse(
        career_goals=list(CareerGoal),
        industries=industries,
        skills=[OnboardingSkillResponse.model_validate(skill) for skill in skills],
    )
