"""Make confirmed CV file columns optional.

Revision ID: e2a9c8f4b6d1
Revises: d7f2c9a5e130
Create Date: 2026-09-03

CV confirmation no longer stores the source file: confirmed CVs keep only the
reviewed extracted data (profile, skills, experiences). Legacy rows may still
reference a stored file, so the columns are kept nullable instead of dropped.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "e2a9c8f4b6d1"
down_revision: Union[str, Sequence[str], None] = "d7f2c9a5e130"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("user_cvs", "file_name", existing_type=sa.String(255), nullable=True)
    op.alter_column("user_cvs", "file_size", existing_type=sa.Integer(), nullable=True)
    op.alter_column("user_cvs", "content_type", existing_type=sa.String(100), nullable=True)
    op.alter_column(
        "user_cvs", "storage_object_path", existing_type=sa.String(500), nullable=True
    )


def downgrade() -> None:
    op.alter_column("user_cvs", "storage_object_path", existing_type=sa.String(500), nullable=False)
    op.alter_column("user_cvs", "content_type", existing_type=sa.String(100), nullable=False)
    op.alter_column("user_cvs", "file_size", existing_type=sa.Integer(), nullable=False)
    op.alter_column("user_cvs", "file_name", existing_type=sa.String(255), nullable=False)
