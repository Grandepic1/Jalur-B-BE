"""create_pivot_analyses_table

Revision ID: 8f7c9f5340d7
Revises: d2f0a586fb1c
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8f7c9f5340d7'
down_revision: Union[str, Sequence[str], None] = 'd2f0a586fb1c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'pivot_analyses',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('current_role_name', sa.String(length=100), nullable=False),
        sa.Column('industry_name', sa.String(length=100), nullable=False),
        sa.Column('work_experience', sa.Text(), nullable=False),
        sa.Column('achievements', sa.Text(), nullable=True),
        sa.Column('work_preferences', sa.Text(), nullable=True),
        sa.Column('target_role_id', sa.Integer(), nullable=True),
        sa.Column('match_score', sa.DECIMAL(precision=5, scale=2), nullable=False),
        sa.Column('shared_skills_count', sa.Integer(), nullable=True),
        sa.Column('missing_skills_count', sa.Integer(), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('analyzed_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['target_role_id'], ['roles.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('pivot_analyses')
