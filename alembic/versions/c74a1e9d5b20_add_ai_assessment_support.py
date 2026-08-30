"""Add AI assessment scores and provenance.

Revision ID: c74a1e9d5b20
Revises: b91e4d7a2c60
Create Date: 2026-08-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c74a1e9d5b20"
down_revision: Union[str, Sequence[str], None] = "b91e4d7a2c60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _provenance_columns(table: str) -> None:
    op.add_column(table, sa.Column("provider_model", sa.String(100)))
    op.add_column(table, sa.Column("prompt_version", sa.String(50)))
    op.add_column(table, sa.Column("scoring_version", sa.String(50)))
    op.add_column(table, sa.Column("input_snapshot", postgresql.JSONB()))


def _drop_provenance_columns(table: str) -> None:
    op.drop_column(table, "input_snapshot")
    op.drop_column(table, "scoring_version")
    op.drop_column(table, "prompt_version")
    op.drop_column(table, "provider_model")


def upgrade() -> None:
    _provenance_columns("health_assessments")
    op.add_column("health_assessments", sa.Column("summary", sa.Text()))
    op.add_column("health_assessments", sa.Column("data_confidence", sa.DECIMAL(5, 2)))
    op.create_index(
        "ix_health_assessments_user_assessed",
        "health_assessments",
        ["user_id", sa.text("assessed_at DESC"), sa.text("id DESC")],
    )
    op.create_unique_constraint(
        "uq_health_breakdown_dimension",
        "health_score_breakdowns",
        ["assessment_id", "dimension"],
    )

    _provenance_columns("risk_scans")
    op.add_column("risk_scans", sa.Column("overall_score", sa.DECIMAL(5, 2)))
    op.add_column("risk_scans", sa.Column("analysis_description", sa.Text()))
    op.add_column("risk_scans", sa.Column("early_warning", sa.Text()))
    op.add_column("risk_scans", sa.Column("data_confidence", sa.DECIMAL(5, 2)))
    op.add_column("risk_factors", sa.Column("score", sa.DECIMAL(5, 2)))
    op.create_index(
        "ix_risk_scans_user_scanned",
        "risk_scans",
        ["user_id", sa.text("scanned_at DESC"), sa.text("id DESC")],
    )

    _provenance_columns("ai_exposure_assessments")
    op.add_column(
        "ai_exposure_assessments",
        sa.Column("overall_exposure_score", sa.DECIMAL(5, 2)),
    )
    op.add_column(
        "ai_exposure_assessments",
        sa.Column("skill_relevance_score", sa.DECIMAL(5, 2)),
    )
    op.add_column(
        "ai_exposure_assessments",
        sa.Column("data_confidence", sa.DECIMAL(5, 2)),
    )
    op.add_column("exposed_activities", sa.Column("exposure_score", sa.DECIMAL(5, 2)))
    op.create_index(
        "ix_ai_exposure_user_assessed",
        "ai_exposure_assessments",
        ["user_id", sa.text("assessed_at DESC"), sa.text("id DESC")],
    )

    _provenance_columns("pivot_analyses")
    op.add_column("pivot_analyses", sa.Column("data_confidence", sa.DECIMAL(5, 2)))
    op.create_index(
        "ix_pivot_analyses_user_analyzed",
        "pivot_analyses",
        ["user_id", sa.text("analyzed_at DESC"), sa.text("id DESC")],
    )

    _provenance_columns("layoff_simulations")
    op.add_column(
        "layoff_simulations",
        sa.Column("target_runway_months", sa.DECIMAL(6, 2)),
    )
    op.create_index(
        "ix_layoff_simulations_user_simulated",
        "layoff_simulations",
        ["user_id", sa.text("simulated_at DESC"), sa.text("id DESC")],
    )
    op.create_unique_constraint(
        "uq_simulation_action_order",
        "simulation_action_items",
        ["simulation_id", "step_order"],
    )

    op.add_column("evidence_items", sa.Column("ai_model", sa.String(100)))
    op.add_column("evidence_items", sa.Column("ai_prompt_version", sa.String(50)))

    op.create_table(
        "weekly_career_insights",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("weekly_insight", sa.Text(), nullable=False),
        sa.Column("next_action", sa.Text(), nullable=False),
        sa.Column("next_action_path", sa.String(100), nullable=False),
        sa.Column("provider_model", sa.String(100), nullable=False),
        sa.Column("prompt_version", sa.String(50), nullable=False),
        sa.Column(
            "generated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "user_id", "week_start", name="uq_weekly_insight_user_week"
        ),
    )


def downgrade() -> None:
    op.drop_table("weekly_career_insights")
    op.drop_column("evidence_items", "ai_prompt_version")
    op.drop_column("evidence_items", "ai_model")
    op.drop_constraint(
        "uq_simulation_action_order", "simulation_action_items", type_="unique"
    )
    op.drop_index(
        "ix_layoff_simulations_user_simulated", table_name="layoff_simulations"
    )
    op.drop_column("layoff_simulations", "target_runway_months")
    _drop_provenance_columns("layoff_simulations")
    op.drop_index("ix_pivot_analyses_user_analyzed", table_name="pivot_analyses")
    op.drop_column("pivot_analyses", "data_confidence")
    _drop_provenance_columns("pivot_analyses")
    op.drop_index("ix_ai_exposure_user_assessed", table_name="ai_exposure_assessments")
    op.drop_column("exposed_activities", "exposure_score")
    op.drop_column("ai_exposure_assessments", "data_confidence")
    op.drop_column("ai_exposure_assessments", "skill_relevance_score")
    op.drop_column("ai_exposure_assessments", "overall_exposure_score")
    _drop_provenance_columns("ai_exposure_assessments")
    op.drop_index("ix_risk_scans_user_scanned", table_name="risk_scans")
    op.drop_column("risk_factors", "score")
    op.drop_column("risk_scans", "data_confidence")
    op.drop_column("risk_scans", "early_warning")
    op.drop_column("risk_scans", "analysis_description")
    op.drop_column("risk_scans", "overall_score")
    _drop_provenance_columns("risk_scans")
    op.drop_constraint(
        "uq_health_breakdown_dimension", "health_score_breakdowns", type_="unique"
    )
    op.drop_index(
        "ix_health_assessments_user_assessed", table_name="health_assessments"
    )
    op.drop_column("health_assessments", "data_confidence")
    op.drop_column("health_assessments", "summary")
    _drop_provenance_columns("health_assessments")
