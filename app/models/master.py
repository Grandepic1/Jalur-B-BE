from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import DECIMAL, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# ─── SQLAlchemy Models ───────────────────────────────────────────────


class Industry(Base):
    __tablename__ = "industries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)

    roles: Mapped[list["Role"]] = relationship(back_populates="industry", cascade="all, delete-orphan")


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    industry_id: Mapped[int] = mapped_column(ForeignKey("industries.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    ai_automation_risk_score: Mapped[Decimal | None] = mapped_column(DECIMAL(5, 2))

    industry: Mapped["Industry"] = relationship(back_populates="roles")


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    category: Mapped[str | None] = mapped_column(String(50))  # technical | soft | domain
    market_trend: Mapped[str] = mapped_column(String(20), default="stable")  # declining | stable | rising


class Tool(Base):
    __tablename__ = "tools"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)


# ─── Pydantic Schemas ────────────────────────────────────────────────


class IndustryRead(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class RoleRead(BaseModel):
    id: int
    industry_id: int
    name: str
    description: str | None
    ai_automation_risk_score: Decimal | None

    model_config = ConfigDict(from_attributes=True)


class RoleReadWithIndustry(RoleRead):
    industry: IndustryRead


class SkillRead(BaseModel):
    id: int
    name: str
    category: str | None
    market_trend: str

    model_config = ConfigDict(from_attributes=True)


class ToolRead(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)
