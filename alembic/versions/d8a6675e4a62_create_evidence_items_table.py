"""create_evidence_items_table

Revision ID: d8a6675e4a62
Revises: 677159a38339
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd8a6675e4a62'
down_revision: Union[str, Sequence[str], None] = '677159a38339'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

evidence_type = postgresql.ENUM(
    'project',
    'achievement',
    'feedback',
    'certificate',
    'award',
    'training',
    'other',
    name='evidencetype',
    create_type=False,
)


def upgrade() -> None:
    """Upgrade schema."""
    evidence_type.create(op.get_bind(), checkfirst=True)
    op.create_table(
        'evidence_items',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('evidence_type', evidence_type, nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('user_role', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('impact', sa.Text(), nullable=False),
        sa.Column('evidence_date', sa.DATE(), nullable=True),
        sa.Column('attachment_url', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('evidence_items')
    evidence_type.drop(op.get_bind(), checkfirst=True)
