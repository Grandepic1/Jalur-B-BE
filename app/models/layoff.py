from datetime import date, datetime
from decimal import Decimal
from enum import Enum as PyEnum

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import BigInteger, BOOLEAN, DATETIME, DECIMAL, DATE, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# ─── Enums ────────────────────────────────────────────────────────────


class ActionPhase(str, PyEnum):
    immediate = "immediate"
    short_term = "short_term"
    long_term = "long_term"


# ─── SQLAlchemy Models ───────────────────────────────────────────────


class LayoffSimulation(Base):
    __tablename__ = "layoff_simulations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    best_pivot_analysis_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("pivot_analyses.id", ondelete="SET NULL")
    )
    career_readiness_score: Mapped[Decimal | None] = mapped_column(DECIMAL(5, 2))
    financial_readiness_score: Mapped[Decimal | None] = mapped_column(DECIMAL(5, 2))
    overall_resilience_score: Mapped[Decimal | None] = mapped_column(DECIMAL(5, 2))
    financial_runway_months: Mapped[Decimal | None] = mapped_column(DECIMAL(6, 2))
    financial_gap: Mapped[Decimal | None] = mapped_column(DECIMAL(15, 2))
    estimated_preparation_time_months: Mapped[int | None] = mapped_column(Integer)
    summary: Mapped[str | None] = mapped_column(Text)
    simulated_at: Mapped[datetime] = mapped_column(
        DATETIME,
        server_default="CURRENT_TIMESTAMP",
    )

    action_items: Mapped[list["SimulationActionItem"]] = relationship(
        back_populates="simulation", cascade="all, delete-orphan"
    )
    best_pivot_analysis: Mapped["PivotAnalysis | None"] = relationship()  # noqa: F821


class SimulationActionItem(Base):
    __tablename__ = "simulation_action_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    simulation_id: Mapped[int] = mapped_column(
        ForeignKey("layoff_simulations.id", ondelete="CASCADE")
    )
    step_order: Mapped[int] = mapped_column(Integer)
    phase: Mapped[ActionPhase] = mapped_column(SAEnum(ActionPhase))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    due_date: Mapped[date | None] = mapped_column(DATE)
    is_completed: Mapped[bool] = mapped_column(BOOLEAN, default=False)

    simulation: Mapped["LayoffSimulation"] = relationship(back_populates="action_items")


# ─── Pydantic Schemas ────────────────────────────────────────────────


class SimulationActionItemResponse(BaseModel):
    id: int
    simulation_id: int
    step_order: int
    phase: ActionPhase
    title: str
    description: str | None
    due_date: date | None
    is_completed: bool

    model_config = ConfigDict(from_attributes=True)


class LayoffSimulationResponse(BaseModel):
    id: int
    user_id: int
    best_pivot_analysis_id: int | None
    career_readiness_score: Decimal | None
    financial_readiness_score: Decimal | None
    overall_resilience_score: Decimal | None
    financial_runway_months: Decimal | None
    financial_gap: Decimal | None
    estimated_preparation_time_months: int | None
    summary: str | None
    simulated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LayoffSimulationWithActionItems(LayoffSimulationResponse):
    action_items: list[SimulationActionItemResponse]
