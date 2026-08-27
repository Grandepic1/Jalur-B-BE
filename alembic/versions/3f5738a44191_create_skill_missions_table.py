"""create_skill_missions_table

Revision ID: 3f5738a44191
Revises: 1385b806bafe
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '3f5738a44191'
down_revision: Union[str, Sequence[str], None] = '1385b806bafe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

mission_status = postgresql.ENUM(
    'todo', 'in_progress', 'completed', name='missionstatus', create_type=False
)


def upgrade() -> None:
    """Upgrade schema."""
    mission_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        'skill_missions',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('skill_id', sa.Integer(), nullable=True),
        sa.Column('pivot_skill_gap_id', sa.BigInteger(), nullable=True),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', mission_status, server_default='todo', nullable=False),
        sa.Column('due_date', sa.DATE(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['pivot_skill_gap_id'], ['pivot_skill_gaps.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['skill_id'], ['skills.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('skill_missions')
    mission_status.drop(op.get_bind(), checkfirst=True)
