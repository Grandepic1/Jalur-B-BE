"""Add support for deterministic user features.

Revision ID: a62f4c8d1e73
Revises: e4a7c29d6b18
Create Date: 2026-08-29
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a62f4c8d1e73"
down_revision: Union[str, Sequence[str], None] = "e4a7c29d6b18"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    duplicate_email = connection.scalar(
        sa.text(
            "SELECT lower(email) FROM users "
            "GROUP BY lower(email) HAVING count(*) > 1 LIMIT 1"
        )
    )
    duplicate_username = connection.scalar(
        sa.text(
            "SELECT lower(username) FROM users "
            "GROUP BY lower(username) HAVING count(*) > 1 LIMIT 1"
        )
    )
    invalid_skill = connection.scalar(
        sa.text(
            "SELECT id FROM user_skills WHERE "
            "(proficiency_level IS NOT NULL AND proficiency_level NOT BETWEEN 1 AND 5) "
            "OR (years_experience IS NOT NULL AND years_experience NOT BETWEEN 0 AND 99.9) "
            "LIMIT 1"
        )
    )
    if duplicate_email is not None:
        raise RuntimeError(
            f"Resolve case-insensitive duplicate user email before migration: {duplicate_email}"
        )
    if duplicate_username is not None:
        raise RuntimeError(
            "Resolve case-insensitive duplicate username before migration: "
            f"{duplicate_username}"
        )
    if invalid_skill is not None:
        raise RuntimeError(
            f"Correct out-of-range user skill values before migration: id={invalid_skill}"
        )

    op.add_column(
        "auth_action_tokens",
        sa.Column("target_email", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "uq_users_email_lower",
        "users",
        [sa.text("lower(email)")],
        unique=True,
    )
    op.create_index(
        "uq_users_username_lower",
        "users",
        [sa.text("lower(username)")],
        unique=True,
    )
    op.create_check_constraint(
        "ck_user_skills_proficiency",
        "user_skills",
        "proficiency_level IS NULL OR proficiency_level BETWEEN 1 AND 5",
    )
    op.create_check_constraint(
        "ck_user_skills_years_experience",
        "user_skills",
        "years_experience IS NULL OR years_experience BETWEEN 0 AND 99.9",
    )
    op.create_index(
        "ix_evidence_items_user_created",
        "evidence_items",
        ["user_id", sa.text("created_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "ix_evidence_items_user_type_created",
        "evidence_items",
        [
            "user_id",
            "evidence_type",
            sa.text("created_at DESC"),
            sa.text("id DESC"),
        ],
    )
    op.create_index(
        "ix_skill_missions_user_status_due",
        "skill_missions",
        ["user_id", "status", "due_date", "id"],
    )
    op.create_index(
        "ix_skill_missions_user_created",
        "skill_missions",
        ["user_id", sa.text("created_at DESC"), sa.text("id DESC")],
    )
    op.add_column(
        "runway_calculations",
        sa.Column("total_assets_snapshot", sa.DECIMAL(15, 2), nullable=True),
    )
    op.add_column(
        "runway_calculations",
        sa.Column("currency_snapshot", sa.CHAR(3), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("runway_calculations", "currency_snapshot")
    op.drop_column("runway_calculations", "total_assets_snapshot")
    op.drop_index(
        "ix_skill_missions_user_created", table_name="skill_missions"
    )
    op.drop_index(
        "ix_skill_missions_user_status_due", table_name="skill_missions"
    )
    op.drop_index(
        "ix_evidence_items_user_type_created", table_name="evidence_items"
    )
    op.drop_index("ix_evidence_items_user_created", table_name="evidence_items")
    op.drop_constraint(
        "ck_user_skills_years_experience", "user_skills", type_="check"
    )
    op.drop_constraint(
        "ck_user_skills_proficiency", "user_skills", type_="check"
    )
    op.drop_index("uq_users_username_lower", table_name="users")
    op.drop_index("uq_users_email_lower", table_name="users")
    op.drop_column("auth_action_tokens", "target_email")
