"""create_risk_scans_table

Revision ID: 73197d76d870
Revises: 23988b4ed48c
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '73197d76d870'
down_revision: Union[str, Sequence[str], None] = '23988b4ed48c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

risk_level = postgresql.ENUM(
    'low', 'medium', 'high', name='risklevel', create_type=False
)


def upgrade() -> None:
    """Upgrade schema."""
    risk_level.create(op.get_bind(), checkfirst=True)
    op.create_table(
        'risk_scans',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('role_name', sa.String(length=100), nullable=False),
        sa.Column('industry_name', sa.String(length=100), nullable=False),
        sa.Column('responsibilities', sa.Text(), nullable=False),
        sa.Column('work_changes', sa.Text(), nullable=True),
        sa.Column('job_description', sa.Text(), nullable=True),
        sa.Column('job_description_url', sa.String(length=500), nullable=True),
        sa.Column('overall_risk_level', risk_level, nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('scanned_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('risk_scans')
    risk_level.drop(op.get_bind(), checkfirst=True)
