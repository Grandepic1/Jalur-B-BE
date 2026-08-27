"""create_risk_scan_skills_table

Revision ID: 2b9aaa2a8a2a
Revises: 7852df489d7c
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2b9aaa2a8a2a'
down_revision: Union[str, Sequence[str], None] = '7852df489d7c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'risk_scan_skills',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('scan_id', sa.BigInteger(), nullable=False),
        sa.Column('skill_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['scan_id'], ['risk_scans.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['skill_id'], ['skills.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('risk_scan_skills')
