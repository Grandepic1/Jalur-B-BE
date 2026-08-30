from datetime import datetime
from enum import Enum as PyEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class MarketBaselineStatus(str, PyEnum):
    draft = "draft"
    approved = "approved"
    rejected = "rejected"
    archived = "archived"


class MarketSubjectType(str, PyEnum):
    role = "role"
    industry = "industry"
    skill = "skill"


class MarketSignalType(str, PyEnum):
    market_demand = "market_demand"
    industry_stability = "industry_stability"
    skill_relevance = "skill_relevance"


class MarketBaseline(Base):
    __tablename__ = "market_baselines"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    version: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[MarketBaselineStatus] = mapped_column(
        SAEnum(MarketBaselineStatus), default=MarketBaselineStatus.draft
    )
    summary: Mapped[str] = mapped_column(Text)
    provider_model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(50))
    search_queries: Mapped[list[str]] = mapped_column(JSONB)
    citations: Mapped[list[dict]] = mapped_column(JSONB)
    grounding_metadata: Mapped[dict] = mapped_column(JSONB)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    approved_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    signals: Mapped[list["MarketBaselineSignal"]] = relationship(
        back_populates="baseline", cascade="all, delete-orphan"
    )


class MarketBaselineSignal(Base):
    __tablename__ = "market_baseline_signals"
    __table_args__ = (
        CheckConstraint(
            "(signal_type = 'skill_relevance' AND classification IN "
            "('declining', 'stable', 'rising')) OR "
            "(signal_type <> 'skill_relevance' AND classification IN "
            "('weak', 'moderate', 'strong'))",
            name="ck_market_signal_classification",
        ),
        CheckConstraint(
            "(subject_type = 'role' AND signal_type = 'market_demand') OR "
            "(subject_type = 'industry' AND signal_type = 'industry_stability') OR "
            "(subject_type = 'skill' AND signal_type = 'skill_relevance')",
            name="ck_market_signal_subject_type",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    baseline_id: Mapped[int] = mapped_column(
        ForeignKey("market_baselines.id", ondelete="CASCADE")
    )
    subject_type: Mapped[MarketSubjectType] = mapped_column(SAEnum(MarketSubjectType))
    subject_name: Mapped[str] = mapped_column(String(150))
    signal_type: Mapped[MarketSignalType] = mapped_column(SAEnum(MarketSignalType))
    classification: Mapped[str] = mapped_column(String(20))
    rationale: Mapped[str] = mapped_column(Text)

    baseline: Mapped[MarketBaseline] = relationship(back_populates="signals")


Index(
    "uq_market_baseline_signal_subject",
    MarketBaselineSignal.baseline_id,
    MarketBaselineSignal.subject_type,
    func.lower(MarketBaselineSignal.subject_name),
    MarketBaselineSignal.signal_type,
    unique=True,
)
Index(
    "uq_market_baselines_one_approved",
    MarketBaseline.status,
    unique=True,
    postgresql_where=MarketBaseline.status == MarketBaselineStatus.approved,
)


class MarketBaselineSubject(BaseModel):
    subject_type: MarketSubjectType
    name: str = Field(..., min_length=1, max_length=150)

    model_config = ConfigDict(extra="forbid")

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return " ".join(value.split())


class MarketBaselineRefreshRequest(BaseModel):
    subjects: list[MarketBaselineSubject] = Field(..., min_length=1, max_length=100)

    model_config = ConfigDict(extra="forbid")

    @field_validator("subjects")
    @classmethod
    def deduplicate_subjects(
        cls, values: list[MarketBaselineSubject]
    ) -> list[MarketBaselineSubject]:
        unique: dict[tuple[str, str], MarketBaselineSubject] = {}
        for value in values:
            unique[(value.subject_type.value, value.name.lower())] = value
        return list(unique.values())


class MarketSignalDraft(BaseModel):
    subject_type: MarketSubjectType
    subject_name: str = Field(..., min_length=1, max_length=150)
    signal_type: MarketSignalType
    classification: str = Field(..., min_length=1, max_length=20)
    rationale: str = Field(..., min_length=1, max_length=1000)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_signal(self) -> "MarketSignalDraft":
        expected = {
            MarketSubjectType.role: MarketSignalType.market_demand,
            MarketSubjectType.industry: MarketSignalType.industry_stability,
            MarketSubjectType.skill: MarketSignalType.skill_relevance,
        }[self.subject_type]
        if self.signal_type != expected:
            raise ValueError("signal_type does not match subject_type")
        allowed = (
            {"declining", "stable", "rising"}
            if self.signal_type == MarketSignalType.skill_relevance
            else {"weak", "moderate", "strong"}
        )
        if self.classification not in allowed:
            raise ValueError("classification does not match signal_type")
        return self


class MarketBaselineAIResult(BaseModel):
    summary: str = Field(..., min_length=1, max_length=2000)
    signals: list[MarketSignalDraft] = Field(..., min_length=1, max_length=100)

    model_config = ConfigDict(extra="forbid")


class MarketCitationResponse(BaseModel):
    title: str
    url: str


class MarketSignalResponse(BaseModel):
    subject_type: MarketSubjectType
    subject_name: str
    signal_type: MarketSignalType
    classification: str
    rationale: str

    model_config = ConfigDict(from_attributes=True)


class MarketBaselineResponse(BaseModel):
    id: int
    version: str
    status: MarketBaselineStatus
    summary: str
    provider_model: str
    prompt_version: str
    search_queries: list[str]
    citations: list[MarketCitationResponse]
    generated_at: datetime
    approved_at: datetime | None
    signals: list[MarketSignalResponse]

    model_config = ConfigDict(from_attributes=True)
