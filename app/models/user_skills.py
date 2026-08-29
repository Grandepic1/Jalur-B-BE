from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import BigInteger, CheckConstraint, DECIMAL, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.master import SkillRead


# ─── SQLAlchemy Model ────────────────────────────────────────────────


class UserSkill(Base):
    __tablename__ = "user_skills"
    __table_args__ = (
        UniqueConstraint("user_id", "skill_id", name="uq_user_skill"),
        CheckConstraint(
            "proficiency_level IS NULL OR proficiency_level BETWEEN 1 AND 5",
            name="ck_user_skills_proficiency",
        ),
        CheckConstraint(
            "years_experience IS NULL OR years_experience BETWEEN 0 AND 99.9",
            name="ck_user_skills_years_experience",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"))
    proficiency_level: Mapped[int | None] = mapped_column(Integer)  # 1-5
    years_experience: Mapped[Decimal | None] = mapped_column(DECIMAL(3, 1))

    user: Mapped["User"] = relationship()  # noqa: F821
    skill: Mapped["Skill"] = relationship()  # noqa: F821


# ─── Pydantic Schemas ────────────────────────────────────────────────


class UserSkillCreate(BaseModel):
    skill_id: int = Field(..., ge=1)
    proficiency_level: int | None = Field(None, ge=1, le=5)
    years_experience: Decimal | None = Field(None, ge=0, le=Decimal("99.9"))

    model_config = ConfigDict(extra="forbid")


class UserSkillUpdate(BaseModel):
    proficiency_level: int | None = Field(None, ge=1, le=5)
    years_experience: Decimal | None = Field(None, ge=0, le=Decimal("99.9"))

    model_config = ConfigDict(extra="forbid")


class UserSkillResponse(BaseModel):
    id: int
    user_id: int
    skill_id: int
    proficiency_level: int | None
    years_experience: Decimal | None

    model_config = ConfigDict(from_attributes=True)


class UserSkillDetailResponse(UserSkillResponse):
    skill: SkillRead
