"""Add current Financial Readiness to financial profiles.

Revision ID: f31a8c4d2e70
Revises: e91f2a6b3c40
Create Date: 2026-08-31
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f31a8c4d2e70"
down_revision: Union[str, Sequence[str], None] = "e91f2a6b3c40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "financial_profiles",
        sa.Column(
            "financial_readiness_score",
            sa.DECIMAL(5, 2),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "financial_profiles",
        sa.Column(
            "financial_readiness_updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_financial_profiles_readiness_score",
        "financial_profiles",
        "financial_readiness_score BETWEEN 0 AND 100",
    )
    op.execute(
        sa.text(
            """
            UPDATE financial_profiles AS profile
            SET financial_readiness_score = LEAST(
                100,
                ROUND(
                    COALESCE((
                        SELECT SUM(asset.amount)
                        FROM financial_assets AS asset
                        WHERE asset.user_id = profile.user_id
                          AND asset.liquidity = 'liquid'
                    ), 0)
                    / (
                        profile.monthly_essential_expenses
                        + COALESCE(profile.monthly_debt_payment, 0)
                    )
                    / 6
                    * 100,
                    2
                )
            ),
            financial_readiness_updated_at = CURRENT_TIMESTAMP
            """
        )
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_financial_profiles_readiness_score",
        "financial_profiles",
        type_="check",
    )
    op.drop_column("financial_profiles", "financial_readiness_updated_at")
    op.drop_column("financial_profiles", "financial_readiness_score")
