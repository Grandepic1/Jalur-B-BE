"""Schedule storage cleanup jobs safely.

Revision ID: d7f2c9a5e130
Revises: c6e1a8b4f920
Create Date: 2026-09-03
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "d7f2c9a5e130"
down_revision: Union[str, Sequence[str], None] = "c6e1a8b4f920"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "storage_deletion_jobs",
        sa.Column(
            "not_before",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("storage_deletion_jobs", "not_before")
