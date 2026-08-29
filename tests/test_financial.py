from decimal import Decimal
from unittest import TestCase

from pydantic import ValidationError

from app.api.financial import _runway_preview
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


class RunwayCalculationTests(TestCase):
    def test_runway_uses_only_liquid_assets_and_total_monthly_burn(self) -> None:
        profile = FinancialProfile(
            user_id=1,
            available_savings=Decimal("10000000"),
            monthly_essential_expenses=Decimal("4000000"),
            monthly_debt_payment=Decimal("1000000"),
            dependents=1,
            other_liquid_funds=Decimal("0"),
            currency="IDR",
        )

        preview = _runway_preview(
            profile,
            total_assets=Decimal("20000000"),
            liquid_assets=Decimal("10000000"),
        )

        self.assertEqual(preview.monthly_burn, Decimal("5000000"))
        self.assertEqual(preview.financial_runway_months, Decimal("2.00"))
        self.assertEqual(preview.runway_gap_months, Decimal("4.00"))


class FinancialRouteTests(TestCase):
    def test_openapi_exposes_financial_contract(self) -> None:
        paths = app.openapi()["paths"]

        self.assertEqual(set(paths["/api/financial"]), {"get", "put"})
        self.assertEqual(set(paths["/api/financial/assets"]), {"get", "post"})
        self.assertEqual(
            set(paths["/api/financial/assets/{asset_id}"]), {"patch", "delete"}
        )
        self.assertEqual(set(paths["/api/financial/runway"]), {"get", "post"})
        self.assertEqual(set(paths["/api/financial/runway/latest"]), {"get"})
        self.assertEqual(set(paths["/api/financial/runway/history"]), {"get"})
