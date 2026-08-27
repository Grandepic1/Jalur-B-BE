"""create_pivot_skill_gaps_table

Revision ID: 677159a38339
Revises: 8bc492acf2db
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '677159a38339'
down_revision: Union[str, Sequence[str], None] = '8bc492acf2db'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

gap_level = postgresql.ENUM(
    'small', 'medium', 'large', name='gaplevel', create_type=False
)


def upgrade() -> None:
    """Upgrade schema."""
    gap_level.create(op.get_bind(), checkfirst=True)
    op.create_table(
        'pivot_skill_gaps',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('analysis_id', sa.BigInteger(), nullable=False),
        sa.Column('skill_id', sa.Integer(), nullable=False),
        sa.Column('current_level', sa.Integer(), nullable=True),
        sa.Column('required_level', sa.Integer(), nullable=False),
        sa.Column('gap_level', gap_level, nullable=False),
        sa.Column('recommended_action', sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(['analysis_id'], ['pivot_analyses.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['skill_id'], ['skills.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('pivot_skill_gaps')
    gap_level.drop(op.get_bind(), checkfirst=True)
