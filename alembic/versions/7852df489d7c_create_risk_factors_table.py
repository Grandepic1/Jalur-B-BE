"""create_risk_factors_table

Revision ID: 7852df489d7c
Revises: 73197d76d870
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '7852df489d7c'
down_revision: Union[str, Sequence[str], None] = '73197d76d870'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

risk_level = postgresql.ENUM(
    'low', 'medium', 'high', name='risklevel', create_type=False
)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'risk_factors',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('scan_id', sa.BigInteger(), nullable=False),
        sa.Column('source', sa.String(length=50), nullable=False),
        sa.Column('severity', risk_level, nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['scan_id'], ['risk_scans.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('risk_factors')
