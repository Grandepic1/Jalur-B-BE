"""create_simulation_action_items_table

Revision ID: d3d4562fa0a5
Revises: 00a3e87e1b13
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd3d4562fa0a5'
down_revision: Union[str, Sequence[str], None] = '00a3e87e1b13'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

action_phase = postgresql.ENUM(
    'immediate', 'short_term', 'long_term', name='actionphase', create_type=False
)


def upgrade() -> None:
    """Upgrade schema."""
    action_phase.create(op.get_bind(), checkfirst=True)
    op.create_table(
        'simulation_action_items',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('simulation_id', sa.BigInteger(), nullable=False),
        sa.Column('step_order', sa.Integer(), nullable=False),
        sa.Column('phase', action_phase, nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('due_date', sa.DATE(), nullable=True),
        sa.Column('is_completed', sa.Boolean(), server_default=sa.text('FALSE'), nullable=False),
        sa.ForeignKeyConstraint(['simulation_id'], ['layoff_simulations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('simulation_action_items')
    action_phase.drop(op.get_bind(), checkfirst=True)
