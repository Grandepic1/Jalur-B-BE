"""create_health_score_breakdowns_table

Revision ID: 23988b4ed48c
Revises: 4ff36541fef0
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '23988b4ed48c'
down_revision: Union[str, Sequence[str], None] = '4ff36541fef0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'health_score_breakdowns',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('assessment_id', sa.BigInteger(), nullable=False),
        sa.Column('dimension', sa.String(length=50), nullable=False),
        sa.Column('score', sa.DECIMAL(precision=5, scale=2), nullable=False),
        sa.Column('note', sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(['assessment_id'], ['health_assessments.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('health_score_breakdowns')
