"""add_frontend_integration_schema

Revision ID: f42b8c1d7e90
Revises: d3d4562fa0a5
Create Date: 2026-08-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f42b8c1d7e90"
down_revision: Union[str, Sequence[str], None] = "d3d4562fa0a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

career_goal = postgresql.ENUM(
    "grow_current",
    "level_up",
    "change_role",
    "change_industry",
    "undecided",
    name="careergoal",
    create_type=False,
)
financial_asset_type = postgresql.ENUM(
    "main_savings",
    "emergency_fund",
    "long_term_savings",
    "investment",
    "other",
    name="financialassettype",
    create_type=False,
)
liquidity_level = postgresql.ENUM(
    "liquid",
    "requires_process",
    "illiquid",
    name="liquiditylevel",
    create_type=False,
)
layoff_scenario = postgresql.ENUM(
    "tomorrow",
    "one_month",
    "three_months",
    name="layoffscenario",
    create_type=False,
)


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    career_goal.create(bind, checkfirst=True)
    financial_asset_type.create(bind, checkfirst=True)
    liquidity_level.create(bind, checkfirst=True)
    layoff_scenario.create(bind, checkfirst=True)

    op.create_table(
        "user_profiles",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("full_name", sa.String(length=150), nullable=False),
        sa.Column("avatar_url", sa.String(length=500), nullable=True),
        sa.Column("current_role_name", sa.String(length=100), nullable=False),
        sa.Column("industry_name", sa.String(length=100), nullable=False),
        sa.Column("work_duration_months", sa.Integer(), nullable=True),
        sa.Column("is_first_job", sa.Boolean(), nullable=True),
        sa.Column("daily_activities", sa.Text(), nullable=True),
        sa.Column("career_goal", career_goal, nullable=True),
        sa.Column("target_role_name", sa.String(length=100), nullable=True),
        sa.Column("target_industry_name", sa.String(length=100), nullable=True),
        sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )

    op.create_table(
        "financial_assets",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("amount", sa.DECIMAL(precision=15, scale=2), nullable=False),
        sa.Column("asset_type", financial_asset_type, nullable=False),
        sa.Column("liquidity", liquidity_level, nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("currency", sa.CHAR(length=3), server_default="IDR", nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_financial_assets_user_id"),
        "financial_assets",
        ["user_id"],
        unique=False,
    )

    op.add_column("pivot_analyses", sa.Column("responsibilities", sa.Text(), nullable=True))
    op.add_column("pivot_analyses", sa.Column("skills_text", sa.Text(), nullable=True))
    op.add_column("pivot_analyses", sa.Column("tools_and_methods", sa.Text(), nullable=True))
    op.add_column("pivot_analyses", sa.Column("job_description", sa.Text(), nullable=True))
    op.add_column(
        "pivot_analyses",
        sa.Column("job_description_url", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "pivot_preferred_roles",
        sa.Column("match_score", sa.DECIMAL(precision=5, scale=2), nullable=True),
    )
    op.add_column(
        "pivot_preferred_roles",
        sa.Column("preparation_time_months", sa.Integer(), nullable=True),
    )
    op.add_column(
        "pivot_preferred_roles",
        sa.Column("preparation_description", sa.Text(), nullable=True),
    )
    op.add_column(
        "evidence_items",
        sa.Column(
            "ai_generated",
            sa.Boolean(),
            server_default=sa.text("FALSE"),
            nullable=False,
        ),
    )
    op.add_column(
        "layoff_simulations",
        sa.Column(
            "scenario",
            layoff_scenario,
            server_default="tomorrow",
            nullable=False,
        ),
    )
    op.add_column(
        "layoff_simulations",
        sa.Column("skill_relevance_score", sa.DECIMAL(precision=5, scale=2), nullable=True),
    )
    op.add_column(
        "layoff_simulations",
        sa.Column("job_mobility_score", sa.DECIMAL(precision=5, scale=2), nullable=True),
    )
    op.add_column(
        "layoff_simulations",
        sa.Column("evidence_count", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("layoff_simulations", "evidence_count")
    op.drop_column("layoff_simulations", "job_mobility_score")
    op.drop_column("layoff_simulations", "skill_relevance_score")
    op.drop_column("layoff_simulations", "scenario")
    op.drop_column("evidence_items", "ai_generated")
    op.drop_column("pivot_preferred_roles", "preparation_description")
    op.drop_column("pivot_preferred_roles", "preparation_time_months")
    op.drop_column("pivot_preferred_roles", "match_score")
    op.drop_column("pivot_analyses", "job_description_url")
    op.drop_column("pivot_analyses", "job_description")
    op.drop_column("pivot_analyses", "tools_and_methods")
    op.drop_column("pivot_analyses", "skills_text")
    op.drop_column("pivot_analyses", "responsibilities")
    op.drop_index(op.f("ix_financial_assets_user_id"), table_name="financial_assets")
    op.drop_table("financial_assets")
    op.drop_table("user_profiles")

    bind = op.get_bind()
    layoff_scenario.drop(bind, checkfirst=True)
    liquidity_level.drop(bind, checkfirst=True)
    financial_asset_type.drop(bind, checkfirst=True)
    career_goal.drop(bind, checkfirst=True)
