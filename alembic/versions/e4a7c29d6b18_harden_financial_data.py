"""Harden financial data constraints and runway history lookup.

Revision ID: e4a7c29d6b18
Revises: d19e5a7c3f40
Create Date: 2026-08-29
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e4a7c29d6b18"
down_revision: Union[str, Sequence[str], None] = "d19e5a7c3f40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_financial_profiles_available_savings_nonnegative",
        "financial_profiles",
        "available_savings >= 0",
    )
    op.create_check_constraint(
        "ck_financial_profiles_expenses_positive",
        "financial_profiles",
        "monthly_essential_expenses > 0",
    )
    op.create_check_constraint(
        "ck_financial_profiles_debt_nonnegative",
        "financial_profiles",
        "monthly_debt_payment IS NULL OR monthly_debt_payment >= 0",
    )
    op.create_check_constraint(
        "ck_financial_profiles_dependents_nonnegative",
        "financial_profiles",
        "dependents IS NULL OR dependents >= 0",
    )
    op.create_check_constraint(
        "ck_financial_profiles_liquid_funds_nonnegative",
        "financial_profiles",
        "other_liquid_funds IS NULL OR other_liquid_funds >= 0",
    )
    op.create_check_constraint(
        "ck_financial_assets_amount_nonnegative",
        "financial_assets",
        "amount >= 0",
    )
    op.alter_column(
        "runway_calculations",
        "financial_runway_months",
        existing_type=sa.DECIMAL(precision=6, scale=2),
        type_=sa.DECIMAL(precision=12, scale=2),
        existing_nullable=False,
    )
    op.create_check_constraint(
        "ck_runway_calculations_months_nonnegative",
        "runway_calculations",
        "financial_runway_months >= 0",
    )
    op.create_index(
        "ix_runway_calculations_user_calculated",
        "runway_calculations",
        ["user_id", sa.text("calculated_at DESC"), sa.text("id DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_runway_calculations_user_calculated",
        table_name="runway_calculations",
    )
    op.drop_constraint(
        "ck_runway_calculations_months_nonnegative",
        "runway_calculations",
        type_="check",
    )
    op.alter_column(
        "runway_calculations",
        "financial_runway_months",
        existing_type=sa.DECIMAL(precision=12, scale=2),
        type_=sa.DECIMAL(precision=6, scale=2),
        existing_nullable=False,
    )
    op.drop_constraint(
        "ck_financial_assets_amount_nonnegative", "financial_assets", type_="check"
    )
    for name in (
        "ck_financial_profiles_liquid_funds_nonnegative",
        "ck_financial_profiles_dependents_nonnegative",
        "ck_financial_profiles_debt_nonnegative",
        "ck_financial_profiles_expenses_positive",
        "ck_financial_profiles_available_savings_nonnegative",
    ):
        op.drop_constraint(name, "financial_profiles", type_="check")
