"""add_case_insensitive_skill_names

Revision ID: d19e5a7c3f40
Revises: c84d2f6a9b13
Create Date: 2026-08-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d19e5a7c3f40"
down_revision: Union[str, Sequence[str], None] = "c84d2f6a9b13"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        CREATE TEMP TABLE skill_merge ON COMMIT DROP AS
        SELECT id AS old_id, MIN(id) OVER (PARTITION BY lower(name)) AS canonical_id
        FROM skills
        """
    )
    op.execute(
        """
        UPDATE skills AS canonical
        SET category = COALESCE(canonical.category, metadata.category),
            market_trend = metadata.market_trend
        FROM (
            SELECT merge.canonical_id,
                   MAX(skill.category) FILTER (WHERE skill.category IS NOT NULL) AS category,
                   CASE
                       WHEN bool_or(skill.market_trend = 'rising') THEN 'rising'
                       WHEN bool_or(skill.market_trend = 'stable') THEN 'stable'
                       ELSE 'declining'
                   END AS market_trend
            FROM skill_merge AS merge
            JOIN skills AS skill ON skill.id = merge.old_id
            GROUP BY merge.canonical_id
        ) AS metadata
        WHERE canonical.id = metadata.canonical_id
        """
    )
    op.execute(
        """
        UPDATE user_skills AS canonical
        SET proficiency_level = GREATEST(
                canonical.proficiency_level,
                duplicate.proficiency_level
            ),
            years_experience = GREATEST(
                canonical.years_experience,
                duplicate.years_experience
            )
        FROM user_skills AS duplicate
        JOIN skill_merge AS merge ON duplicate.skill_id = merge.old_id
        WHERE merge.old_id <> merge.canonical_id
          AND canonical.user_id = duplicate.user_id
          AND canonical.skill_id = merge.canonical_id
        """
    )
    op.execute(
        """
        DELETE FROM user_skills AS old
        USING skill_merge AS merge
        WHERE old.skill_id = merge.old_id
          AND merge.old_id <> merge.canonical_id
          AND EXISTS (
              SELECT 1 FROM user_skills AS canonical
              WHERE canonical.user_id = old.user_id
                AND canonical.skill_id = merge.canonical_id
          )
        """
    )
    for table_name in (
        "user_skills",
        "risk_scan_skills",
        "skill_relevances",
        "ai_exposure_skills",
        "pivot_skill_gaps",
        "skill_missions",
    ):
        op.execute(
            f"""
            UPDATE {table_name} AS reference
            SET skill_id = merge.canonical_id
            FROM skill_merge AS merge
            WHERE reference.skill_id = merge.old_id
              AND merge.old_id <> merge.canonical_id
            """
        )
    op.execute(
        """
        DELETE FROM skills AS duplicate
        USING skill_merge AS merge
        WHERE duplicate.id = merge.old_id
          AND merge.old_id <> merge.canonical_id
        """
    )
    op.create_index(
        "uq_skills_name_lower",
        "skills",
        [sa.text("lower(name)")],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("uq_skills_name_lower", table_name="skills")
