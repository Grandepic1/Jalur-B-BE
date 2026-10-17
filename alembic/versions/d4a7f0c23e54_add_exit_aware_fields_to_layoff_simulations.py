"""add exit aware fields to layoff_simulations

Revision ID: d4a7f0c23e54
Revises: c3f6e9b12d43
Create Date: 2026-10-14

Records which exit ground a simulation assumed, the regulation version used, the visible
search-time assumption, and the Transition Gap that the simulation now centres on.

All columns are nullable so simulations created before this change stay readable.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd4a7f0c23e54'
down_revision: Union[str, Sequence[str], None] = 'c3f6e9b12d43'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Created by the employment_terms migration; reuse without re-creating.
EXIT_TYPE = postgresql.ENUM(
    'efficiency_prevent_loss',
    'efficiency_due_to_loss',
    'closure_not_loss',
    'bankruptcy',
    'pkwt_ends_on_schedule',
    'resign',
    name='exittype',
    create_type=False,
)


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('layoff_simulations', sa.Column('exit_type', EXIT_TYPE, nullable=True))
    op.add_column(
        'layoff_simulations',
        sa.Column('regulation_version', sa.String(length=64), nullable=True),
    )
    op.add_column(
        'layoff_simulations',
        sa.Column('search_time_months', sa.DECIMAL(precision=6, scale=2), nullable=True),
    )
    op.add_column(
        'layoff_simulations',
        sa.Column('transition_role_name', sa.String(length=100), nullable=True),
    )
    op.add_column(
        'layoff_simulations',
        sa.Column(
            'transition_gap_months', sa.DECIMAL(precision=8, scale=2), nullable=True
        ),
    )
    op.add_column(
        'layoff_simulations',
        sa.Column('transition_gap_status', sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('layoff_simulations', 'transition_gap_status')
    op.drop_column('layoff_simulations', 'transition_gap_months')
    op.drop_column('layoff_simulations', 'transition_role_name')
    op.drop_column('layoff_simulations', 'search_time_months')
    op.drop_column('layoff_simulations', 'regulation_version')
    op.drop_column('layoff_simulations', 'exit_type')
