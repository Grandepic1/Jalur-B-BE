from decimal import Decimal
from unittest import TestCase

from app.models.evidence import EvidenceItem, EvidenceItemCreate, EvidenceType
from app.models.financial import (
    FinancialAsset,
    FinancialAssetCreate,
    FinancialAssetType,
    LiquidityLevel,
)
from app.core.entitlements import DEFAULT_SEARCH_TIME_MONTHS, ExitType
from app.models.layoff import LayoffSimulation, LayoffSimulationCreate
from app.models.pivot import PivotAnalysis, PivotPreferredRole
from app.models.profile import CareerGoal, OnboardingCreate, UserProfile


class FrontendContractModelTests(TestCase):
    def test_onboarding_profile_columns_exist(self) -> None:
        self.assertEqual(
            set(UserProfile.__table__.columns.keys()),
            {
                "id",
                "user_id",
                "full_name",
                "avatar_url",
                "current_role_name",
                "industry_name",
                "work_duration_months",
                "is_first_job",
                "daily_activities",
                "career_goal",
                "target_role_name",
                "target_industry_name",
                "onboarding_completed_at",
                "created_at",
                "updated_at",
            },
        )

    def test_financial_asset_columns_preserve_form_data(self) -> None:
        self.assertTrue(
            {"name", "amount", "asset_type", "liquidity", "note", "currency"}
            <= set(FinancialAsset.__table__.columns.keys())
        )

    def test_analysis_models_include_frontend_result_fields(self) -> None:
        self.assertTrue(
            {"responsibilities", "skills_text", "tools_and_methods", "job_description"}
            <= set(PivotAnalysis.__table__.columns.keys())
        )
        self.assertTrue(
            {"match_score", "preparation_time_months", "preparation_description"}
            <= set(PivotPreferredRole.__table__.columns.keys())
        )
        self.assertTrue(
            {"scenario", "skill_relevance_score", "job_mobility_score", "evidence_count"}
            <= set(LayoffSimulation.__table__.columns.keys())
        )
        # Exit-aware fields: the simulation records which exit ground drove its numbers
        # and the regulation version those numbers came from.
        self.assertTrue(
            {
                "exit_type",
                "regulation_version",
                "search_time_months",
                "transition_gap_months",
                "transition_gap_status",
                "transition_role_name",
            }
            <= set(LayoffSimulation.__table__.columns.keys())
        )
        self.assertIn("ai_generated", EvidenceItem.__table__.columns)


class FrontendContractSchemaTests(TestCase):
    def test_onboarding_uses_canonical_types(self) -> None:
        profile = OnboardingCreate(
            full_name="Joan Orlando",
            current_role_name="Software Engineer",
            industry_name="Technology",
            work_duration_months=38,
            is_first_job=False,
            daily_activities="Build and maintain backend services",
            career_goal=CareerGoal.level_up,
            skills=["Programming", "System Design"],
        )

        self.assertEqual(profile.work_duration_months, 38)
        self.assertIs(profile.career_goal, CareerGoal.level_up)
        self.assertEqual(profile.skills, ["Programming", "System Design"])

    def test_financial_asset_uses_numeric_amount_and_enums(self) -> None:
        asset = FinancialAssetCreate(
            name="Emergency fund",
            amount=Decimal("20000000.00"),
            asset_type=FinancialAssetType.emergency_fund,
            liquidity=LiquidityLevel.liquid,
        )

        self.assertEqual(asset.amount, Decimal("20000000.00"))
        self.assertEqual(asset.currency, "IDR")

    def test_evidence_and_simulation_defaults_match_ui(self) -> None:
        evidence = EvidenceItemCreate(
            evidence_type=EvidenceType.project,
            title="Migration",
            user_role="Engineer",
            description="Completed migration",
            impact="Reduced deployment risk",
        )
        simulation = LayoffSimulationCreate()

        self.assertFalse(evidence.ai_generated)
        # The exit ground replaced the old time-based scenario choice; the search time is
        # an explicit, visible assumption.
        self.assertIs(simulation.exit_type, ExitType.efficiency_due_to_loss)
        self.assertEqual(simulation.search_time_months, DEFAULT_SEARCH_TIME_MONTHS)

    def test_layoff_simulation_horizon_defaults_to_twelve_months(self) -> None:
        from app.models.ai_features import LayoffSimulationRequest

        # The saving target is spread over an explicit horizon; the old code always passed
        # a zero horizon, which inflated the monthly figure to an unpayable amount.
        request = LayoffSimulationRequest()
        self.assertEqual(request.horizon_months, Decimal("12"))

    def test_employment_terms_model_exposes_statutory_inputs(self) -> None:
        from app.models.employment import EmploymentTerms, ExitRunwayCalculation

        self.assertTrue(
            {
                "monthly_wage_base",
                "employment_type",
                "assumed_exit_type",
                "contract_start_date",
                "contract_end_date",
                "tenure_months",
                "bpjs_tk_active",
                "jkn_active",
                "bpjs_contribution_months_last_24",
                "bpjs_consecutive_months",
                "jht_balance",
                "unused_leave_days",
            }
            <= set(EmploymentTerms.__table__.columns.keys())
        )
        self.assertIn("regulation_version", ExitRunwayCalculation.__table__.columns)
