"""create employment_terms table

Revision ID: a1f4c7d90b21
Revises: e2a9c8f4b6d1
Create Date: 2026-10-14

Adds the wage and contract facts the exit-aware runway needs: base wage, PKWT/PKWTT,
contract dates, tenure, and BPJS/JKN participation. Without these the statutory
entitlements (pesangon, UPMK, JKP) cannot be computed at all.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1f4c7d90b21'
down_revision: Union[str, Sequence[str], None] = 'e2a9c8f4b6d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'employment_terms',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('monthly_wage_base', sa.DECIMAL(precision=15, scale=2), nullable=False),
        sa.Column(
            'employment_type',
            sa.Enum('pkwtt', 'pkwt', name='employmenttype'),
            server_default='pkwtt',
            nullable=False,
        ),
        sa.Column(
            'assumed_exit_type',
            sa.Enum(
                'efficiency_prevent_loss',
                'efficiency_due_to_loss',
                'closure_not_loss',
                'bankruptcy',
                'pkwt_ends_on_schedule',
                'resign',
                name='exittype',
            ),
            server_default='efficiency_due_to_loss',
            nullable=False,
        ),
        sa.Column('contract_start_date', sa.DATE(), nullable=True),
        sa.Column('contract_end_date', sa.DATE(), nullable=True),
        sa.Column('tenure_months', sa.Integer(), nullable=True),
        sa.Column('bpjs_tk_active', sa.BOOLEAN(), server_default='false', nullable=False),
        sa.Column('jkn_active', sa.BOOLEAN(), server_default='false', nullable=False),
        sa.Column(
            'bpjs_contribution_months_last_24',
            sa.Integer(),
            server_default='0',
            nullable=False,
        ),
        sa.Column(
            'bpjs_consecutive_months', sa.Integer(), server_default='0', nullable=False
        ),
        sa.Column('age_years', sa.Integer(), nullable=True),
        sa.Column('jht_balance', sa.DECIMAL(precision=15, scale=2), nullable=True),
        sa.Column('unused_leave_days', sa.Integer(), nullable=True),
        sa.Column(
            'updated_at',
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.CheckConstraint(
            'age_years IS NULL OR age_years BETWEEN 15 AND 100',
            name='ck_employment_terms_age_range',
        ),
        sa.CheckConstraint(
            'bpjs_consecutive_months >= 0',
            name='ck_employment_terms_bpjs_consecutive_nonnegative',
        ),
        sa.CheckConstraint(
            'bpjs_contribution_months_last_24 >= 0',
            name='ck_employment_terms_bpjs_window_nonnegative',
        ),
        sa.CheckConstraint(
            'jht_balance IS NULL OR jht_balance >= 0',
            name='ck_employment_terms_jht_nonnegative',
        ),
        sa.CheckConstraint(
            'monthly_wage_base > 0', name='ck_employment_terms_wage_positive'
        ),
        sa.CheckConstraint(
            'tenure_months IS NULL OR tenure_months >= 0',
            name='ck_employment_terms_tenure_nonnegative',
        ),
        sa.CheckConstraint(
            'unused_leave_days IS NULL OR unused_leave_days >= 0',
            name='ck_employment_terms_leave_nonnegative',
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('employment_terms')
    # Last user of these types on the way down: exit_runway_calculations and
    # layoff_simulations have already dropped their columns by this point.
    op.execute('DROP TYPE IF EXISTS exittype')
    op.execute('DROP TYPE IF EXISTS employmenttype')
