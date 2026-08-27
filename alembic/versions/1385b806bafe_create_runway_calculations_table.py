"""create_runway_calculations_table

Revision ID: 1385b806bafe
Revises: d18086de5aa6
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1385b806bafe'
down_revision: Union[str, Sequence[str], None] = 'd18086de5aa6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'runway_calculations',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('available_savings_snapshot', sa.DECIMAL(precision=15, scale=2), nullable=False),
        sa.Column('essential_expenses_snapshot', sa.DECIMAL(precision=15, scale=2), nullable=False),
        sa.Column('debt_payment_snapshot', sa.DECIMAL(precision=15, scale=2), nullable=True),
        sa.Column('dependents_snapshot', sa.Integer(), nullable=True),
        sa.Column('liquid_funds_snapshot', sa.DECIMAL(precision=15, scale=2), nullable=True),
        sa.Column('financial_runway_months', sa.DECIMAL(precision=6, scale=2), nullable=False),
        sa.Column('calculated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('runway_calculations')
