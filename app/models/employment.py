"""Employment terms and exit-aware runway.

``employment_terms`` is a one-to-one satellite of ``users``, kept separate from
``financial_profiles`` because wage, contract type, and social-security participation are
employment facts governed by labour law, while ``financial_profiles`` holds the user's
budget. Keeping them apart also lets each exit-runway result carry its own
``regulation_version`` without overloading the financial row.
"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import (
    BigInteger,
    BOOLEAN,
    CheckConstraint,
    DATE,
    DECIMAL,
    ForeignKey,
    Index,
    Integer,
    String,
    TIMESTAMP,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.entitlements import (
    DEFAULT_SEARCH_TIME_MONTHS,
    EmploymentType,
    ExitType,
)


# ─── SQLAlchemy Models ───────────────────────────────────────────────


class EmploymentTerms(Base):
    """How the user is employed and on what terms. Drives statutory entitlements."""

    __tablename__ = "employment_terms"
    __table_args__ = (
        CheckConstraint(
            "monthly_wage_base > 0",
            name="ck_employment_terms_wage_positive",
        ),
        CheckConstraint(
            "tenure_months IS NULL OR tenure_months >= 0",
            name="ck_employment_terms_tenure_nonnegative",
        ),
        CheckConstraint(
            "bpjs_contribution_months_last_24 >= 0",
            name="ck_employment_terms_bpjs_window_nonnegative",
        ),
        CheckConstraint(
            "bpjs_consecutive_months >= 0",
            name="ck_employment_terms_bpjs_consecutive_nonnegative",
        ),
        CheckConstraint(
            "jht_balance IS NULL OR jht_balance >= 0",
            name="ck_employment_terms_jht_nonnegative",
        ),
        CheckConstraint(
            "unused_leave_days IS NULL OR unused_leave_days >= 0",
            name="ck_employment_terms_leave_nonnegative",
        ),
        CheckConstraint(
            "age_years IS NULL OR age_years BETWEEN 15 AND 100",
            name="ck_employment_terms_age_range",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    # Base wage plus fixed allowances: the base for pesangon, UPMK, JKP, and PKWT
    # compensation.
    monthly_wage_base: Mapped[Decimal] = mapped_column(DECIMAL(15, 2))
    employment_type: Mapped[EmploymentType] = mapped_column(
        SAEnum(EmploymentType), server_default=EmploymentType.pkwtt.value
    )
    # The exit ground assumed when Financial Readiness is recalculated outside an explicit
    # exit-runway request. Visible and user-editable so the assumption is never hidden.
    assumed_exit_type: Mapped[ExitType] = mapped_column(
        SAEnum(ExitType), server_default=ExitType.efficiency_due_to_loss.value
    )
    contract_start_date: Mapped[date | None] = mapped_column(DATE)
    contract_end_date: Mapped[date | None] = mapped_column(DATE)
    # Falls back to user_profiles.work_duration_months when left empty.
    tenure_months: Mapped[int | None] = mapped_column(Integer)
    bpjs_tk_active: Mapped[bool] = mapped_column(BOOLEAN, server_default="false")
    jkn_active: Mapped[bool] = mapped_column(BOOLEAN, server_default="false")
    bpjs_contribution_months_last_24: Mapped[int] = mapped_column(
        Integer, server_default="0"
    )
    bpjs_consecutive_months: Mapped[int] = mapped_column(Integer, server_default="0")
    age_years: Mapped[int | None] = mapped_column(Integer)
    jht_balance: Mapped[Decimal | None] = mapped_column(DECIMAL(15, 2))
    unused_leave_days: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship()  # noqa: F821


class ExitRunwayCalculation(Base):
    """Immutable snapshot of one exit-aware runway calculation."""

    __tablename__ = "exit_runway_calculations"
    __table_args__ = (
        CheckConstraint(
            "savings_only_runway_months >= 0",
            name="ck_exit_runway_savings_months_nonnegative",
        ),
        CheckConstraint(
            "with_jkp_runway_months >= 0",
            name="ck_exit_runway_headline_months_nonnegative",
        ),
        CheckConstraint(
            "day_of_layoff IS NOT NULL",
            name="ck_exit_runway_effective_date_present",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    exit_type: Mapped[ExitType] = mapped_column(SAEnum(ExitType))
    employment_type: Mapped[EmploymentType] = mapped_column(SAEnum(EmploymentType))
    # Stored on every result so a change in the law never rewrites history.
    regulation_version: Mapped[str] = mapped_column(String(64))

    monthly_wage_base_snapshot: Mapped[Decimal] = mapped_column(DECIMAL(15, 2))
    tenure_months_snapshot: Mapped[int] = mapped_column(Integer)
    essential_expenses_snapshot: Mapped[Decimal] = mapped_column(DECIMAL(15, 2))
    debt_payment_snapshot: Mapped[Decimal | None] = mapped_column(DECIMAL(15, 2))
    liquid_assets_snapshot: Mapped[Decimal] = mapped_column(DECIMAL(15, 2))
    jht_balance_snapshot: Mapped[Decimal | None] = mapped_column(DECIMAL(15, 2))
    currency_snapshot: Mapped[str] = mapped_column(String(3))

    pesangon_months: Mapped[Decimal] = mapped_column(DECIMAL(6, 2))
    upmk_months: Mapped[Decimal] = mapped_column(DECIMAL(6, 2))
    gross_lump_sum: Mapped[Decimal] = mapped_column(DECIMAL(15, 2))
    severance_tax: Mapped[Decimal] = mapped_column(DECIMAL(15, 2))
    net_lump_sum: Mapped[Decimal] = mapped_column(DECIMAL(15, 2))
    normative_collectable: Mapped[bool] = mapped_column(BOOLEAN, server_default="true")
    liquid_normative: Mapped[Decimal] = mapped_column(DECIMAL(15, 2))

    jkp_eligible: Mapped[bool] = mapped_column(BOOLEAN, server_default="false")
    jkp_monthly_benefit: Mapped[Decimal] = mapped_column(DECIMAL(15, 2))
    jkp_months: Mapped[int] = mapped_column(Integer, server_default="0")
    jkp_ineligible_reasons: Mapped[list | None] = mapped_column(JSONB)

    savings_only_runway_months: Mapped[Decimal] = mapped_column(DECIMAL(12, 2))
    with_normative_rights_runway_months: Mapped[Decimal] = mapped_column(DECIMAL(12, 2))
    with_jkp_runway_months: Mapped[Decimal] = mapped_column(DECIMAL(12, 2))
    with_jht_runway_months: Mapped[Decimal] = mapped_column(DECIMAL(12, 2))
    day_of_layoff: Mapped[date] = mapped_column(DATE)
    money_runs_out_on: Mapped[date | None] = mapped_column(DATE)
    jkp_claim_deadline: Mapped[date | None] = mapped_column(DATE)
    cost_of_living_warning: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[list | None] = mapped_column(JSONB)
    calculated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )


Index(
    "ix_exit_runway_calculations_user_calculated",
    ExitRunwayCalculation.user_id,
    ExitRunwayCalculation.calculated_at.desc(),
    ExitRunwayCalculation.id.desc(),
)


# ─── Pydantic Schemas ────────────────────────────────────────────────


class EmploymentTermsUpsert(BaseModel):
    """Full replacement of the user's employment terms."""

    monthly_wage_base: Decimal = Field(..., gt=0)
    employment_type: EmploymentType = EmploymentType.pkwtt
    assumed_exit_type: ExitType = ExitType.efficiency_due_to_loss
    contract_start_date: date | None = None
    contract_end_date: date | None = None
    tenure_months: int | None = Field(None, ge=0, le=960)
    bpjs_tk_active: bool = False
    jkn_active: bool = False
    bpjs_contribution_months_last_24: int = Field(0, ge=0, le=24)
    bpjs_consecutive_months: int = Field(0, ge=0, le=600)
    age_years: int | None = Field(None, ge=15, le=100)
    jht_balance: Decimal | None = Field(None, ge=0)
    unused_leave_days: int | None = Field(None, ge=0, le=365)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def require_pkwt_dates(self) -> "EmploymentTermsUpsert":
        if self.employment_type is EmploymentType.pkwt:
            if self.contract_start_date is None or self.contract_end_date is None:
                raise ValueError(
                    "contract_start_date and contract_end_date are required for PKWT"
                )
            if self.contract_end_date < self.contract_start_date:
                raise ValueError("contract_end_date cannot precede contract_start_date")
        return self


class EmploymentTermsResponse(BaseModel):
    id: int
    user_id: int
    monthly_wage_base: Decimal
    employment_type: EmploymentType
    assumed_exit_type: ExitType
    contract_start_date: date | None
    contract_end_date: date | None
    tenure_months: int | None
    bpjs_tk_active: bool
    jkn_active: bool
    bpjs_contribution_months_last_24: int
    bpjs_consecutive_months: int
    age_years: int | None
    jht_balance: Decimal | None
    unused_leave_days: int | None
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExitRunwayRequest(BaseModel):
    """Inputs for one exit-aware runway calculation."""

    exit_type: ExitType
    # Overrides the bankruptcy conservatism default. ``None`` keeps the default.
    normative_rights_collectable: bool | None = None
    # Search time is an explicit assumption, not sourced data, so it is always visible
    # and always adjustable by the user.
    search_time_months: Decimal = Field(
        DEFAULT_SEARCH_TIME_MONTHS, ge=0, le=24
    )
    day_of_layoff: date | None = None
    # How long the user has to save before the money is needed, used only to spread a
    # remaining Transition Gap into a monthly saving target. Acts as the fallback when
    # ``day_of_layoff`` is missing or not in the future, so the target never divides the
    # whole deficit by the runway.
    horizon_months: Decimal = Field(Decimal("12"), gt=0, le=60)

    model_config = ConfigDict(extra="forbid")


class RunwayLayerResponse(BaseModel):
    key: str
    label: str
    runway_months: Decimal
    liquid_funds: Decimal
    monthly_benefit: Decimal
    uses_retirement_savings: bool = False


class TransitionGapResponse(BaseModel):
    """Runway minus the time needed to prepare and land a new role."""

    role_name: str
    match_score: Decimal
    preparation_time_months: Decimal
    search_time_months: Decimal
    transition_months: Decimal
    transition_gap_months: Decimal
    status: str
    recommended_monthly_saving: Decimal
    months_saved_by_closing_one_gap: Decimal
    note: str


class ExitRunwayResponse(BaseModel):
    exit_type: ExitType
    regulation_version: str
    employment_type: EmploymentType
    currency: str
    monthly_wage_base: Decimal
    tenure_months: int
    monthly_burn: Decimal

    pesangon_months: Decimal
    upmk_months: Decimal
    gross_lump_sum: Decimal
    severance_tax: Decimal
    net_lump_sum: Decimal
    normative_collectable: bool
    liquid_normative: Decimal

    jkp_eligible: bool
    jkp_monthly_benefit: Decimal
    jkp_months: int
    jkp_total_benefit: Decimal
    jkp_ineligible_reasons: list[str]

    # Headline runway: normative rights plus JKP, excluding retirement savings.
    runway_months: Decimal
    layers: list[RunwayLayerResponse]
    day_of_layoff: date
    money_runs_out_on: date | None
    jkp_claim_deadline: date | None

    cost_of_living_warning: str | None
    poverty_line_version: str
    notes: list[str]
    role_transitions: list[TransitionGapResponse] = Field(default_factory=list)
    calculated_at: datetime | None = None
