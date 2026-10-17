"""Weight invariants for the resilience scores.

These tests are the acceptance criteria for the double-counting fix: every weight group
must sum to exactly 1.00, and no raw input may reach a final score through two different
paths.
"""

from decimal import Decimal
from unittest import TestCase

from app.core.scoring import (
    SCORE_VERSION,
    average,
    career_readiness,
    career_risk,
    overall_resilience,
    pivot_match,
    weighted_optional,
)
from app.core.scoring_config import (
    CAREER_READINESS_WEIGHTS,
    CAREER_RISK_WEIGHTS,
    PIVOT_MATCH_WEIGHTS,
    RESILIENCE_WEIGHTS,
    weight_groups,
)


class WeightGroupTests(TestCase):
    def test_every_group_sums_to_exactly_one(self) -> None:
        for name, weights in weight_groups().items():
            with self.subTest(group=name):
                self.assertEqual(
                    sum(weights.values()),
                    Decimal("1"),
                    f"{name} weights must sum to 1.00",
                )

    def test_every_group_is_non_empty_and_positive(self) -> None:
        for name, weights in weight_groups().items():
            with self.subTest(group=name):
                self.assertTrue(weights)
                self.assertTrue(all(weight > 0 for weight in weights.values()))


class NoDoubleCountingTests(TestCase):
    """T1: Financial Readiness, Skill Relevance, and Mobility each had two paths."""

    def test_financial_readiness_is_not_inside_career_readiness(self) -> None:
        self.assertNotIn("financial_readiness", CAREER_READINESS_WEIGHTS)

    def test_resilience_composes_two_aggregates_only(self) -> None:
        self.assertEqual(
            set(RESILIENCE_WEIGHTS), {"career_readiness", "financial_readiness"}
        )

    def test_raw_career_inputs_do_not_reappear_in_resilience(self) -> None:
        # Skill relevance and mobility belong to Career Readiness alone.
        overlap = set(CAREER_READINESS_WEIGHTS) & set(RESILIENCE_WEIGHTS)
        self.assertEqual(overlap, set())
        for leaked in ("skill_relevance", "mobility", "performance_growth"):
            self.assertNotIn(leaked, RESILIENCE_WEIGHTS)

    def test_financial_readiness_does_not_change_career_readiness(self) -> None:
        values = {
            "performance_growth": Decimal("80"),
            "skill_relevance": Decimal("80"),
            "adaptability": Decimal("80"),
            "mobility": Decimal("80"),
        }
        # All four components are 80, so the weighted result is exactly 80 regardless of
        # any financial input. Under the old formula this moved with financial readiness.
        self.assertEqual(career_readiness(**values), Decimal("80.00"))

    def test_resilience_is_the_unweighted_blend_of_the_two_halves(self) -> None:
        self.assertEqual(
            overall_resilience(
                career_readiness_score=Decimal("80"),
                financial_readiness_score=Decimal("50"),
            ),
            Decimal("65.00"),
        )
        self.assertEqual(
            overall_resilience(
                career_readiness_score=Decimal("50"),
                financial_readiness_score=Decimal("80"),
            ),
            Decimal("65.00"),
        )

    def test_resilience_does_not_accept_raw_component_arguments(self) -> None:
        # The signature is the guard: there is no way to pass skill relevance or mobility
        # into Overall Resilience at all.
        with self.assertRaises(TypeError):
            overall_resilience(  # type: ignore[call-arg]
                career_readiness_score=Decimal("80"),
                financial_readiness_score=Decimal("50"),
                skill_relevance=Decimal("90"),
            )

    def test_score_version_records_the_formula_change(self) -> None:
        self.assertEqual(SCORE_VERSION, "career-resilience-v2")


class OptionalComponentTests(TestCase):
    """T5: a missing input must never be replaced by a plausible-looking number."""

    def test_average_of_nothing_is_none_not_fifty(self) -> None:
        self.assertIsNone(average([]))

    def test_average_of_values_is_unchanged(self) -> None:
        self.assertEqual(
            average([Decimal("25"), Decimal("80")]), Decimal("52.50")
        )

    def test_weighted_optional_drops_missing_components_and_renormalizes(self) -> None:
        # Present weights are 0.50 and 0.25 and sum to 0.75, so they become 2/3 and 1/3:
        # 60 * (0.50/0.75) + 90 * (0.25/0.75) = 40 + 30 = 70.
        self.assertEqual(
            weighted_optional(
                [
                    (Decimal("60"), Decimal("0.5")),
                    (None, Decimal("0.25")),
                    (Decimal("90"), Decimal("0.25")),
                ]
            ),
            Decimal("70.00"),
        )

    def test_weighted_optional_is_none_when_everything_is_missing(self) -> None:
        self.assertIsNone(
            weighted_optional([(None, Decimal("0.5")), (None, Decimal("0.5"))])
        )

    def test_renormalization_keeps_the_score_on_scale(self) -> None:
        # Dropping a component must not dilute the score toward zero.
        self.assertEqual(
            weighted_optional(
                [
                    (Decimal("100"), Decimal("0.5")),
                    (None, Decimal("0.5")),
                ]
            ),
            Decimal("100.00"),
        )

    def test_career_readiness_renormalizes_when_a_component_is_missing(self) -> None:
        without_mobility = career_readiness(
            performance_growth=Decimal("80"),
            skill_relevance=Decimal("80"),
            adaptability=Decimal("80"),
            mobility=None,
        )
        self.assertEqual(without_mobility, Decimal("80.00"))

    def test_career_risk_renormalizes_when_exposure_is_missing(self) -> None:
        self.assertEqual(
            career_risk(
                activity_exposure=None,
                market_demand_risk=Decimal("50"),
                skill_dependency_risk=Decimal("50"),
                industry_volatility_risk=Decimal("50"),
            ),
            Decimal("50.00"),
        )


class PivotMatchTests(TestCase):
    def test_pivot_weights_are_applied_in_order(self) -> None:
        self.assertEqual(
            pivot_match(
                skill_fit=Decimal("85"),
                activity_fit=Decimal("85"),
                experience_fit=Decimal("85"),
                industry_fit=Decimal("85"),
            ),
            Decimal("85.00"),
        )

    def test_documented_weights_match_the_configured_weights(self) -> None:
        self.assertEqual(PIVOT_MATCH_WEIGHTS["skill_fit"], Decimal("0.55"))
        self.assertEqual(PIVOT_MATCH_WEIGHTS["industry_fit"], Decimal("0.10"))
        self.assertEqual(CAREER_RISK_WEIGHTS["activity_exposure"], Decimal("0.40"))
        self.assertEqual(CAREER_RISK_WEIGHTS["industry_volatility"], Decimal("0.15"))
