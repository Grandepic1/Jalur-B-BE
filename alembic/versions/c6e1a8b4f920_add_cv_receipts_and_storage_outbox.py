"""Add CV confirmation receipts and storage deletion outbox.

Revision ID: c6e1a8b4f920
Revises: b5d9f7c2a841
Create Date: 2026-09-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c6e1a8b4f920"
down_revision: Union[str, Sequence[str], None] = "b5d9f7c2a841"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cv_confirmation_receipts",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("preview_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "confirmed_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "preview_id", name="uq_cv_confirmation_receipt"
        ),
    )
    op.create_index(
        "ix_cv_confirmation_receipts_user_id",
        "cv_confirmation_receipts",
        ["user_id"],
        unique=False,
    )
    op.create_table(
        "storage_deletion_jobs",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("object_path", sa.String(length=500), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_path"),
    )


def downgrade() -> None:
    op.drop_table("storage_deletion_jobs")
    op.drop_index(
        "ix_cv_confirmation_receipts_user_id",
        table_name="cv_confirmation_receipts",
    )
    op.drop_table("cv_confirmation_receipts")
