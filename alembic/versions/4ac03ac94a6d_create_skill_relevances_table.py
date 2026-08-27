"""create_skill_relevances_table

Revision ID: 4ac03ac94a6d
Revises: 13cfb6396809
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '4ac03ac94a6d'
down_revision: Union[str, Sequence[str], None] = '13cfb6396809'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

skill_relevance_status = postgresql.ENUM(
    'declining', 'stable', 'rising',
    name='skillrelevancestatus',
    create_type=False,
)


def upgrade() -> None:
    """Upgrade schema."""
    skill_relevance_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        'skill_relevances',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('assessment_id', sa.BigInteger(), nullable=False),
        sa.Column('skill_id', sa.Integer(), nullable=False),
        sa.Column('status', skill_relevance_status, nullable=False),
        sa.Column('recommendation', sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(['assessment_id'], ['ai_exposure_assessments.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['skill_id'], ['skills.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('skill_relevances')
    skill_relevance_status.drop(op.get_bind(), checkfirst=True)
