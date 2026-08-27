"""create_pivot_preferred_roles_table

Revision ID: 8bc492acf2db
Revises: 8f7c9f5340d7
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8bc492acf2db'
down_revision: Union[str, Sequence[str], None] = '8f7c9f5340d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'pivot_preferred_roles',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('analysis_id', sa.BigInteger(), nullable=False),
        sa.Column('role_name', sa.String(length=100), nullable=False),
        sa.ForeignKeyConstraint(['analysis_id'], ['pivot_analyses.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('pivot_preferred_roles')
