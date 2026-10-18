"""Transition Gap tests.

TG(role) = R_exit - (T_prep(role) + T_search). The persona expectations come from the fix
spec: Rani with efficiency_due_to_loss (R = 10.75) and a four-month preparation time plus
the three-month search assumption is a surplus, while the same user exiting by
resignation (R = 2.50) is in deficit.
"""

from datetime import date
from decimal import Decimal
from unittest import TestCase

from app.core.entitlements import ExitType
from app.core.transition import (
    MAX_PREPARATION_MONTHS,
    MIN_PREPARATION_MONTHS,
    months_saved_by_closing_one_gap,
    preparation_months_for_gap_count,
    savings_horizon,
    select_preparation_role,
    transition_gap,
)


class RaniTransitionTests(TestCase):
    def test_prevent_loss_exit_is_a_surplus(self) -> None:
        # 10.75 - (4 + 3) = 3.75
        result = transition_gap(
            role_name="Data Analyst",
            match_score=Decimal("72"),
            preparation_time_months=Decimal("4"),
            exit_runway_months=Decimal("10.75"),
            monthly_burn=Decimal("6000000"),
            search_time_months=Decimal("3"),
        )
        self.assertEqual(result.transition_gap_months, Decimal("3.75"))
        self.assertEqual(result.status, "surplus")
        self.assertEqual(result.transition_months, Decimal("7"))
        self.assertEqual(result.recommended_monthly_saving, Decimal("0"))

    def test_resignation_is_a_deficit(self) -> None:
        # 2.50 - (4 + 3) = -4.50
        result = transition_gap(
            role_name="Data Analyst",
            match_score=Decimal("72"),
            preparation_time_months=Decimal("4"),
            exit_runway_months=Decimal("2.50"),
            monthly_burn=Decimal("6000000"),
            search_time_months=Decimal("3"),
        )
        self.assertEqual(result.transition_gap_months, Decimal("-4.50"))
        self.assertEqual(result.status, "deficit")

    def test_deficit_becomes_a_monthly_saving_target(self) -> None:
        result = transition_gap(
            role_name="Data Analyst",
            match_score=Decimal("72"),
            preparation_time_months=Decimal("4"),
            exit_runway_months=Decimal("2.50"),
            monthly_burn=Decimal("6000000"),
            search_time_months=Decimal("3"),
            horizon_months=Decimal("6"),
        )
        # 4.5 months of burn is 27,000,000 spread over 6 months.
        self.assertEqual(result.recommended_monthly_saving, Decimal("4500000"))

    def test_twelve_month_horizon_matches_the_paper(self) -> None:
        result = transition_gap(
            role_name="Data Analyst",
            match_score=Decimal("72"),
            preparation_time_months=Decimal("4"),
            exit_runway_months=Decimal("2.50"),
            monthly_burn=Decimal("6000000"),
            search_time_months=Decimal("3"),
            horizon_months=Decimal("12"),
        )
        # 27,000,000 spread over 12 months, the figure reported in the paper.
        self.assertEqual(result.recommended_monthly_saving, Decimal("2250000"))

    def test_saving_target_is_zero_when_the_exit_is_immediate_and_runway_is_zero(self) -> None:
        result = transition_gap(
            role_name="Data Analyst",
            match_score=Decimal("72"),
            preparation_time_months=Decimal("4"),
            exit_runway_months=Decimal("0"),
            monthly_burn=Decimal("6000000"),
            search_time_months=Decimal("3"),
        )
        self.assertEqual(result.status, "deficit")
        self.assertEqual(result.recommended_monthly_saving, Decimal("0"))

    def test_exactly_zero_gap_counts_as_surplus(self) -> None:
        result = transition_gap(
            role_name="Data Analyst",
            match_score=Decimal("72"),
            preparation_time_months=Decimal("4"),
            exit_runway_months=Decimal("7"),
            monthly_burn=Decimal("6000000"),
            search_time_months=Decimal("3"),
        )
        self.assertEqual(result.transition_gap_months, Decimal("0"))
        self.assertEqual(result.status, "surplus")


class PreparationTimeTests(TestCase):
    def test_preparation_scales_with_gap_count(self) -> None:
        self.assertEqual(preparation_months_for_gap_count(0), 1)
        self.assertEqual(preparation_months_for_gap_count(1), 2)
        self.assertEqual(preparation_months_for_gap_count(2), 3)
        self.assertEqual(preparation_months_for_gap_count(4), 6)

    def test_preparation_is_clamped(self) -> None:
        self.assertEqual(preparation_months_for_gap_count(-5), MIN_PREPARATION_MONTHS)
        self.assertEqual(
            preparation_months_for_gap_count(99), MAX_PREPARATION_MONTHS
        )

    def test_closing_one_gap_reports_months_saved(self) -> None:
        self.assertEqual(months_saved_by_closing_one_gap(1), Decimal("0"))
        self.assertEqual(months_saved_by_closing_one_gap(0), Decimal("0"))
        # 4 gaps -> 6 months; 3 gaps -> 5 months.
        self.assertEqual(months_saved_by_closing_one_gap(4), Decimal("1"))

    def test_transition_gap_reports_the_saving_from_closing_a_gap(self) -> None:
        result = transition_gap(
            role_name="Data Analyst",
            match_score=Decimal("72"),
            preparation_time_months=Decimal("6"),
            exit_runway_months=Decimal("8"),
            monthly_burn=Decimal("6000000"),
            gap_count=4,
        )
        self.assertEqual(result.months_saved_by_closing_one_gap, Decimal("1"))


class RoleSelectionTests(TestCase):
    ROLES = [
        ("Data Analyst", Decimal("72"), 4),
        ("Product Manager", Decimal("81"), 9),
        ("QA Engineer", Decimal("65"), 2),
    ]

    def test_default_is_the_highest_match_score_not_the_slowest(self) -> None:
        # The old behaviour took max(preparation) across all roles, which made the slowest
        # option define the outlook for every user.
        role_name, match_score, preparation = select_preparation_role(self.ROLES)
        self.assertEqual(role_name, "Product Manager")
        self.assertEqual(match_score, Decimal("81"))
        self.assertEqual(preparation, 9)

    def test_explicit_choice_wins_and_is_case_insensitive(self) -> None:
        role_name, _, preparation = select_preparation_role(
            self.ROLES, preferred_role_name="  data analyst "
        )
        self.assertEqual(role_name, "Data Analyst")
        self.assertEqual(preparation, 4)

    def test_unknown_choice_falls_back_to_the_highest_match(self) -> None:
        role_name, _, _ = select_preparation_role(
            self.ROLES, preferred_role_name="Astronaut"
        )
        self.assertEqual(role_name, "Product Manager")

    def test_empty_role_list_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            select_preparation_role([])


class ExitTypeIndependenceTests(TestCase):
    def test_the_same_role_yields_different_gaps_per_exit_type(self) -> None:
        runways = {
            ExitType.resign: Decimal("2.50"),
            ExitType.efficiency_due_to_loss: Decimal("10.75"),
            ExitType.efficiency_prevent_loss: Decimal("13.67"),
        }
        gaps = {}
        for exit_type, runway in runways.items():
            gaps[exit_type] = transition_gap(
                role_name="Data Analyst",
                match_score=Decimal("72"),
                preparation_time_months=Decimal("4"),
                exit_runway_months=runway,
                monthly_burn=Decimal("6000000"),
                search_time_months=Decimal("3"),
            ).transition_gap_months
        # The exit ground has to change the answer, otherwise the simulation is cosmetic.
        self.assertEqual(gaps[ExitType.resign], Decimal("-4.50"))
        self.assertEqual(gaps[ExitType.efficiency_due_to_loss], Decimal("3.75"))
        self.assertEqual(gaps[ExitType.efficiency_prevent_loss], Decimal("6.67"))
        self.assertEqual(len(set(gaps.values())), 3)


class SavingsHorizonTests(TestCase):
    """The saving target must never divide the deficit by the runway itself."""

    TODAY = date(2026, 1, 1)

    def test_future_layoff_uses_the_time_until_then(self) -> None:
        # 1 Jan -> 1 Jul 2026 is 181 days; 181 / 30.44 = 5.95 months.
        horizon = savings_horizon(
            date(2026, 7, 1), self.TODAY, fallback=Decimal("12")
        )
        self.assertEqual(horizon, Decimal("5.95"))

    def test_missing_or_past_layoff_uses_the_fallback(self) -> None:
        self.assertEqual(
            savings_horizon(self.TODAY, self.TODAY, fallback=Decimal("12")),
            Decimal("12"),
        )
        self.assertEqual(
            savings_horizon(date(2025, 12, 1), self.TODAY, fallback=Decimal("12")),
            Decimal("12"),
        )

    def test_resignation_without_a_date_targets_twelve_months(self) -> None:
        # The old endpoint passed today as the layoff date, giving horizon 0 and a target
        # of 4.5 * 6jt / 2.5 = 10.8jt. The fallback keeps the paper's 2.25jt.
        horizon = savings_horizon(self.TODAY, self.TODAY, fallback=Decimal("12"))
        result = transition_gap(
            role_name="Data Analyst",
            match_score=Decimal("72"),
            preparation_time_months=Decimal("4"),
            exit_runway_months=Decimal("2.50"),
            monthly_burn=Decimal("6000000"),
            search_time_months=Decimal("3"),
            horizon_months=horizon,
        )
        self.assertEqual(result.recommended_monthly_saving, Decimal("2250000"))
