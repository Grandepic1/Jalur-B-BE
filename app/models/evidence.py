from datetime import date, datetime
from enum import Enum as PyEnum

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import BigInteger, Boolean, DATE, TIMESTAMP, ForeignKey, String, Text, false
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
    ai_generated: Mapped[bool] = mapped_column(Boolean, server_default=false())
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default="CURRENT_TIMESTAMP",
    )


# ─── Pydantic Schemas ────────────────────────────────────────────────


class EvidenceItemCreate(BaseModel):
    evidence_type: EvidenceType
    title: str = Field(..., max_length=200)
    user_role: str = Field(..., max_length=100)
    description: str
    impact: str
    evidence_date: date | None = None
    attachment_url: str | None = Field(None, max_length=500)
    ai_generated: bool = False


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
