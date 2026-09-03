from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.profile import OnboardingSkillResponse, UserProfileResponse

CVSkill = Annotated[str, Field(min_length=1, max_length=100)]


class UserCV(Base):
    __tablename__ = "user_cvs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    # Legacy file columns are nullable and no longer populated: confirmed CVs do not
    # retain the source file, only the reviewed extracted data.
    file_name: Mapped[str | None] = mapped_column(String(255))
    file_size: Mapped[int | None] = mapped_column(Integer)
    content_type: Mapped[str | None] = mapped_column(String(100))
    storage_object_path: Mapped[str | None] = mapped_column(String(500))
    source_preview_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), unique=True
    )
    experiences: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    provider_model: Mapped[str] = mapped_column(String(100))
    uploaded_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="CURRENT_TIMESTAMP"
    )


class CVConfirmationReceipt(Base):
    __tablename__ = "cv_confirmation_receipts"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "preview_id", name="uq_cv_confirmation_receipt"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    preview_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    confirmed_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="CURRENT_TIMESTAMP"
    )


class CVProfileExtraction(BaseModel):
    full_name: str | None = Field(None, min_length=1, max_length=150)
    current_role_name: str | None = Field(None, min_length=1, max_length=100)
    industry_name: str | None = Field(None, min_length=1, max_length=100)
    work_duration_months: int | None = Field(None, strict=True, ge=0, le=960)
    daily_activities: str | None = Field(None, min_length=20, max_length=5000)

    model_config = ConfigDict(extra="forbid")

    @field_validator(
        "full_name",
        "current_role_name",
        "industry_name",
        "daily_activities",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = " ".join(value.split())
        return normalized or None


class CVExperience(BaseModel):
    role: str = Field(..., min_length=2, max_length=150)
    company: str | None = Field(None, min_length=2, max_length=150)
    start_date: str | None = Field(None, min_length=2, max_length=50)
    end_date: str | None = Field(None, min_length=2, max_length=50)
    description: str | None = Field(None, min_length=20, max_length=1000)

    model_config = ConfigDict(extra="forbid")

    @field_validator(
        "role", "company", "start_date", "end_date", "description", mode="before"
    )
    @classmethod
    def normalize_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = " ".join(value.split())
        return normalized or None


def _normalize_skills(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        skill = " ".join(value.split())
        if len(skill) > 100:
            raise ValueError("skill names must not exceed 100 characters")
        key = skill.lower()
        if skill and key not in seen:
            normalized.append(skill)
            seen.add(key)
    return normalized


class CVExtractionAIResult(BaseModel):
    profile: CVProfileExtraction
    skills: list[CVSkill] = Field(..., max_length=20)
    experiences: list[CVExperience] = Field(..., max_length=12)

    model_config = ConfigDict(extra="forbid")

    @field_validator("skills")
    @classmethod
    def normalize_skills(cls, values: list[str]) -> list[str]:
        return _normalize_skills(values)


class CVResponse(BaseModel):
    uploaded_at: datetime
    experiences: list[CVExperience] = Field(..., max_length=12)
    model: str


class CVPreviewResponse(BaseModel):
    preview_id: UUID
    preview_token: str
    file_name: str
    file_size: int
    content_type: str
    expires_at: datetime
    profile: CVProfileExtraction
    skills: list[CVSkill] = Field(..., max_length=20)
    experiences: list[CVExperience] = Field(..., max_length=12)
    model: str


class CVPreviewTokenData(BaseModel):
    preview_id: UUID
    user_id: int
    expires_at: datetime
    model: str = Field(..., max_length=100)

    model_config = ConfigDict(extra="forbid")


class CVConfirmRequest(BaseModel):
    """User-reviewed values sent after editing the preview draft.

    These values replace the AI extraction: the confirmed profile fields, skills, and
    career history are whatever the authenticated user reviewed and edited.
    """

    preview_token: str = Field(..., min_length=1)
    profile: CVProfileExtraction
    skills: list[CVSkill] = Field(..., max_length=20)
    experiences: list[CVExperience] = Field(..., max_length=12)

    model_config = ConfigDict(extra="forbid")

    @field_validator("skills")
    @classmethod
    def normalize_skills(cls, values: list[str]) -> list[str]:
        return _normalize_skills(values)


class CVConfirmResponse(BaseModel):
    cv: CVResponse
    profile: UserProfileResponse
    skills: list[OnboardingSkillResponse]
