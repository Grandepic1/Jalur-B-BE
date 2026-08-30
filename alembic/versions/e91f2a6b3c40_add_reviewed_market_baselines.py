"""Add reviewed market baselines and optional evidence impact.

Revision ID: e91f2a6b3c40
Revises: c74a1e9d5b20
Create Date: 2026-08-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e91f2a6b3c40"
down_revision: Union[str, Sequence[str], None] = "c74a1e9d5b20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


baseline_status = sa.Enum(
    "draft", "approved", "rejected", "archived", name="marketbaselinestatus"
)
subject_type = sa.Enum("role", "industry", "skill", name="marketsubjecttype")
signal_type = sa.Enum(
    "market_demand",
    "industry_stability",
    "skill_relevance",
    name="marketsignaltype",
)


def upgrade() -> None:
    op.alter_column("evidence_items", "impact", existing_type=sa.Text(), nullable=True)
    for table in (
        "health_assessments",
        "risk_scans",
        "ai_exposure_assessments",
        "pivot_analyses",
    ):
        op.add_column(table, sa.Column("market_baseline_version", sa.String(64)))
    op.add_column(
        "pivot_skill_gaps",
        sa.Column(
            "preferred_role_id",
            sa.BigInteger(),
            sa.ForeignKey("pivot_preferred_roles.id", ondelete="CASCADE"),
        ),
    )
    op.create_index(
        "ix_pivot_skill_gaps_preferred_role_id",
        "pivot_skill_gaps",
        ["preferred_role_id"],
    )

    op.create_table(
        "market_baselines",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("version", sa.String(64), nullable=False, unique=True),
        sa.Column("status", baseline_status, nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("provider_model", sa.String(100), nullable=False),
        sa.Column("prompt_version", sa.String(50), nullable=False),
        sa.Column("search_queries", postgresql.JSONB(), nullable=False),
        sa.Column("citations", postgresql.JSONB(), nullable=False),
        sa.Column("grounding_metadata", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_by",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "approved_by",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "generated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("approved_at", sa.TIMESTAMP(timezone=True)),
    )
    op.create_index(
        "uq_market_baselines_one_approved",
        "market_baselines",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'approved'"),
    )
    op.create_table(
        "market_baseline_signals",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "baseline_id",
            sa.BigInteger(),
            sa.ForeignKey("market_baselines.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("subject_type", subject_type, nullable=False),
        sa.Column("subject_name", sa.String(150), nullable=False),
        sa.Column("signal_type", signal_type, nullable=False),
        sa.Column("classification", sa.String(20), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "(signal_type = 'skill_relevance' AND classification IN "
            "('declining', 'stable', 'rising')) OR "
            "(signal_type <> 'skill_relevance' AND classification IN "
            "('weak', 'moderate', 'strong'))",
            name="ck_market_signal_classification",
        ),
        sa.CheckConstraint(
            "(subject_type = 'role' AND signal_type = 'market_demand') OR "
            "(subject_type = 'industry' AND signal_type = 'industry_stability') OR "
            "(subject_type = 'skill' AND signal_type = 'skill_relevance')",
            name="ck_market_signal_subject_type",
        ),
    )
    op.create_index(
        "uq_market_baseline_signal_subject",
        "market_baseline_signals",
        ["baseline_id", "subject_type", sa.text("lower(subject_name)"), "signal_type"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_market_baseline_signal_subject", table_name="market_baseline_signals"
    )
    op.drop_table("market_baseline_signals")
    op.drop_index("uq_market_baselines_one_approved", table_name="market_baselines")
    op.drop_table("market_baselines")
    signal_type.drop(op.get_bind(), checkfirst=True)
    subject_type.drop(op.get_bind(), checkfirst=True)
    baseline_status.drop(op.get_bind(), checkfirst=True)
    op.drop_index(
        "ix_pivot_skill_gaps_preferred_role_id", table_name="pivot_skill_gaps"
    )
    op.drop_column("pivot_skill_gaps", "preferred_role_id")
    for table in (
        "pivot_analyses",
        "ai_exposure_assessments",
        "risk_scans",
        "health_assessments",
    ):
        op.drop_column(table, "market_baseline_version")
    op.execute(
        sa.text(
            "UPDATE evidence_items SET impact = 'Dampak belum disebutkan.' "
            "WHERE impact IS NULL"
        )
    )
    op.alter_column("evidence_items", "impact", existing_type=sa.Text(), nullable=False)
