"""create_layoff_simulations_table

Revision ID: 00a3e87e1b13
Revises: 3f5738a44191
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '00a3e87e1b13'
down_revision: Union[str, Sequence[str], None] = '3f5738a44191'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'layoff_simulations',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('best_pivot_analysis_id', sa.BigInteger(), nullable=True),
        sa.Column('career_readiness_score', sa.DECIMAL(precision=5, scale=2), nullable=True),
        sa.Column('financial_readiness_score', sa.DECIMAL(precision=5, scale=2), nullable=True),
        sa.Column('overall_resilience_score', sa.DECIMAL(precision=5, scale=2), nullable=True),
        sa.Column('financial_runway_months', sa.DECIMAL(precision=6, scale=2), nullable=True),
        sa.Column('financial_gap', sa.DECIMAL(precision=15, scale=2), nullable=True),
        sa.Column('estimated_preparation_time_months', sa.Integer(), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('simulated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['best_pivot_analysis_id'], ['pivot_analyses.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('layoff_simulations')
