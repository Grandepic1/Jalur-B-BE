from unittest import TestCase

from pydantic import ValidationError

from app.models.profile import CareerGoal, OnboardingCreate
from main import app


class OnboardingSchemaTests(TestCase):
    def test_normalizes_text_and_deduplicates_skills(self) -> None:
        payload = OnboardingCreate(
            full_name="  Joan   Orlando ",
            current_role_name=" Backend   Engineer ",
            industry_name=" Technology ",
            work_duration_months=24,
            is_first_job=False,
            daily_activities=" Build   APIs ",
            career_goal=CareerGoal.level_up,
            target_role_name=" Senior   Engineer ",
            skills=[" Python ", "python", " API   Design "],
        )

        self.assertEqual(payload.full_name, "Joan Orlando")
        self.assertEqual(payload.daily_activities, "Build APIs")
        self.assertEqual(payload.target_role_name, "Senior Engineer")
        self.assertEqual(payload.skills, ["Python", "API Design"])

    def test_requires_at_least_one_non_empty_skill(self) -> None:
        with self.assertRaises(ValidationError):
            OnboardingCreate(
                full_name="Joan Orlando",
                current_role_name="Backend Engineer",
                industry_name="Technology",
                work_duration_months=24,
                is_first_job=False,
                daily_activities="Build APIs",
                career_goal=CareerGoal.level_up,
                skills=["   "],
            )

    def test_rejects_malformed_and_oversized_values(self) -> None:
        base_payload = {
            "current_role_name": "Backend Engineer",
            "industry_name": "Technology",
            "work_duration_months": 24,
            "is_first_job": False,
            "daily_activities": "Build APIs",
            "career_goal": CareerGoal.level_up,
        }
        with self.assertRaises(ValidationError):
            OnboardingCreate(full_name=123, skills=["Python"], **base_payload)
        with self.assertRaises(ValidationError):
            OnboardingCreate(full_name="Joan", skills=["x" * 101], **base_payload)
        with self.assertRaises(ValidationError):
            OnboardingCreate(
                full_name="Joan",
                skills=["Python"],
                **{**base_payload, "work_duration_months": "24"},
            )
        with self.assertRaises(ValidationError):
            OnboardingCreate(
                full_name="Joan",
                skills=["Python"],
                **{**base_payload, "work_duration_months": 961},
            )
        with self.assertRaises(ValidationError):
            OnboardingCreate(
                full_name="Joan",
                skills=["Python"],
                **{**base_payload, "is_first_job": 1},
            )


class OnboardingRouteTests(TestCase):
    def test_openapi_exposes_onboarding_contract(self) -> None:
        paths = app.openapi()["paths"]

        self.assertEqual(set(paths["/api/onboarding"]), {"get", "put"})
        self.assertEqual(set(paths["/api/onboarding/options"]), {"get"})
