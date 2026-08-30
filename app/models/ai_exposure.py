from datetime import datetime
from enum import Enum as PyEnum
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import BigInteger, DECIMAL, TIMESTAMP, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# ─── Enums ────────────────────────────────────────────────────────────


class ExposureLevel(str, PyEnum):
    low = "low"
    medium = "medium"
    high = "high"


class SkillRelevanceStatus(str, PyEnum):
    declining = "declining"
    stable = "stable"
    rising = "rising"


# ─── SQLAlchemy Models ───────────────────────────────────────────────


class AiExposureAssessment(Base):
    __tablename__ = "ai_exposure_assessments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role_name: Mapped[str] = mapped_column(String(100))
    responsibilities: Mapped[str] = mapped_column(Text)
    work_experience: Mapped[str | None] = mapped_column(Text)
    job_description: Mapped[str | None] = mapped_column(Text)
    job_description_url: Mapped[str | None] = mapped_column(String(500))
    overall_exposure_level: Mapped[ExposureLevel] = mapped_column(SAEnum(ExposureLevel))
    overall_exposure_score: Mapped[Decimal | None] = mapped_column(DECIMAL(5, 2))
    skill_relevance_score: Mapped[Decimal | None] = mapped_column(DECIMAL(5, 2))
    summary: Mapped[str | None] = mapped_column(Text)
    data_confidence: Mapped[Decimal | None] = mapped_column(DECIMAL(5, 2))
    provider_model: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(50))
    scoring_version: Mapped[str | None] = mapped_column(String(50))
    market_baseline_version: Mapped[str | None] = mapped_column(String(64))
    input_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    assessed_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        server_default="CURRENT_TIMESTAMP",
    )

    exposed_activities: Mapped[list["ExposedActivity"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )
    skill_relevances: Mapped[list["SkillRelevance"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )
    skills: Mapped[list["AiExposureSkill"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )
    tools: Mapped[list["AiExposureTool"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )


Index(
    "ix_ai_exposure_user_assessed",
    AiExposureAssessment.user_id,
    AiExposureAssessment.assessed_at.desc(),
    AiExposureAssessment.id.desc(),
)


class ExposedActivity(Base):
    __tablename__ = "exposed_activities"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("ai_exposure_assessments.id", ondelete="CASCADE")
    )
    activity_name: Mapped[str] = mapped_column(String(150))
    exposure_level: Mapped[ExposureLevel] = mapped_column(SAEnum(ExposureLevel))
    exposure_score: Mapped[Decimal | None] = mapped_column(DECIMAL(5, 2))
    ai_impact_note: Mapped[str | None] = mapped_column(Text)

    assessment: Mapped["AiExposureAssessment"] = relationship(
        back_populates="exposed_activities"
    )


class SkillRelevance(Base):
    __tablename__ = "skill_relevances"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("ai_exposure_assessments.id", ondelete="CASCADE")
    )
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"))
    status: Mapped[SkillRelevanceStatus] = mapped_column(SAEnum(SkillRelevanceStatus))
    recommendation: Mapped[str | None] = mapped_column(String(255))

    assessment: Mapped["AiExposureAssessment"] = relationship(
        back_populates="skill_relevances"
    )
    skill: Mapped["Skill"] = relationship()  # noqa: F821


class AiExposureSkill(Base):
    __tablename__ = "ai_exposure_skills"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("ai_exposure_assessments.id", ondelete="CASCADE")
    )
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"))

    assessment: Mapped["AiExposureAssessment"] = relationship(back_populates="skills")
    skill: Mapped["Skill"] = relationship()  # noqa: F821


class AiExposureTool(Base):
    __tablename__ = "ai_exposure_tools"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("ai_exposure_assessments.id", ondelete="CASCADE")
    )
    tool_id: Mapped[int] = mapped_column(ForeignKey("tools.id", ondelete="CASCADE"))

    assessment: Mapped["AiExposureAssessment"] = relationship(back_populates="tools")
    tool: Mapped["Tool"] = relationship()  # noqa: F821


# ─── Pydantic Schemas ────────────────────────────────────────────────


class ExposedActivityResponse(BaseModel):
    id: int
    assessment_id: int
    activity_name: str
    exposure_level: ExposureLevel
    ai_impact_note: str | None

    model_config = ConfigDict(from_attributes=True)


class SkillRelevanceResponse(BaseModel):
    id: int
    assessment_id: int
    skill_id: int
    status: SkillRelevanceStatus
    recommendation: str | None

    model_config = ConfigDict(from_attributes=True)


class AiExposureAssessmentCreate(BaseModel):
    role_name: str = Field(..., max_length=100)
    responsibilities: str
    work_experience: str | None = None
    job_description: str | None = None
    job_description_url: str | None = Field(None, max_length=500)
    skill_ids: list[int] = []
    tool_ids: list[int] = []


class AiExposureAssessmentResponse(BaseModel):
    id: int
    user_id: int
    role_name: str
    responsibilities: str
    work_experience: str | None
    job_description: str | None
    job_description_url: str | None
    overall_exposure_level: ExposureLevel
    summary: str | None
    assessed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AiExposureAssessmentWithDetails(AiExposureAssessmentResponse):
    exposed_activities: list[ExposedActivityResponse]
    skill_relevances: list[SkillRelevanceResponse]
