from datetime import datetime
from decimal import Decimal
from enum import Enum as PyEnum

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    BigInteger,
    DECIMAL,
    TIMESTAMP,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base


# ─── Enums ────────────────────────────────────────────────────────────


class HealthLevel(str, PyEnum):
    low = "low"
    medium = "medium"
    high = "high"


# ─── SQLAlchemy Models ───────────────────────────────────────────────


class HealthAssessment(Base):
    __tablename__ = "health_assessments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role_name: Mapped[str] = mapped_column(String(100))
    industry_name: Mapped[str] = mapped_column(String(100))
    work_duration_months: Mapped[int] = mapped_column(Integer)
    responsibilities: Mapped[str] = mapped_column(Text)
    achievements: Mapped[str | None] = mapped_column(Text)
    performance_feedback: Mapped[str | None] = mapped_column(Text)
    performance_feedback_url: Mapped[str | None] = mapped_column(String(500))
    career_progression: Mapped[str | None] = mapped_column(Text)
    overall_score: Mapped[Decimal] = mapped_column(DECIMAL(5, 2))
    level: Mapped[HealthLevel] = mapped_column(SAEnum(HealthLevel))
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

    breakdowns: Mapped[list["HealthScoreBreakdown"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )


class HealthScoreBreakdown(Base):
    __tablename__ = "health_score_breakdowns"
    __table_args__ = (
        UniqueConstraint(
            "assessment_id", "dimension", name="uq_health_breakdown_dimension"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("health_assessments.id", ondelete="CASCADE")
    )
    dimension: Mapped[str] = mapped_column(
        String(50)
    )  # performance | growth | skill_relevance | adaptability | mobility
    score: Mapped[Decimal] = mapped_column(DECIMAL(5, 2))
    note: Mapped[str | None] = mapped_column(String(255))

    assessment: Mapped["HealthAssessment"] = relationship(back_populates="breakdowns")


Index(
    "ix_health_assessments_user_assessed",
    HealthAssessment.user_id,
    HealthAssessment.assessed_at.desc(),
    HealthAssessment.id.desc(),
)


# ─── Pydantic Schemas ────────────────────────────────────────────────


class HealthAssessmentCreate(BaseModel):
    role_name: str = Field(..., max_length=100)
    industry_name: str = Field(..., max_length=100)
    work_duration_months: int = Field(..., gt=0)
    responsibilities: str
    achievements: str | None = None
    performance_feedback: str | None = None
    performance_feedback_url: str | None = Field(None, max_length=500)
    career_progression: str | None = None


class HealthAssessmentResponse(BaseModel):
    id: int
    user_id: int
    role_name: str
    industry_name: str
    work_duration_months: int
    responsibilities: str
    achievements: str | None
    performance_feedback: str | None
    performance_feedback_url: str | None
    career_progression: str | None
    overall_score: Decimal
    level: HealthLevel
    assessed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class HealthScoreBreakdownResponse(BaseModel):
    id: int
    assessment_id: int
    dimension: str
    score: Decimal
    note: str | None

    model_config = ConfigDict(from_attributes=True)


class HealthAssessmentWithBreakdowns(HealthAssessmentResponse):
    breakdowns: list[HealthScoreBreakdownResponse]
