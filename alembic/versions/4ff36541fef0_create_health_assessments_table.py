"""create_health_assessments_table

Revision ID: 4ff36541fef0
Revises: b60c5c5cecd8
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '4ff36541fef0'
down_revision: Union[str, Sequence[str], None] = 'b60c5c5cecd8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

health_level = postgresql.ENUM(
    'low', 'medium', 'high', name='healthlevel', create_type=False
)


def upgrade() -> None:
    """Upgrade schema."""
    health_level.create(op.get_bind(), checkfirst=True)
    op.create_table(
        'health_assessments',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('role_name', sa.String(length=100), nullable=False),
        sa.Column('industry_name', sa.String(length=100), nullable=False),
        sa.Column('work_duration_months', sa.Integer(), nullable=False),
        sa.Column('responsibilities', sa.Text(), nullable=False),
        sa.Column('achievements', sa.Text(), nullable=True),
        sa.Column('performance_feedback', sa.Text(), nullable=True),
        sa.Column('performance_feedback_url', sa.String(length=500), nullable=True),
        sa.Column('career_progression', sa.Text(), nullable=True),
        sa.Column('overall_score', sa.DECIMAL(precision=5, scale=2), nullable=False),
        sa.Column('level', health_level, nullable=False),
        sa.Column('assessed_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('health_assessments')
    health_level.drop(op.get_bind(), checkfirst=True)
