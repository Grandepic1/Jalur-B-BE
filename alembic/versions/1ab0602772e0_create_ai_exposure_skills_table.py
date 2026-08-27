"""create_ai_exposure_skills_table

Revision ID: 1ab0602772e0
Revises: 4ac03ac94a6d
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1ab0602772e0'
down_revision: Union[str, Sequence[str], None] = '4ac03ac94a6d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'ai_exposure_skills',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('assessment_id', sa.BigInteger(), nullable=False),
        sa.Column('skill_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['assessment_id'], ['ai_exposure_assessments.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['skill_id'], ['skills.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('ai_exposure_skills')
