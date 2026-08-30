from datetime import datetime
from decimal import Decimal
from enum import Enum as PyEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import (
    BigInteger,
    CHAR,
    DECIMAL,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    TIMESTAMP,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class FinancialAssetType(str, PyEnum):
    main_savings = "main_savings"
    emergency_fund = "emergency_fund"
    long_term_savings = "long_term_savings"
    investment = "investment"
    other = "other"


class LiquidityLevel(str, PyEnum):
    liquid = "liquid"
    requires_process = "requires_process"
    illiquid = "illiquid"


# ─── SQLAlchemy Models ───────────────────────────────────────────────


class FinancialProfile(Base):
    __tablename__ = "financial_profiles"
    __table_args__ = (
        CheckConstraint(
            "available_savings >= 0",
            name="ck_financial_profiles_available_savings_nonnegative",
        ),
        CheckConstraint(
            "monthly_essential_expenses > 0",
            name="ck_financial_profiles_expenses_positive",
        ),
        CheckConstraint(
            "monthly_debt_payment IS NULL OR monthly_debt_payment >= 0",
            name="ck_financial_profiles_debt_nonnegative",
        ),
        CheckConstraint(
            "dependents IS NULL OR dependents >= 0",
            name="ck_financial_profiles_dependents_nonnegative",
        ),
        CheckConstraint(
            "other_liquid_funds IS NULL OR other_liquid_funds >= 0",
            name="ck_financial_profiles_liquid_funds_nonnegative",
        ),
        CheckConstraint(
            "financial_readiness_score BETWEEN 0 AND 100",
            name="ck_financial_profiles_readiness_score",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    available_savings: Mapped[Decimal] = mapped_column(DECIMAL(15, 2))
    monthly_essential_expenses: Mapped[Decimal] = mapped_column(DECIMAL(15, 2))
    monthly_debt_payment: Mapped[Decimal | None] = mapped_column(DECIMAL(15, 2))
    dependents: Mapped[int | None] = mapped_column(Integer)
    other_liquid_funds: Mapped[Decimal | None] = mapped_column(DECIMAL(15, 2))
    financial_readiness_score: Mapped[Decimal] = mapped_column(
        DECIMAL(5, 2), server_default="0"
    )
    financial_readiness_updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    currency: Mapped[str] = mapped_column(CHAR(3), default="IDR")
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default="CURRENT_TIMESTAMP",
        onupdate=func.now(),
    )


class RunwayCalculation(Base):
    __tablename__ = "runway_calculations"
    __table_args__ = (
        CheckConstraint(
            "financial_runway_months >= 0",
            name="ck_runway_calculations_months_nonnegative",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    available_savings_snapshot: Mapped[Decimal] = mapped_column(DECIMAL(15, 2))
    essential_expenses_snapshot: Mapped[Decimal] = mapped_column(DECIMAL(15, 2))
    debt_payment_snapshot: Mapped[Decimal | None] = mapped_column(DECIMAL(15, 2))
    dependents_snapshot: Mapped[int | None] = mapped_column(Integer)
    liquid_funds_snapshot: Mapped[Decimal | None] = mapped_column(DECIMAL(15, 2))
    financial_runway_months: Mapped[Decimal] = mapped_column(DECIMAL(12, 2))
    total_assets_snapshot: Mapped[Decimal | None] = mapped_column(DECIMAL(15, 2))
    currency_snapshot: Mapped[str | None] = mapped_column(CHAR(3))
    calculated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        server_default="CURRENT_TIMESTAMP",
    )


class FinancialAsset(Base):
    __tablename__ = "financial_assets"
    __table_args__ = (
        CheckConstraint(
            "amount >= 0", name="ck_financial_assets_amount_nonnegative"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    amount: Mapped[Decimal] = mapped_column(DECIMAL(15, 2))
    asset_type: Mapped[FinancialAssetType] = mapped_column(SAEnum(FinancialAssetType))
    liquidity: Mapped[LiquidityLevel] = mapped_column(SAEnum(LiquidityLevel))
    note: Mapped[str | None] = mapped_column(Text)
    currency: Mapped[str] = mapped_column(CHAR(3), server_default="IDR")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship()  # noqa: F821


Index(
    "ix_runway_calculations_user_calculated",
    RunwayCalculation.user_id,
    RunwayCalculation.calculated_at.desc(),
    RunwayCalculation.id.desc(),
)


# ─── Pydantic Schemas ────────────────────────────────────────────────


class FinancialProfileCreate(BaseModel):
    """Monthly financial settings; asset totals are derived by the API."""

    monthly_essential_expenses: Decimal = Field(..., gt=0)
    monthly_debt_payment: Decimal = Field(Decimal("0"), ge=0)
    dependents: int = Field(0, ge=0)
    currency: str = Field("IDR", min_length=3, max_length=3)

    model_config = ConfigDict(extra="forbid")

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        value = value.upper()
        if not value.isalpha():
            raise ValueError("currency must be a three-letter ISO code")
        return value


class FinancialProfileResponse(BaseModel):
    id: int
    user_id: int
    monthly_essential_expenses: Decimal
    monthly_debt_payment: Decimal | None
    dependents: int | None
    financial_readiness_score: Decimal
    financial_readiness_updated_at: datetime
    currency: str
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RunwayCalculationResponse(BaseModel):
    id: int
    user_id: int
    available_savings_snapshot: Decimal
    essential_expenses_snapshot: Decimal
    debt_payment_snapshot: Decimal | None
    dependents_snapshot: int | None
    liquid_funds_snapshot: Decimal | None
    financial_runway_months: Decimal
    total_assets_snapshot: Decimal | None
    currency_snapshot: str | None
    calculated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FinancialAssetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    amount: Decimal = Field(..., gt=0)
    asset_type: FinancialAssetType
    liquidity: LiquidityLevel
    note: str | None = Field(None, max_length=2000)
    currency: str = Field("IDR", min_length=3, max_length=3)

    model_config = ConfigDict(extra="forbid")

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name cannot be blank")
        return value

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        value = value.upper()
        if not value.isalpha():
            raise ValueError("currency must be a three-letter ISO code")
        return value


class FinancialAssetUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    amount: Decimal | None = Field(None, gt=0)
    asset_type: FinancialAssetType | None = None
    liquidity: LiquidityLevel | None = None
    note: str | None = Field(None, max_length=2000)
    currency: str | None = Field(None, min_length=3, max_length=3)

    model_config = ConfigDict(extra="forbid")

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("name cannot be blank")
        return value

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.upper()
        if not value.isalpha():
            raise ValueError("currency must be a three-letter ISO code")
        return value

    @model_validator(mode="after")
    def reject_null_required_fields(self) -> "FinancialAssetUpdate":
        for field in ("name", "amount", "asset_type", "liquidity", "currency"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class FinancialAssetResponse(BaseModel):
    id: int
    user_id: int
    name: str
    amount: Decimal
    asset_type: FinancialAssetType
    liquidity: LiquidityLevel
    note: str | None
    currency: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FinancialRunwayPreview(BaseModel):
    total_assets: Decimal
    liquid_assets: Decimal
    monthly_burn: Decimal
    financial_runway_months: Decimal
    target_runway_months: Decimal
    runway_gap_months: Decimal
    currency: str


class FinancialSummaryResponse(BaseModel):
    profile: FinancialProfileResponse
    assets: list[FinancialAssetResponse]
    runway: FinancialRunwayPreview


class FinancialAssetBreakdown(BaseModel):
    total_assets: Decimal
    liquid_assets: Decimal
    by_type: dict[FinancialAssetType, Decimal]
    by_liquidity: dict[LiquidityLevel, Decimal]
    asset_count: int
    currency: str


class RunwayScenarioRequest(BaseModel):
    monthly_essential_expenses: Decimal = Field(..., gt=0)
    monthly_debt_payment: Decimal = Field(Decimal("0"), ge=0)
    liquid_assets: Decimal | None = Field(None, ge=0)

    model_config = ConfigDict(extra="forbid")


class RunwayTrendResponse(BaseModel):
    latest: RunwayCalculationResponse | None
    previous: RunwayCalculationResponse | None
    delta_months: Decimal | None
