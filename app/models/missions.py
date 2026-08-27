from datetime import date, datetime
from enum import Enum as PyEnum

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import BigInteger, DATE, TIMESTAMP, ForeignKey, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# ─── Enums ────────────────────────────────────────────────────────────


class MissionStatus(str, PyEnum):
    todo = "todo"
    in_progress = "in_progress"
    completed = "completed"


# ─── SQLAlchemy Model ────────────────────────────────────────────────


class SkillMission(Base):
    __tablename__ = "skill_missions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    skill_id: Mapped[int | None] = mapped_column(
        ForeignKey("skills.id", ondelete="SET NULL")
    )
    pivot_skill_gap_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("pivot_skill_gaps.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[MissionStatus] = mapped_column(
        SAEnum(MissionStatus), default=MissionStatus.todo
    )
    due_date: Mapped[date | None] = mapped_column(DATE)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default="CURRENT_TIMESTAMP",
    )

    skill: Mapped["Skill | None"] = relationship()  # noqa: F821
    pivot_skill_gap: Mapped["PivotSkillGap | None"] = relationship()  # noqa: F821


# ─── Pydantic Schemas ────────────────────────────────────────────────


class SkillMissionCreate(BaseModel):
    skill_id: int | None = None
    pivot_skill_gap_id: int | None = None
    title: str = Field(..., max_length=200)
    description: str | None = None
    status: MissionStatus = MissionStatus.todo
    due_date: date | None = None


class SkillMissionResponse(BaseModel):
    id: int
    user_id: int
    skill_id: int | None
    pivot_skill_gap_id: int | None
    title: str
    description: str | None
    status: MissionStatus
    due_date: date | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
