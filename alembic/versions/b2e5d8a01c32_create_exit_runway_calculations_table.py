"""create exit_runway_calculations table

Revision ID: b2e5d8a01c32
Revises: a1f4c7d90b21
Create Date: 2026-10-14

Immutable snapshots of one exit-aware runway calculation. ``regulation_version`` is
stored on every row so a future change to the severance tables never rewrites history.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b2e5d8a01c32'
down_revision: Union[str, Sequence[str], None] = 'a1f4c7d90b21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Created by the employment_terms migration; reuse without re-creating.
EXIT_TYPE = postgresql.ENUM(
    'efficiency_prevent_loss',
    'efficiency_due_to_loss',
    'closure_not_loss',
    'bankruptcy',
    'pkwt_ends_on_schedule',
    'resign',
    name='exittype',
    create_type=False,
)
EMPLOYMENT_TYPE = postgresql.ENUM(
    'pkwtt', 'pkwt', name='employmenttype', create_type=False
)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'exit_runway_calculations',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('exit_type', EXIT_TYPE, nullable=False),
        sa.Column('employment_type', EMPLOYMENT_TYPE, nullable=False),
        sa.Column('regulation_version', sa.String(length=64), nullable=False),
        sa.Column(
            'monthly_wage_base_snapshot', sa.DECIMAL(precision=15, scale=2), nullable=False
        ),
        sa.Column('tenure_months_snapshot', sa.Integer(), nullable=False),
        sa.Column(
            'essential_expenses_snapshot', sa.DECIMAL(precision=15, scale=2), nullable=False
        ),
        sa.Column(
            'debt_payment_snapshot', sa.DECIMAL(precision=15, scale=2), nullable=True
        ),
        sa.Column(
            'liquid_assets_snapshot', sa.DECIMAL(precision=15, scale=2), nullable=False
        ),
        sa.Column('jht_balance_snapshot', sa.DECIMAL(precision=15, scale=2), nullable=True),
        sa.Column('currency_snapshot', sa.String(length=3), nullable=False),
        sa.Column('pesangon_months', sa.DECIMAL(precision=6, scale=2), nullable=False),
        sa.Column('upmk_months', sa.DECIMAL(precision=6, scale=2), nullable=False),
        sa.Column('gross_lump_sum', sa.DECIMAL(precision=15, scale=2), nullable=False),
        sa.Column('severance_tax', sa.DECIMAL(precision=15, scale=2), nullable=False),
        sa.Column('net_lump_sum', sa.DECIMAL(precision=15, scale=2), nullable=False),
        sa.Column(
            'normative_collectable', sa.BOOLEAN(), server_default='true', nullable=False
        ),
        sa.Column('liquid_normative', sa.DECIMAL(precision=15, scale=2), nullable=False),
        sa.Column('jkp_eligible', sa.BOOLEAN(), server_default='false', nullable=False),
        sa.Column(
            'jkp_monthly_benefit', sa.DECIMAL(precision=15, scale=2), nullable=False
        ),
        sa.Column('jkp_months', sa.Integer(), server_default='0', nullable=False),
        sa.Column(
            'jkp_ineligible_reasons',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            'savings_only_runway_months', sa.DECIMAL(precision=12, scale=2), nullable=False
        ),
        sa.Column(
            'with_normative_rights_runway_months',
            sa.DECIMAL(precision=12, scale=2),
            nullable=False,
        ),
        sa.Column(
            'with_jkp_runway_months', sa.DECIMAL(precision=12, scale=2), nullable=False
        ),
        sa.Column(
            'with_jht_runway_months', sa.DECIMAL(precision=12, scale=2), nullable=False
        ),
        sa.Column('day_of_layoff', sa.DATE(), nullable=False),
        sa.Column('money_runs_out_on', sa.DATE(), nullable=True),
        sa.Column('jkp_claim_deadline', sa.DATE(), nullable=True),
        sa.Column('cost_of_living_warning', sa.String(length=500), nullable=True),
        sa.Column('notes', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            'calculated_at',
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.CheckConstraint(
            'day_of_layoff IS NOT NULL', name='ck_exit_runway_effective_date_present'
        ),
        sa.CheckConstraint(
            'savings_only_runway_months >= 0',
            name='ck_exit_runway_savings_months_nonnegative',
        ),
        sa.CheckConstraint(
            'with_jkp_runway_months >= 0',
            name='ck_exit_runway_headline_months_nonnegative',
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_exit_runway_calculations_user_calculated',
        'exit_runway_calculations',
        ['user_id', sa.literal_column('calculated_at DESC'), sa.literal_column('id DESC')],
        unique=False,
    )
    op.create_index(
        op.f('ix_exit_runway_calculations_user_id'),
        'exit_runway_calculations',
        ['user_id'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_exit_runway_calculations_user_id'),
        table_name='exit_runway_calculations',
    )
    op.drop_index(
        'ix_exit_runway_calculations_user_calculated',
        table_name='exit_runway_calculations',
    )
    op.drop_table('exit_runway_calculations')
