from datetime import datetime
from enum import Enum as PyEnum

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class CareerGoal(str, PyEnum):
    grow_current = "grow_current"
    level_up = "level_up"
    change_role = "change_role"
    change_industry = "change_industry"
    undecided = "undecided"


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    full_name: Mapped[str] = mapped_column(String(150))
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    current_role_name: Mapped[str] = mapped_column(String(100))
    industry_name: Mapped[str] = mapped_column(String(100))
    work_duration_months: Mapped[int | None]
    is_first_job: Mapped[bool | None] = mapped_column(Boolean)
    daily_activities: Mapped[str | None] = mapped_column(Text)
    career_goal: Mapped[CareerGoal | None] = mapped_column(SAEnum(CareerGoal))
    target_role_name: Mapped[str | None] = mapped_column(String(100))
    target_industry_name: Mapped[str | None] = mapped_column(String(100))
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship()  # noqa: F821


class UserProfileCreate(BaseModel):
    full_name: str = Field(..., max_length=150)
    current_role_name: str = Field(..., max_length=100)
    industry_name: str = Field(..., max_length=100)
    work_duration_months: int | None = Field(None, ge=0)
    is_first_job: bool | None = None
    daily_activities: str | None = None
    career_goal: CareerGoal | None = None
    target_role_name: str | None = Field(None, max_length=100)
    target_industry_name: str | None = Field(None, max_length=100)
    avatar_url: str | None = Field(None, max_length=500)


class OnboardingCreate(UserProfileCreate):
    skills: list[str] = Field(default_factory=list, max_length=8)


class UserProfileUpdate(BaseModel):
    full_name: str | None = Field(None, max_length=150)
    current_role_name: str | None = Field(None, max_length=100)
    industry_name: str | None = Field(None, max_length=100)
    work_duration_months: int | None = Field(None, ge=0)
    is_first_job: bool | None = None
    daily_activities: str | None = None
    career_goal: CareerGoal | None = None
    target_role_name: str | None = Field(None, max_length=100)
    target_industry_name: str | None = Field(None, max_length=100)
    avatar_url: str | None = Field(None, max_length=500)


class UserProfileResponse(BaseModel):
    id: int
    user_id: int
    full_name: str
    avatar_url: str | None
    current_role_name: str
    industry_name: str
    work_duration_months: int | None
    is_first_job: bool | None
    daily_activities: str | None
    career_goal: CareerGoal | None
    target_role_name: str | None
    target_industry_name: str | None
    onboarding_completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
