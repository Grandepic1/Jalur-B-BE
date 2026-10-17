from datetime import date, datetime
from decimal import Decimal
from enum import Enum as PyEnum

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    BigInteger,
    BOOLEAN,
    DECIMAL,
    DATE,
    TIMESTAMP,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.entitlements import DEFAULT_SEARCH_TIME_MONTHS, ExitType


# ─── Enums ────────────────────────────────────────────────────────────


class ActionPhase(str, PyEnum):
    immediate = "immediate"
    short_term = "short_term"
    long_term = "long_term"


class LayoffScenario(str, PyEnum):
    """Urgency of the assumed exit. Derived from ``ExitType``; no longer user-chosen.

    The old API let the user pick tomorrow / one month / three months, which only shifted
    action-item due dates and left every headline number identical. The exit ground now
    drives the numbers and this enum only schedules the action plan.
    """

    tomorrow = "tomorrow"
    one_month = "one_month"
    three_months = "three_months"


class TransitionGapStatus(str, PyEnum):
    surplus = "surplus"
    deficit = "deficit"


# ─── SQLAlchemy Models ───────────────────────────────────────────────


class LayoffSimulation(Base):
    __tablename__ = "layoff_simulations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    scenario: Mapped[LayoffScenario] = mapped_column(
        SAEnum(LayoffScenario), server_default=LayoffScenario.tomorrow.value
    )
    best_pivot_analysis_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("pivot_analyses.id", ondelete="SET NULL")
    )
    career_readiness_score: Mapped[Decimal | None] = mapped_column(DECIMAL(5, 2))
    financial_readiness_score: Mapped[Decimal | None] = mapped_column(DECIMAL(5, 2))
    skill_relevance_score: Mapped[Decimal | None] = mapped_column(DECIMAL(5, 2))
    job_mobility_score: Mapped[Decimal | None] = mapped_column(DECIMAL(5, 2))
    overall_resilience_score: Mapped[Decimal | None] = mapped_column(DECIMAL(5, 2))
    financial_runway_months: Mapped[Decimal | None] = mapped_column(DECIMAL(6, 2))
    target_runway_months: Mapped[Decimal | None] = mapped_column(DECIMAL(6, 2))
    financial_gap: Mapped[Decimal | None] = mapped_column(DECIMAL(15, 2))
    estimated_preparation_time_months: Mapped[int | None] = mapped_column(Integer)
    # Nullable so simulations created before the exit-aware change stay readable.
    exit_type: Mapped[ExitType | None] = mapped_column(SAEnum(ExitType))
    regulation_version: Mapped[str | None] = mapped_column(String(64))
    search_time_months: Mapped[Decimal | None] = mapped_column(DECIMAL(6, 2))
    transition_role_name: Mapped[str | None] = mapped_column(String(100))
    transition_gap_months: Mapped[Decimal | None] = mapped_column(DECIMAL(8, 2))
    transition_gap_status: Mapped[str | None] = mapped_column(String(20))
    evidence_count: Mapped[int] = mapped_column(Integer, server_default="0")
    summary: Mapped[str | None] = mapped_column(Text)
    provider_model: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(50))
    scoring_version: Mapped[str | None] = mapped_column(String(50))
    input_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    simulated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        server_default="CURRENT_TIMESTAMP",
    )

    action_items: Mapped[list["SimulationActionItem"]] = relationship(
        back_populates="simulation", cascade="all, delete-orphan"
    )
    role_transitions: Mapped[list["SimulationRoleTransition"]] = relationship(
        back_populates="simulation", cascade="all, delete-orphan"
    )
    best_pivot_analysis: Mapped["PivotAnalysis | None"] = relationship()  # noqa: F821


Index(
    "ix_layoff_simulations_user_simulated",
    LayoffSimulation.user_id,
    LayoffSimulation.simulated_at.desc(),
    LayoffSimulation.id.desc(),
)


class SimulationRoleTransition(Base):
    """One Transition Gap row per pivot role, so the card can show every option."""

    __tablename__ = "simulation_role_transitions"
    __table_args__ = (
        UniqueConstraint(
            "simulation_id", "role_name", name="uq_simulation_role_transition"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    simulation_id: Mapped[int] = mapped_column(
        ForeignKey("layoff_simulations.id", ondelete="CASCADE"), index=True
    )
    role_name: Mapped[str] = mapped_column(String(100))
    match_score: Mapped[Decimal] = mapped_column(DECIMAL(5, 2))
    preparation_time_months: Mapped[Decimal] = mapped_column(DECIMAL(6, 2))
    search_time_months: Mapped[Decimal] = mapped_column(DECIMAL(6, 2))
    transition_months: Mapped[Decimal] = mapped_column(DECIMAL(6, 2))
    transition_gap_months: Mapped[Decimal] = mapped_column(DECIMAL(8, 2))
    status: Mapped[TransitionGapStatus] = mapped_column(SAEnum(TransitionGapStatus))
    recommended_monthly_saving: Mapped[Decimal] = mapped_column(DECIMAL(15, 2))
    months_saved_by_closing_one_gap: Mapped[Decimal] = mapped_column(DECIMAL(6, 2))
    note: Mapped[str | None] = mapped_column(Text)

    simulation: Mapped["LayoffSimulation"] = relationship(
        back_populates="role_transitions"
    )


class SimulationActionItem(Base):
    __tablename__ = "simulation_action_items"
    __table_args__ = (
        UniqueConstraint(
            "simulation_id", "step_order", name="uq_simulation_action_order"
        ),
    )

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
    scenario: LayoffScenario
    best_pivot_analysis_id: int | None
    career_readiness_score: Decimal | None
    financial_readiness_score: Decimal | None
    skill_relevance_score: Decimal | None
    job_mobility_score: Decimal | None
    overall_resilience_score: Decimal | None
    financial_runway_months: Decimal | None
    financial_gap: Decimal | None
    estimated_preparation_time_months: int | None
    evidence_count: int
    summary: str | None
    simulated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LayoffSimulationWithActionItems(LayoffSimulationResponse):
    action_items: list[SimulationActionItemResponse]


class SimulationRoleTransitionResponse(BaseModel):
    id: int
    simulation_id: int
    role_name: str
    match_score: Decimal
    preparation_time_months: Decimal
    search_time_months: Decimal
    transition_months: Decimal
    transition_gap_months: Decimal
    status: TransitionGapStatus
    recommended_monthly_saving: Decimal
    months_saved_by_closing_one_gap: Decimal
    note: str | None

    model_config = ConfigDict(from_attributes=True)


class LayoffSimulationCreate(BaseModel):
    """Replaces the old time-based scenario: the exit ground is what changes the numbers."""

    exit_type: ExitType = ExitType.efficiency_due_to_loss
    search_time_months: Decimal = Field(DEFAULT_SEARCH_TIME_MONTHS, ge=0, le=24)

    model_config = ConfigDict(extra="forbid")
