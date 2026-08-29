"""Add private evidence attachment object paths.

Revision ID: b91e4d7a2c60
Revises: a62f4c8d1e73
Create Date: 2026-08-29
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b91e4d7a2c60"
down_revision: Union[str, Sequence[str], None] = "a62f4c8d1e73"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "evidence_items",
        sa.Column("attachment_object_path", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("evidence_items", "attachment_object_path")
