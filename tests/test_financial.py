from decimal import Decimal
from unittest import IsolatedAsyncioTestCase, TestCase

from pydantic import ValidationError

from app.api.financial import (
    REFERENCE_RUNWAY_MONTHS,
    _financial_readiness_for,
    _runway_preview,
)
from app.models.financial import (
    FinancialAssetCreate,
    FinancialAssetType,
    FinancialAssetUpdate,
    FinancialProfile,
    FinancialProfileCreate,
    LiquidityLevel,
)
from main import app


class FinancialSchemaTests(TestCase):
    def test_profile_normalizes_currency_and_rejects_derived_totals(self) -> None:
        profile = FinancialProfileCreate(
            monthly_essential_expenses="4000000.00",
            monthly_debt_payment="1000000.00",
            dependents=2,
            currency="idr",
        )

        self.assertEqual(profile.currency, "IDR")
        with self.assertRaises(ValidationError):
            FinancialProfileCreate(
                monthly_essential_expenses=Decimal("4000000"),
                available_savings=Decimal("10000000"),
            )

    def test_asset_requires_positive_amount_and_valid_currency(self) -> None:
        valid = {
            "name": " Emergency Fund ",
            "amount": Decimal("10000000"),
            "asset_type": FinancialAssetType.emergency_fund,
            "liquidity": LiquidityLevel.liquid,
            "currency": "idr",
        }
        asset = FinancialAssetCreate(**valid)

        self.assertEqual(asset.name, "Emergency Fund")
        self.assertEqual(asset.currency, "IDR")
        with self.assertRaises(ValidationError):
            FinancialAssetCreate(**{**valid, "amount": Decimal("0")})
        with self.assertRaises(ValidationError):
            FinancialAssetCreate(**{**valid, "currency": "12$"})

    def test_asset_patch_allows_clearing_note_but_not_required_fields(self) -> None:
        self.assertEqual(
            FinancialAssetUpdate(note=None).model_dump(exclude_unset=True),
            {"note": None},
        )
        for payload in ({"name": None}, {"amount": None}, {"liquidity": None}):
            with self.assertRaises(ValidationError):
                FinancialAssetUpdate(**payload)


class RunwayCalculationTests(IsolatedAsyncioTestCase):
    def _profile(self) -> FinancialProfile:
        return FinancialProfile(
            user_id=1,
            available_savings=Decimal("10000000"),
            monthly_essential_expenses=Decimal("4000000"),
            monthly_debt_payment=Decimal("1000000"),
            dependents=1,
            other_liquid_funds=Decimal("0"),
            currency="IDR",
        )

    async def test_runway_uses_only_liquid_assets_and_total_monthly_burn(self) -> None:
        profile = self._profile()

        preview = await _runway_preview(
            profile,
            Decimal("20000000"),
            Decimal("10000000"),
            REFERENCE_RUNWAY_MONTHS,
        )

        self.assertEqual(preview.monthly_burn, Decimal("5000000"))
        self.assertEqual(preview.financial_runway_months, Decimal("2.00"))
        self.assertEqual(preview.runway_gap_months, Decimal("4.00"))
        # The flat six-month line is reported separately and no longer drives the score.
        self.assertEqual(preview.reference_runway_months, REFERENCE_RUNWAY_MONTHS)
        self.assertEqual(preview.target_runway_months, REFERENCE_RUNWAY_MONTHS)
        self.assertEqual(preview.target_basis, "reference_default_no_pivot_analysis")

    async def test_runway_gap_uses_the_personal_target(self) -> None:
        profile = self._profile()

        preview = await _runway_preview(
            profile,
            Decimal("20000000"),
            Decimal("10000000"),
            Decimal("10"),
            target_basis="pivot_preparation_plus_search",
        )

        self.assertEqual(preview.target_runway_months, Decimal("10"))
        self.assertEqual(preview.runway_gap_months, Decimal("8.00"))
        self.assertEqual(preview.target_basis, "pivot_preparation_plus_search")

    async def test_financial_readiness_tracks_liquidity_target_and_burn(self) -> None:
        profile = self._profile()

        self.assertEqual(
            _financial_readiness_for(
                profile, Decimal("15000000"), Decimal("6"), None
            ),
            Decimal("50.00"),
        )
        self.assertEqual(
            _financial_readiness_for(
                profile, Decimal("30000000"), Decimal("6"), None
            ),
            Decimal("100.00"),
        )
        # A longer personal target lowers readiness for the same savings.
        self.assertEqual(
            _financial_readiness_for(
                profile, Decimal("30000000"), Decimal("12"), None
            ),
            Decimal("50.00"),
        )

    async def test_implausibly_low_expenses_are_flagged(self) -> None:
        profile = self._profile()
        profile.monthly_essential_expenses = Decimal("900000")
        profile.dependents = 2

        preview = await _runway_preview(
            profile,
            Decimal("10000000"),
            Decimal("10000000"),
            REFERENCE_RUNWAY_MONTHS,
        )

        self.assertIsNotNone(preview.cost_of_living_warning)
        self.assertIsNotNone(preview.poverty_line_version)


class FinancialRouteTests(TestCase):
    def test_openapi_exposes_financial_contract(self) -> None:
        paths = app.openapi()["paths"]

        self.assertEqual(set(paths["/api/financial"]), {"get", "put"})
        self.assertEqual(set(paths["/api/financial/assets"]), {"get", "post"})
        self.assertEqual(
            set(paths["/api/financial/assets/{asset_id}"]), {"get", "patch", "delete"}
        )
        self.assertEqual(set(paths["/api/financial/runway"]), {"get", "post"})
        self.assertEqual(set(paths["/api/financial/runway/latest"]), {"get"})
        self.assertEqual(set(paths["/api/financial/runway/history"]), {"get"})
        self.assertEqual(
            set(paths["/api/financial/employment-terms"]), {"get", "put"}
        )
        self.assertEqual(set(paths["/api/financial/exit-runway"]), {"post"})
        self.assertEqual(set(paths["/api/financial/exit-runway/latest"]), {"get"})
