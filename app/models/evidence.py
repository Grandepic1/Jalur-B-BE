from datetime import date, datetime
from enum import Enum as PyEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import BigInteger, Boolean, DATE, TIMESTAMP, ForeignKey, Index, String, Text, false
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


# ─── Enums ────────────────────────────────────────────────────────────


class EvidenceType(str, PyEnum):
    project = "project"
    achievement = "achievement"
    feedback = "feedback"
    certificate = "certificate"
    award = "award"
    training = "training"
    other = "other"


# ─── SQLAlchemy Model ────────────────────────────────────────────────


class EvidenceItem(Base):
    __tablename__ = "evidence_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    evidence_type: Mapped[EvidenceType] = mapped_column(SAEnum(EvidenceType))
    title: Mapped[str] = mapped_column(String(200))
    user_role: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    impact: Mapped[str] = mapped_column(Text)
    evidence_date: Mapped[date | None] = mapped_column(DATE)
    attachment_url: Mapped[str | None] = mapped_column(String(500))
    attachment_object_path: Mapped[str | None] = mapped_column(String(500))
    ai_generated: Mapped[bool] = mapped_column(Boolean, server_default=false())
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default="CURRENT_TIMESTAMP",
    )


Index(
    "ix_evidence_items_user_created",
    EvidenceItem.user_id,
    EvidenceItem.created_at.desc(),
    EvidenceItem.id.desc(),
)
Index(
    "ix_evidence_items_user_type_created",
    EvidenceItem.user_id,
    EvidenceItem.evidence_type,
    EvidenceItem.created_at.desc(),
    EvidenceItem.id.desc(),
)


# ─── Pydantic Schemas ────────────────────────────────────────────────


class EvidenceItemCreate(BaseModel):
    evidence_type: EvidenceType
    title: str = Field(..., min_length=1, max_length=200)
    user_role: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1, max_length=10000)
    impact: str = Field(..., min_length=1, max_length=5000)
    evidence_date: date | None = None
    ai_generated: Literal[False] = False

    model_config = ConfigDict(extra="forbid")

    @field_validator("title", "user_role", "description", "impact")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("value cannot be blank")
        return value


class EvidenceItemUpdate(BaseModel):
    evidence_type: EvidenceType | None = None
    title: str | None = Field(None, min_length=1, max_length=200)
    user_role: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, min_length=1, max_length=10000)
    impact: str | None = Field(None, min_length=1, max_length=5000)
    evidence_date: date | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("title", "user_role", "description", "impact")
    @classmethod
    def normalize_required_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = " ".join(value.split())
        if not value:
            raise ValueError("value cannot be blank")
        return value

    @model_validator(mode="after")
    def reject_null_required_fields(self) -> "EvidenceItemUpdate":
        for field in ("evidence_type", "title", "user_role", "description", "impact"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class EvidenceItemResponse(BaseModel):
    id: int
    user_id: int
    evidence_type: EvidenceType
    title: str
    user_role: str
    description: str
    impact: str
    evidence_date: date | None
    attachment_url: str | None
    ai_generated: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EvidenceStatsResponse(BaseModel):
    total: int
    by_type: dict[EvidenceType, int]
    human_authored: int
    ai_generated: int
