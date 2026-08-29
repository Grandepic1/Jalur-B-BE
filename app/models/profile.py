from datetime import datetime
from enum import Enum as PyEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.user import UserResponse


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


class OnboardingCreate(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=150)
    current_role_name: str = Field(..., min_length=1, max_length=100)
    industry_name: str = Field(..., min_length=1, max_length=100)
    work_duration_months: int = Field(..., strict=True, ge=0, le=960)
    is_first_job: bool = Field(..., strict=True)
    daily_activities: str = Field(..., min_length=1, max_length=5000)
    career_goal: CareerGoal
    target_role_name: str | None = Field(None, max_length=100)
    target_industry_name: str | None = Field(None, max_length=100)
    skills: list[str] = Field(..., min_length=1, max_length=8)

    @field_validator(
        "full_name",
        "current_role_name",
        "industry_name",
        "daily_activities",
        "target_role_name",
        "target_industry_name",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: object) -> object:
        if value is None or not isinstance(value, str):
            return value
        normalized = " ".join(value.split())
        return normalized or None

    @field_validator("skills")
    @classmethod
    def normalize_skills(cls, values: list[object]) -> list[object]:
        normalized: list[object] = []
        seen: set[str] = set()
        for value in values:
            if not isinstance(value, str):
                normalized.append(value)
                continue
            skill = " ".join(value.split())
            if len(skill) > 100:
                raise ValueError("skill names must not exceed 100 characters")
            key = skill.lower()
            if skill and key not in seen:
                normalized.append(skill)
                seen.add(key)
        if not normalized:
            raise ValueError("at least one non-empty skill is required")
        return normalized


class UserProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(None, min_length=1, max_length=150)
    current_role_name: str | None = Field(None, min_length=1, max_length=100)
    industry_name: str | None = Field(None, min_length=1, max_length=100)
    work_duration_months: int | None = Field(None, strict=True, ge=0, le=960)
    is_first_job: bool | None = Field(None, strict=True)
    daily_activities: str | None = Field(None, min_length=1, max_length=5000)
    career_goal: CareerGoal | None = None
    target_role_name: str | None = Field(None, max_length=100)
    target_industry_name: str | None = Field(None, max_length=100)
    avatar_url: str | None = Field(None, max_length=500)

    @field_validator(
        "full_name",
        "current_role_name",
        "industry_name",
        "daily_activities",
        "target_role_name",
        "target_industry_name",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: object) -> object:
        if value is None or not isinstance(value, str):
            return value
        normalized = " ".join(value.split())
        return normalized or None

    @model_validator(mode="after")
    def prevent_required_fields_from_being_cleared(self) -> "UserProfileUpdate":
        for field in ("full_name", "current_role_name", "industry_name"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null or empty")
        return self


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


class OnboardingSkillResponse(BaseModel):
    id: int
    name: str
    category: str | None
    market_trend: str

    model_config = ConfigDict(from_attributes=True)


class OnboardingResponse(BaseModel):
    completed: bool
    profile: UserProfileResponse | None
    skills: list[OnboardingSkillResponse]


class OnboardingOptionsResponse(BaseModel):
    career_goals: list[CareerGoal]
    industries: list[str]
    skills: list[OnboardingSkillResponse]


class ProfileResponse(BaseModel):
    user: UserResponse
    profile: UserProfileResponse
    skills: list[OnboardingSkillResponse]
