from unittest import TestCase

from pydantic import ValidationError

from app.models.master import IndustryRead, Page
from app.models.profile import UserProfileUpdate
from main import app


class ProfileSchemaTests(TestCase):
    def test_patch_normalizes_only_supplied_fields(self) -> None:
        payload = UserProfileUpdate(
            full_name="  Joan   Orlando ",
            current_role_name=" Platform   Engineer ",
        )

        self.assertEqual(
            payload.model_dump(exclude_unset=True),
            {
                "full_name": "Joan Orlando",
                "current_role_name": "Platform Engineer",
            },
        )

    def test_patch_rejects_clearing_required_fields(self) -> None:
        for payload in ({"full_name": None}, {"current_role_name": " "}, {"industry_name": None}):
            with self.assertRaises(ValidationError):
                UserProfileUpdate(**payload)

    def test_patch_rejects_unknown_fields(self) -> None:
        with self.assertRaises(ValidationError):
            UserProfileUpdate(full_nam="Joan")


class MasterDataSchemaTests(TestCase):
    def test_page_contract(self) -> None:
        page = Page[IndustryRead](
            items=[IndustryRead(id=1, name="Technology")],
            total=1,
            limit=50,
            offset=0,
        )

        self.assertEqual(page.total, 1)
        self.assertEqual(page.items[0].name, "Technology")


class ProfileMasterRouteTests(TestCase):
    def test_openapi_exposes_profile_and_master_routes(self) -> None:
        paths = app.openapi()["paths"]

        self.assertEqual(set(paths["/api/profile"]), {"get", "patch"})
        for resource in ("industries", "roles", "skills", "tools"):
            self.assertEqual(set(paths[f"/api/master/{resource}"]), {"get"})
