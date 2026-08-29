from datetime import date, datetime
from decimal import Decimal
from enum import Enum as PyEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import BigInteger, DATE, TIMESTAMP, ForeignKey, Index, String, Text
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


Index(
    "ix_skill_missions_user_status_due",
    SkillMission.user_id,
    SkillMission.status,
    SkillMission.due_date,
    SkillMission.id,
)
Index(
    "ix_skill_missions_user_created",
    SkillMission.user_id,
    SkillMission.created_at.desc(),
    SkillMission.id.desc(),
)


# ─── Pydantic Schemas ────────────────────────────────────────────────


class SkillMissionCreate(BaseModel):
    skill_id: int | None = None
    pivot_skill_gap_id: int | None = None
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=5000)
    status: MissionStatus = MissionStatus.todo
    due_date: date | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("title cannot be blank")
        return value


class SkillMissionUpdate(BaseModel):
    skill_id: int | None = None
    pivot_skill_gap_id: int | None = None
    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=5000)
    status: MissionStatus | None = None
    due_date: date | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = " ".join(value.split())
        if not value:
            raise ValueError("title cannot be blank")
        return value

    @model_validator(mode="after")
    def reject_null_required_fields(self) -> "SkillMissionUpdate":
        for field in ("title", "status"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


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


class MissionProgressResponse(BaseModel):
    total: int
    todo: int
    in_progress: int
    completed: int
    overdue: int
    completion_percentage: Decimal
