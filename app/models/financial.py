from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import BigInteger, CHAR, DATETIME, DECIMAL, ForeignKey, Integer, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


# ─── SQLAlchemy Models ───────────────────────────────────────────────


class FinancialProfile(Base):
    __tablename__ = "financial_profiles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    available_savings: Mapped[Decimal] = mapped_column(DECIMAL(15, 2))
    monthly_essential_expenses: Mapped[Decimal] = mapped_column(DECIMAL(15, 2))
    monthly_debt_payment: Mapped[Decimal | None] = mapped_column(DECIMAL(15, 2))
    dependents: Mapped[int | None] = mapped_column(Integer)
    other_liquid_funds: Mapped[Decimal | None] = mapped_column(DECIMAL(15, 2))
    currency: Mapped[str] = mapped_column(CHAR(3), default="IDR")
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default="CURRENT_TIMESTAMP",
    )


class RunwayCalculation(Base):
    __tablename__ = "runway_calculations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    available_savings_snapshot: Mapped[Decimal] = mapped_column(DECIMAL(15, 2))
    essential_expenses_snapshot: Mapped[Decimal] = mapped_column(DECIMAL(15, 2))
    debt_payment_snapshot: Mapped[Decimal | None] = mapped_column(DECIMAL(15, 2))
    dependents_snapshot: Mapped[int | None] = mapped_column(Integer)
    liquid_funds_snapshot: Mapped[Decimal | None] = mapped_column(DECIMAL(15, 2))
    financial_runway_months: Mapped[Decimal] = mapped_column(DECIMAL(6, 2))
    calculated_at: Mapped[datetime] = mapped_column(
        DATETIME,
        server_default="CURRENT_TIMESTAMP",
    )


# ─── Pydantic Schemas ────────────────────────────────────────────────


class FinancialProfileCreate(BaseModel):
    available_savings: Decimal = Field(..., ge=0)
    monthly_essential_expenses: Decimal = Field(..., gt=0)
    monthly_debt_payment: Decimal | None = Field(None, ge=0)
    dependents: int | None = Field(None, ge=0)
    other_liquid_funds: Decimal | None = Field(None, ge=0)
    currency: str = Field("IDR", max_length=3)


class FinancialProfileResponse(BaseModel):
    id: int
    user_id: int
    available_savings: Decimal
    monthly_essential_expenses: Decimal
    monthly_debt_payment: Decimal | None
    dependents: int | None
    other_liquid_funds: Decimal | None
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
    calculated_at: datetime

    model_config = ConfigDict(from_attributes=True)
