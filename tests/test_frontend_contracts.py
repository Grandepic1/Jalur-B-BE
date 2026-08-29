from decimal import Decimal
from unittest import TestCase

from app.models.evidence import EvidenceItem, EvidenceItemCreate, EvidenceType
from app.models.financial import (
    FinancialAsset,
    FinancialAssetCreate,
    FinancialAssetType,
    LiquidityLevel,
)
from app.models.layoff import LayoffScenario, LayoffSimulation, LayoffSimulationCreate
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
        self.assertIs(simulation.scenario, LayoffScenario.tomorrow)
