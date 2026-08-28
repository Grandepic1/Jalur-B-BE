"""add_auth_action_tokens

Revision ID: c84d2f6a9b13
Revises: b7c31e9a4d62
Create Date: 2026-08-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c84d2f6a9b13"
down_revision: Union[str, Sequence[str], None] = "b7c31e9a4d62"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

auth_token_purpose = postgresql.ENUM(
    "verify_email",
    "reset_password",
    name="authtokenpurpose",
    create_type=False,
)


def upgrade() -> None:
    """Upgrade schema."""
    auth_token_purpose.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "auth_action_tokens",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("purpose", auth_token_purpose, nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
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
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        op.f("ix_auth_action_tokens_user_id"),
        "auth_action_tokens",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_auth_action_tokens_expires_at"),
        "auth_action_tokens",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_auth_action_tokens_expires_at"), table_name="auth_action_tokens")
    op.drop_index(op.f("ix_auth_action_tokens_user_id"), table_name="auth_action_tokens")
    op.drop_table("auth_action_tokens")
    auth_token_purpose.drop(op.get_bind(), checkfirst=True)
