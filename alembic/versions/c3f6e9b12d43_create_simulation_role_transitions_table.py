"""create simulation_role_transitions table

Revision ID: c3f6e9b12d43
Revises: b2e5d8a01c32
Create Date: 2026-10-14

One Transition Gap row per pivot role per simulation, so the simulation card can show
every option instead of collapsing them into a single worst-case preparation time.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3f6e9b12d43'
down_revision: Union[str, Sequence[str], None] = 'b2e5d8a01c32'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'simulation_role_transitions',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('simulation_id', sa.BigInteger(), nullable=False),
        sa.Column('role_name', sa.String(length=100), nullable=False),
        sa.Column('match_score', sa.DECIMAL(precision=5, scale=2), nullable=False),
        sa.Column(
            'preparation_time_months', sa.DECIMAL(precision=6, scale=2), nullable=False
        ),
        sa.Column(
            'search_time_months', sa.DECIMAL(precision=6, scale=2), nullable=False
        ),
        sa.Column('transition_months', sa.DECIMAL(precision=6, scale=2), nullable=False),
        sa.Column(
            'transition_gap_months', sa.DECIMAL(precision=8, scale=2), nullable=False
        ),
        sa.Column(
            'status',
            sa.Enum('surplus', 'deficit', name='transitiongapstatus'),
            nullable=False,
        ),
        sa.Column(
            'recommended_monthly_saving', sa.DECIMAL(precision=15, scale=2), nullable=False
        ),
        sa.Column(
            'months_saved_by_closing_one_gap',
            sa.DECIMAL(precision=6, scale=2),
            nullable=False,
        ),
        sa.Column('note', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ['simulation_id'], ['layoff_simulations.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'simulation_id', 'role_name', name='uq_simulation_role_transition'
        ),
    )
    op.create_index(
        op.f('ix_simulation_role_transitions_simulation_id'),
        'simulation_role_transitions',
        ['simulation_id'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_simulation_role_transitions_simulation_id'),
        table_name='simulation_role_transitions',
    )
    op.drop_table('simulation_role_transitions')
    op.execute('DROP TYPE IF EXISTS transitiongapstatus')
