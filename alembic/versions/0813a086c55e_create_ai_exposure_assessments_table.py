"""create_ai_exposure_assessments_table

Revision ID: 0813a086c55e
Revises: 2b9aaa2a8a2a
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '0813a086c55e'
down_revision: Union[str, Sequence[str], None] = '2b9aaa2a8a2a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

exposure_level = postgresql.ENUM(
    'low', 'medium', 'high', name='exposurelevel', create_type=False
)


def upgrade() -> None:
    """Upgrade schema."""
    exposure_level.create(op.get_bind(), checkfirst=True)
    op.create_table(
        'ai_exposure_assessments',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('role_name', sa.String(length=100), nullable=False),
        sa.Column('responsibilities', sa.Text(), nullable=False),
        sa.Column('work_experience', sa.Text(), nullable=True),
        sa.Column('job_description', sa.Text(), nullable=True),
        sa.Column('job_description_url', sa.String(length=500), nullable=True),
        sa.Column('overall_exposure_level', exposure_level, nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('assessed_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('ai_exposure_assessments')
    exposure_level.drop(op.get_bind(), checkfirst=True)
