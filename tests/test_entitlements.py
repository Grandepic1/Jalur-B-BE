"""Statutory entitlement and exit-aware runway tests.

The persona numbers come from the fix spec's acceptance table. They are checked exactly,
because the whole point of the module is that it is deterministic and auditable.
"""

from datetime import date
from decimal import Decimal
from unittest import TestCase

from app.core.entitlements import (
    BPS_POVERTY_LINE_PER_CAPITA,
    DEFAULT_SEARCH_TIME_MONTHS,
    REGULATION_VERSION,
    EmploymentType,
    ExitTerms,
    ExitType,
    add_months,
    compute_exit_entitlements,
    contract_duration_months,
    cost_of_living_warning,
    essential_expenses_per_person,
    exit_type_consistency_error,
    jkp_eligibility,
    jkp_monthly_benefit,
    pesangon_months,
    pkwt_compensation,
    runway_layers,
    runway_months,
    severance_final_tax,
    upmk_months,
)


def eligible_terms(exit_type: ExitType, **overrides) -> ExitTerms:
    values = {
        "exit_type": exit_type,
        "monthly_wage_base": Decimal("7000000"),
        "tenure_months": 48,
        "bpjs_tk_active": True,
        "bpjs_contributions_last_24_months": 24,
        "bpjs_consecutive_months": 24,
        "age_years": 30,
        "jkn_active": True,
    }
    values.update(overrides)
    return ExitTerms(**values)


class RaniPersonaTests(TestCase):
    """Upah Rp7 jt, masa kerja 4 tahun, tabungan Rp15 jt, B = Rp6 jt, BPJS eligible."""

    SAVINGS = Decimal("15000000")
    BURN = Decimal("6000000")

    def _runway(self, exit_type: ExitType, tenure_months: int = 48) -> Decimal:
        terms = eligible_terms(exit_type, tenure_months=tenure_months)
        entitlements = compute_exit_entitlements(terms)
        return runway_months(
            liquid_assets=self.SAVINGS + entitlements.liquid_normative,
            monthly_burn=self.BURN,
            jkp_monthly=entitlements.jkp.monthly_benefit,
            jkp_months=entitlements.jkp.months,
        )

    def test_expected_runway_per_exit_type(self) -> None:
        expected = {
            ExitType.resign: Decimal("2.50"),
            ExitType.pkwt_ends_on_schedule: Decimal("3.67"),
            ExitType.bankruptcy: Decimal("5.00"),
            ExitType.efficiency_due_to_loss: Decimal("10.75"),
            ExitType.efficiency_prevent_loss: Decimal("13.67"),
        }
        for exit_type, want in expected.items():
            tenure = 12 if exit_type is ExitType.pkwt_ends_on_schedule else 48
            with self.subTest(exit_type=exit_type.value):
                self.assertEqual(self._runway(exit_type, tenure), want)

    def test_resignation_pays_nothing_but_savings(self) -> None:
        entitlements = compute_exit_entitlements(eligible_terms(ExitType.resign))
        self.assertEqual(entitlements.pesangon_months, Decimal("0"))
        self.assertEqual(entitlements.upmk_months, Decimal("0"))
        self.assertFalse(entitlements.jkp.eligible)
        self.assertEqual(entitlements.liquid_normative, Decimal("0"))

    def test_bankruptcy_treats_normative_rights_as_not_collectable(self) -> None:
        entitlements = compute_exit_entitlements(eligible_terms(ExitType.bankruptcy))
        # Halved pesangon plus full UPMK on paper...
        self.assertEqual(entitlements.pesangon_months, Decimal("2.5"))
        self.assertEqual(entitlements.upmk_months, Decimal("2"))
        # ...but not counted as spendable cash under the conservative default.
        self.assertFalse(entitlements.normative_collectable)
        self.assertEqual(entitlements.liquid_normative, Decimal("0"))
        # JKP is still paid even when the company is insolvent.
        self.assertTrue(entitlements.jkp.eligible)

    def test_bankruptcy_toggle_restores_normative_rights(self) -> None:
        entitlements = compute_exit_entitlements(
            eligible_terms(ExitType.bankruptcy, normative_rights_collectable=True)
        )
        self.assertTrue(entitlements.normative_collectable)
        self.assertEqual(entitlements.liquid_normative, entitlements.net_lump_sum)

    def test_pkwt_compensation_replaces_pesangon(self) -> None:
        terms = eligible_terms(
            ExitType.pkwt_ends_on_schedule,
            tenure_months=12,
            employment_type=EmploymentType.pkwt,
        )
        entitlements = compute_exit_entitlements(terms)
        self.assertEqual(entitlements.gross_lump_sum, Decimal("7000000.00"))
        self.assertFalse(entitlements.jkp.eligible)

    def test_regulation_version_is_recorded(self) -> None:
        entitlements = compute_exit_entitlements(eligible_terms(ExitType.resign))
        self.assertEqual(entitlements.regulation_version, REGULATION_VERSION)


class TenureTableTests(TestCase):
    def test_pesangon_months_follow_pp35_table(self) -> None:
        cases = {
            0: Decimal("1"),
            11: Decimal("1"),
            12: Decimal("2"),
            23: Decimal("2"),
            24: Decimal("3"),
            35: Decimal("3"),
            47: Decimal("4"),
            48: Decimal("5"),
            95: Decimal("8"),
            96: Decimal("9"),
            240: Decimal("9"),
        }
        for tenure, want in cases.items():
            with self.subTest(tenure=tenure):
                self.assertEqual(pesangon_months(tenure), want)

    def test_upmk_starts_at_exactly_three_years(self) -> None:
        self.assertEqual(upmk_months(35), Decimal("0"))
        self.assertEqual(upmk_months(36), Decimal("2"))
        self.assertEqual(upmk_months(72), Decimal("3"))
        self.assertEqual(upmk_months(288), Decimal("10"))
        self.assertEqual(upmk_months(600), Decimal("10"))

    def test_negative_tenure_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            pesangon_months(-1)
        with self.assertRaises(ValueError):
            upmk_months(-1)


class JkpTests(TestCase):
    def test_benefit_is_capped_at_five_million_of_wage(self) -> None:
        self.assertEqual(jkp_monthly_benefit(Decimal("7000000")), Decimal("3000000.00"))
        self.assertEqual(jkp_monthly_benefit(Decimal("20000000")), Decimal("3000000.00"))
        self.assertEqual(jkp_monthly_benefit(Decimal("4000000")), Decimal("2400000.00"))

    def test_eleven_months_of_contributions_disqualifies(self) -> None:
        result = jkp_eligibility(
            exit_type=ExitType.efficiency_prevent_loss,
            monthly_wage=Decimal("7000000"),
            bpjs_tk_active=True,
            bpjs_contributions_last_24_months=11,
            bpjs_consecutive_months=11,
            age_years=30,
            jkn_active=True,
        )
        self.assertFalse(result.eligible)
        self.assertEqual(result.monthly_benefit, Decimal("0"))
        self.assertEqual(result.months, 0)
        self.assertTrue(result.reasons)

    def test_every_failing_condition_is_reported(self) -> None:
        result = jkp_eligibility(
            exit_type=ExitType.resign,
            monthly_wage=Decimal("7000000"),
            bpjs_tk_active=False,
            bpjs_contributions_last_24_months=0,
            bpjs_consecutive_months=0,
            age_years=60,
            jkn_active=False,
        )
        self.assertFalse(result.eligible)
        self.assertEqual(len(result.reasons), 6)

    def test_benefit_runs_for_six_months(self) -> None:
        result = jkp_eligibility(
            exit_type=ExitType.efficiency_due_to_loss,
            monthly_wage=Decimal("7000000"),
            bpjs_tk_active=True,
            bpjs_contributions_last_24_months=24,
            bpjs_consecutive_months=12,
            age_years=30,
            jkn_active=True,
        )
        self.assertTrue(result.eligible)
        self.assertEqual(result.months, 6)
        self.assertEqual(result.total_benefit, Decimal("18000000.00"))


class SeveranceTaxTests(TestCase):
    def test_brackets_are_marginal_not_flat(self) -> None:
        self.assertEqual(severance_final_tax(Decimal("0")), Decimal("0.00"))
        self.assertEqual(severance_final_tax(Decimal("50000000")), Decimal("0.00"))
        # Only the 10 million above the first bracket is taxed at 5%.
        self.assertEqual(severance_final_tax(Decimal("60000000")), Decimal("500000.00"))
        self.assertEqual(
            severance_final_tax(Decimal("100000000")), Decimal("2500000.00")
        )
        # 50m untaxed + 50m at 5% + 400m at 15% = 62.5m
        self.assertEqual(
            severance_final_tax(Decimal("500000000")), Decimal("62500000.00")
        )

    def test_net_lump_sum_subtracts_the_tax(self) -> None:
        terms = eligible_terms(
            ExitType.efficiency_prevent_loss,
            monthly_wage_base=Decimal("15000000"),
            tenure_months=120,
        )
        entitlements = compute_exit_entitlements(terms)
        self.assertEqual(
            entitlements.net_lump_sum,
            entitlements.gross_lump_sum - entitlements.severance_tax,
        )
        self.assertGreater(entitlements.severance_tax, Decimal("0"))


class PkwtCompensationTests(TestCase):
    def test_twelve_months_equals_one_month_of_wage(self) -> None:
        self.assertEqual(
            pkwt_compensation(Decimal("7000000"), 12), Decimal("7000000.00")
        )
        self.assertEqual(pkwt_compensation(Decimal("7000000"), 6), Decimal("3500000.00"))
        self.assertEqual(pkwt_compensation(Decimal("7000000"), 0), Decimal("0.00"))

    def test_negative_months_rejected(self) -> None:
        with self.assertRaises(ValueError):
            pkwt_compensation(Decimal("7000000"), -1)


class PkwtContractDurationTests(TestCase):
    """A renewed PKWT is compensated for the running contract, not total service."""

    def test_compensation_uses_the_running_contract(self) -> None:
        terms = eligible_terms(
            ExitType.pkwt_ends_on_schedule,
            tenure_months=48,
            contract_months=12,
            employment_type=EmploymentType.pkwt,
        )
        entitlements = compute_exit_entitlements(terms)
        # 12/12 x 7jt, not 48/12 x 7jt: the earlier contracts were settled when they ended.
        self.assertEqual(entitlements.gross_lump_sum, Decimal("7000000.00"))

    def test_missing_contract_months_falls_back_to_tenure(self) -> None:
        terms = eligible_terms(
            ExitType.pkwt_ends_on_schedule,
            tenure_months=12,
            employment_type=EmploymentType.pkwt,
        )
        self.assertEqual(
            compute_exit_entitlements(terms).gross_lump_sum, Decimal("7000000.00")
        )


class ContractDurationTests(TestCase):
    def test_whole_months_between_contract_dates(self) -> None:
        self.assertEqual(
            contract_duration_months(date(2025, 1, 1), date(2026, 1, 1)), 12
        )
        self.assertEqual(
            contract_duration_months(date(2025, 1, 15), date(2026, 1, 14)), 11
        )

    def test_missing_bounds_return_none(self) -> None:
        self.assertIsNone(contract_duration_months(None, date(2026, 1, 1)))
        self.assertIsNone(contract_duration_months(date(2025, 1, 1), None))


class RunwayClosedFormTests(TestCase):
    def test_without_benefit_is_plain_division(self) -> None:
        self.assertEqual(
            runway_months(liquid_assets=Decimal("12000000"), monthly_burn=Decimal("6000000")),
            Decimal("2.00"),
        )

    def test_benefit_outlasting_the_money_uses_net_burn(self) -> None:
        # 15m < (6m - 3m) * 6 = 18m, so 15 / 3 = 5.
        self.assertEqual(
            runway_months(
                liquid_assets=Decimal("15000000"),
                monthly_burn=Decimal("6000000"),
                jkp_monthly=Decimal("3000000"),
                jkp_months=6,
            ),
            Decimal("5.00"),
        )

    def test_money_outlasting_the_benefit_adds_the_tail(self) -> None:
        # 6 + (64 - 18) / 6 = 13.67, matching the spec's efficiency table.
        self.assertEqual(
            runway_months(
                liquid_assets=Decimal("64000000"),
                monthly_burn=Decimal("6000000"),
                jkp_monthly=Decimal("3000000"),
                jkp_months=6,
            ),
            Decimal("13.67"),
        )

    def test_benefit_covering_whole_burn_does_not_divide_by_zero(self) -> None:
        value = runway_months(
            liquid_assets=Decimal("12000000"),
            monthly_burn=Decimal("3000000"),
            jkp_monthly=Decimal("3000000"),
            jkp_months=6,
        )
        self.assertEqual(value, Decimal("10.00"))

    def test_invalid_inputs_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            runway_months(liquid_assets=Decimal("1"), monthly_burn=Decimal("0"))
        with self.assertRaises(ValueError):
            runway_months(liquid_assets=Decimal("-1"), monthly_burn=Decimal("1"))


class RunwayLayerTests(TestCase):
    def test_layers_are_stacked_and_monotonic(self) -> None:
        entitlements = compute_exit_entitlements(
            eligible_terms(
                ExitType.efficiency_prevent_loss,
                jht_balance=Decimal("20000000"),
            )
        )
        layers = runway_layers(
            liquid_assets=Decimal("15000000"),
            monthly_burn=Decimal("6000000"),
            entitlements=entitlements,
        )
        self.assertEqual(
            [layer.key for layer in layers],
            ["savings_only", "with_normative_rights", "with_jkp", "with_jht"],
        )
        months = [layer.runway_months for layer in layers]
        self.assertEqual(months, sorted(months))
        # Savings alone never includes a benefit.
        self.assertEqual(layers[0].monthly_benefit, Decimal("0"))
        # Retirement savings are labelled as such.
        self.assertTrue(layers[-1].key == "with_jht")
        self.assertIn("dana pensiun", layers[-1].label)


class ExitTypeConsistencyTests(TestCase):
    def test_pkwt_expiry_requires_a_fixed_term_contract(self) -> None:
        self.assertIsNotNone(
            exit_type_consistency_error(
                ExitType.pkwt_ends_on_schedule, EmploymentType.pkwtt
            )
        )
        self.assertIsNone(
            exit_type_consistency_error(
                ExitType.pkwt_ends_on_schedule, EmploymentType.pkwt
            )
        )

    def test_other_exit_grounds_apply_to_both_contract_types(self) -> None:
        for exit_type in ExitType:
            if exit_type is ExitType.pkwt_ends_on_schedule:
                continue
            for employment_type in EmploymentType:
                with self.subTest(exit_type=exit_type.value, contract=employment_type.value):
                    self.assertIsNone(
                        exit_type_consistency_error(exit_type, employment_type)
                    )


class DateHelperTests(TestCase):
    def test_whole_months_are_calendar_aware(self) -> None:
        self.assertEqual(add_months(date(2026, 1, 15), Decimal("1")), date(2026, 2, 15))
        self.assertEqual(add_months(date(2026, 1, 15), Decimal("12")), date(2027, 1, 15))

    def test_month_end_is_clamped(self) -> None:
        self.assertEqual(add_months(date(2026, 1, 31), Decimal("1")), date(2026, 2, 28))

    def test_fractional_months_become_days(self) -> None:
        # 0.75 * 30.44 rounds to 23 days, so 1 Jan + 23 days is 24 Jan.
        value = add_months(date(2026, 1, 1), Decimal("0.75"))
        self.assertEqual(value.month, 1)
        self.assertEqual(value.day, 24)

    def test_zero_months_is_a_no_op(self) -> None:
        self.assertEqual(add_months(date(2026, 5, 5), Decimal("0")), date(2026, 5, 5))


class CostOfLivingTests(TestCase):
    def test_per_person_divides_by_household_size(self) -> None:
        self.assertEqual(
            essential_expenses_per_person(Decimal("6000000"), 2), Decimal("2000000.00")
        )

    def test_plausible_spend_produces_no_warning(self) -> None:
        self.assertIsNone(cost_of_living_warning(Decimal("6000000"), 2))

    def test_implausibly_low_spend_warns(self) -> None:
        # 900,000 across three people is 300,000 per person, well below the poverty line.
        warning = cost_of_living_warning(Decimal("900000" ), 2)
        self.assertIsNotNone(warning)
        self.assertIn("garis kemiskinan", warning)

    def test_threshold_matches_the_published_constant(self) -> None:
        at_line = BPS_POVERTY_LINE_PER_CAPITA
        self.assertIsNone(cost_of_living_warning(at_line, 0))
        self.assertIsNotNone(cost_of_living_warning(at_line - 1, 0))


class SearchTimeAssumptionTests(TestCase):
    def test_search_time_default_is_visible_and_non_zero(self) -> None:
        self.assertGreater(DEFAULT_SEARCH_TIME_MONTHS, Decimal("0"))
