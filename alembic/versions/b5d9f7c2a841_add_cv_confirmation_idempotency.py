"""Add CV confirmation idempotency key.

Revision ID: b5d9f7c2a841
Revises: a4c8e2f1d730
Create Date: 2026-09-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b5d9f7c2a841"
down_revision: Union[str, Sequence[str], None] = "a4c8e2f1d730"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_cvs",
        sa.Column("source_preview_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_unique_constraint(
        "uq_user_cvs_source_preview_id", "user_cvs", ["source_preview_id"]
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_user_cvs_source_preview_id", "user_cvs", type_="unique"
    )
    op.drop_column("user_cvs", "source_preview_id")
