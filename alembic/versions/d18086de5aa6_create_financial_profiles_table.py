"""create_financial_profiles_table

Revision ID: d18086de5aa6
Revises: d8a6675e4a62
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd18086de5aa6'
down_revision: Union[str, Sequence[str], None] = 'd8a6675e4a62'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'financial_profiles',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('available_savings', sa.DECIMAL(precision=15, scale=2), nullable=False),
        sa.Column('monthly_essential_expenses', sa.DECIMAL(precision=15, scale=2), nullable=False),
        sa.Column('monthly_debt_payment', sa.DECIMAL(precision=15, scale=2), nullable=True),
        sa.Column('dependents', sa.Integer(), nullable=True),
        sa.Column('other_liquid_funds', sa.DECIMAL(precision=15, scale=2), nullable=True),
        sa.Column('currency', sa.CHAR(length=3), server_default='IDR', nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('financial_profiles')
