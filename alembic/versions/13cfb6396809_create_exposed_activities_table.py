"""create_exposed_activities_table

Revision ID: 13cfb6396809
Revises: 0813a086c55e
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '13cfb6396809'
down_revision: Union[str, Sequence[str], None] = '0813a086c55e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

exposure_level = postgresql.ENUM(
    'low', 'medium', 'high', name='exposurelevel', create_type=False
)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'exposed_activities',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('assessment_id', sa.BigInteger(), nullable=False),
        sa.Column('activity_name', sa.String(length=150), nullable=False),
        sa.Column('exposure_level', exposure_level, nullable=False),
        sa.Column('ai_impact_note', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['assessment_id'], ['ai_exposure_assessments.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('exposed_activities')
