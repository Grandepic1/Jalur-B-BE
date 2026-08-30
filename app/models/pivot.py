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
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# ─── Enums ────────────────────────────────────────────────────────────


class GapLevel(str, PyEnum):
    small = "small"
    medium = "medium"
    large = "large"


# ─── SQLAlchemy Models ───────────────────────────────────────────────


class PivotAnalysis(Base):
    __tablename__ = "pivot_analyses"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    current_role_name: Mapped[str] = mapped_column(String(100))
    industry_name: Mapped[str] = mapped_column(String(100))
    work_experience: Mapped[str] = mapped_column(Text)
    responsibilities: Mapped[str | None] = mapped_column(Text)
    skills_text: Mapped[str | None] = mapped_column(Text)
    tools_and_methods: Mapped[str | None] = mapped_column(Text)
    job_description: Mapped[str | None] = mapped_column(Text)
    job_description_url: Mapped[str | None] = mapped_column(String(500))
    achievements: Mapped[str | None] = mapped_column(Text)
    work_preferences: Mapped[str | None] = mapped_column(Text)
    target_role_id: Mapped[int | None] = mapped_column(
        ForeignKey("roles.id", ondelete="SET NULL")
    )
    match_score: Mapped[Decimal] = mapped_column(DECIMAL(5, 2))
    shared_skills_count: Mapped[int | None] = mapped_column(Integer)
    missing_skills_count: Mapped[int | None] = mapped_column(Integer)
    summary: Mapped[str | None] = mapped_column(Text)
    data_confidence: Mapped[Decimal | None] = mapped_column(DECIMAL(5, 2))
    provider_model: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(50))
    scoring_version: Mapped[str | None] = mapped_column(String(50))
    market_baseline_version: Mapped[str | None] = mapped_column(String(64))
    input_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    analyzed_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        server_default="CURRENT_TIMESTAMP",
    )

    preferred_roles: Mapped[list["PivotPreferredRole"]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan"
    )
    skill_gaps: Mapped[list["PivotSkillGap"]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan"
    )
    target_role: Mapped["Role | None"] = relationship()  # noqa: F821


Index(
    "ix_pivot_analyses_user_analyzed",
    PivotAnalysis.user_id,
    PivotAnalysis.analyzed_at.desc(),
    PivotAnalysis.id.desc(),
)


class PivotPreferredRole(Base):
    __tablename__ = "pivot_preferred_roles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    analysis_id: Mapped[int] = mapped_column(
        ForeignKey("pivot_analyses.id", ondelete="CASCADE")
    )
    role_name: Mapped[str] = mapped_column(String(100))
    match_score: Mapped[Decimal | None] = mapped_column(DECIMAL(5, 2))
    preparation_time_months: Mapped[int | None] = mapped_column(Integer)
    preparation_description: Mapped[str | None] = mapped_column(Text)

    analysis: Mapped["PivotAnalysis"] = relationship(back_populates="preferred_roles")


class PivotSkillGap(Base):
    __tablename__ = "pivot_skill_gaps"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    analysis_id: Mapped[int] = mapped_column(
        ForeignKey("pivot_analyses.id", ondelete="CASCADE")
    )
    preferred_role_id: Mapped[int | None] = mapped_column(
        ForeignKey("pivot_preferred_roles.id", ondelete="CASCADE")
    )
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"))
    current_level: Mapped[int | None] = mapped_column(
        Integer
    )  # 1-5, NULL jika belum dimiliki
    required_level: Mapped[int] = mapped_column(Integer)  # 1-5
    gap_level: Mapped[GapLevel] = mapped_column(SAEnum(GapLevel))
    recommended_action: Mapped[str | None] = mapped_column(String(255))

    analysis: Mapped["PivotAnalysis"] = relationship(back_populates="skill_gaps")
    preferred_role: Mapped["PivotPreferredRole | None"] = relationship()
    skill: Mapped["Skill"] = relationship()  # noqa: F821


Index("ix_pivot_skill_gaps_preferred_role_id", PivotSkillGap.preferred_role_id)


# ─── Pydantic Schemas ────────────────────────────────────────────────


class PivotPreferredRoleResponse(BaseModel):
    id: int
    analysis_id: int
    role_name: str
    match_score: Decimal | None
    preparation_time_months: int | None
    preparation_description: str | None

    model_config = ConfigDict(from_attributes=True)


class PivotSkillGapResponse(BaseModel):
    id: int
    analysis_id: int
    skill_id: int
    current_level: int | None
    required_level: int
    gap_level: GapLevel
    recommended_action: str | None

    model_config = ConfigDict(from_attributes=True)


class PivotAnalysisCreate(BaseModel):
    current_role_name: str = Field(..., max_length=100)
    industry_name: str = Field(..., max_length=100)
    work_experience: str
    responsibilities: str | None = None
    skills_text: str | None = None
    tools_and_methods: str | None = None
    job_description: str | None = None
    job_description_url: str | None = Field(None, max_length=500)
    achievements: str | None = None
    work_preferences: str | None = None
    preferred_role_names: list[str] = Field(default_factory=list)


class PivotAnalysisResponse(BaseModel):
    id: int
    user_id: int
    current_role_name: str
    industry_name: str
    work_experience: str
    responsibilities: str | None
    skills_text: str | None
    tools_and_methods: str | None
    job_description: str | None
    job_description_url: str | None
    achievements: str | None
    work_preferences: str | None
    target_role_id: int | None
    match_score: Decimal
    shared_skills_count: int | None
    missing_skills_count: int | None
    summary: str | None
    analyzed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PivotAnalysisWithDetails(PivotAnalysisResponse):
    preferred_roles: list[PivotPreferredRoleResponse]
    skill_gaps: list[PivotSkillGapResponse]
