"""create_ai_exposure_tools_table

Revision ID: d2f0a586fb1c
Revises: 1ab0602772e0
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd2f0a586fb1c'
down_revision: Union[str, Sequence[str], None] = '1ab0602772e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'ai_exposure_tools',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('assessment_id', sa.BigInteger(), nullable=False),
        sa.Column('tool_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['assessment_id'], ['ai_exposure_assessments.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tool_id'], ['tools.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('ai_exposure_tools')
