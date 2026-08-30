from datetime import datetime
from enum import Enum as PyEnum

from pydantic import BaseModel, ConfigDict, Field
from decimal import Decimal

from sqlalchemy import BigInteger, DECIMAL, TIMESTAMP, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# ─── Enums ────────────────────────────────────────────────────────────


class RiskLevel(str, PyEnum):
    low = "low"
    medium = "medium"
    high = "high"


# ─── SQLAlchemy Models ───────────────────────────────────────────────


class RiskScan(Base):
    __tablename__ = "risk_scans"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role_name: Mapped[str] = mapped_column(String(100))
    industry_name: Mapped[str] = mapped_column(String(100))
    responsibilities: Mapped[str] = mapped_column(Text)
    work_changes: Mapped[str | None] = mapped_column(Text)
    job_description: Mapped[str | None] = mapped_column(Text)
    job_description_url: Mapped[str | None] = mapped_column(String(500))
    overall_risk_level: Mapped[RiskLevel] = mapped_column(SAEnum(RiskLevel))
    overall_score: Mapped[Decimal | None] = mapped_column(DECIMAL(5, 2))
    summary: Mapped[str | None] = mapped_column(Text)
    analysis_description: Mapped[str | None] = mapped_column(Text)
    early_warning: Mapped[str | None] = mapped_column(Text)
    data_confidence: Mapped[Decimal | None] = mapped_column(DECIMAL(5, 2))
    provider_model: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(50))
    scoring_version: Mapped[str | None] = mapped_column(String(50))
    market_baseline_version: Mapped[str | None] = mapped_column(String(64))
    input_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    scanned_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        server_default="CURRENT_TIMESTAMP",
    )

    factors: Mapped[list["RiskFactor"]] = relationship(
        back_populates="scan", cascade="all, delete-orphan"
    )
    skills: Mapped[list["RiskScanSkill"]] = relationship(
        back_populates="scan", cascade="all, delete-orphan"
    )


Index(
    "ix_risk_scans_user_scanned",
    RiskScan.user_id,
    RiskScan.scanned_at.desc(),
    RiskScan.id.desc(),
)


class RiskFactor(Base):
    __tablename__ = "risk_factors"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    scan_id: Mapped[int] = mapped_column(
        ForeignKey("risk_scans.id", ondelete="CASCADE")
    )
    source: Mapped[str] = mapped_column(
        String(50)
    )  # industry_shift | market_demand | role_change | skill_dependency | ai_advancement
    severity: Mapped[RiskLevel] = mapped_column(SAEnum(RiskLevel))
    score: Mapped[Decimal | None] = mapped_column(DECIMAL(5, 2))
    description: Mapped[str] = mapped_column(Text)

    scan: Mapped["RiskScan"] = relationship(back_populates="factors")


class RiskScanSkill(Base):
    __tablename__ = "risk_scan_skills"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    scan_id: Mapped[int] = mapped_column(
        ForeignKey("risk_scans.id", ondelete="CASCADE")
    )
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"))

    scan: Mapped["RiskScan"] = relationship(back_populates="skills")
    skill: Mapped["Skill"] = relationship()  # noqa: F821


# ─── Pydantic Schemas ────────────────────────────────────────────────


class RiskFactorResponse(BaseModel):
    id: int
    scan_id: int
    source: str
    severity: RiskLevel
    description: str

    model_config = ConfigDict(from_attributes=True)


class RiskScanCreate(BaseModel):
    role_name: str = Field(..., max_length=100)
    industry_name: str = Field(..., max_length=100)
    responsibilities: str
    work_changes: str | None = None
    job_description: str | None = None
    job_description_url: str | None = Field(None, max_length=500)
    skill_ids: list[int] = []


class RiskScanResponse(BaseModel):
    id: int
    user_id: int
    role_name: str
    industry_name: str
    responsibilities: str
    work_changes: str | None
    job_description: str | None
    job_description_url: str | None
    overall_risk_level: RiskLevel
    summary: str | None
    scanned_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RiskScanWithFactors(RiskScanResponse):
    factors: list[RiskFactorResponse]
