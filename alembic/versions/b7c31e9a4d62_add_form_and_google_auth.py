"""add_form_and_google_auth

Revision ID: b7c31e9a4d62
Revises: f42b8c1d7e90
Create Date: 2026-08-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7c31e9a4d62"
down_revision: Union[str, Sequence[str], None] = "f42b8c1d7e90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column("users", "password", existing_type=sa.String(length=255), nullable=True)
    op.add_column("users", sa.Column("google_sub", sa.String(length=255), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "email_verified",
            sa.Boolean(),
            server_default=sa.text("FALSE"),
            nullable=False,
        ),
    )
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_unique_constraint("uq_users_google_sub", "users", ["google_sub"])

    op.create_table(
        "oauth_login_codes",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_hash"),
    )
    op.create_index(
        op.f("ix_oauth_login_codes_user_id"),
        "oauth_login_codes",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_oauth_login_codes_expires_at"),
        "oauth_login_codes",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_oauth_login_codes_expires_at"), table_name="oauth_login_codes")
    op.drop_index(op.f("ix_oauth_login_codes_user_id"), table_name="oauth_login_codes")
    op.drop_table("oauth_login_codes")
    op.drop_constraint("uq_users_google_sub", "users", type_="unique")
    op.drop_column("users", "token_version")
    op.drop_column("users", "email_verified")
    op.drop_column("users", "google_sub")
    op.execute("UPDATE users SET password = '$disabled$' WHERE password IS NULL")
    op.alter_column("users", "password", existing_type=sa.String(length=255), nullable=False)
