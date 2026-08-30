from decimal import Decimal
from unittest import TestCase

from pydantic import ValidationError

from app.api.evidence import MAX_ATTACHMENT_BYTES, detect_attachment_type
from app.models.auth import DeleteAccountRequest, EmailChangeRequest, UsernameUpdateRequest
from app.models.evidence import EvidenceItemCreate, EvidenceItemUpdate, EvidenceType
from app.models.missions import MissionStatus, SkillMissionCreate, SkillMissionUpdate
from app.models.user_skills import UserSkillUpdate
from main import app


class EvidenceSchemaTests(TestCase):
    def test_human_evidence_normalizes_required_text(self) -> None:
        evidence = EvidenceItemCreate(
            evidence_type=EvidenceType.project,
            title="  Platform   migration ",
            user_role=" Engineer ",
            description=" Migrated  the platform ",
            impact=" Reduced  incidents ",
        )

        self.assertEqual(evidence.title, "Platform migration")
        self.assertFalse(evidence.ai_generated)

    def test_evidence_impact_is_optional_and_clearable(self) -> None:
        evidence = EvidenceItemCreate(
            evidence_type=EvidenceType.project,
            title="Migration",
            user_role="Engineer",
            description="Migrated the platform",
        )
        self.assertIsNone(evidence.impact)
        self.assertEqual(
            EvidenceItemUpdate(impact=None).model_dump(exclude_unset=True),
            {"impact": None},
        )

    def test_human_endpoint_rejects_ai_flag_and_external_attachment_url(self) -> None:
        base = {
            "evidence_type": EvidenceType.project,
            "title": "Migration",
            "user_role": "Engineer",
            "description": "Migrated the platform",
            "impact": "Reduced incidents",
        }
        with self.assertRaises(ValidationError):
            EvidenceItemCreate(**base, ai_generated=True)
        with self.assertRaises(ValidationError):
            EvidenceItemCreate(**base, attachment_url="https://example.com/file.pdf")

    def test_evidence_patch_clears_optional_fields_only(self) -> None:
        self.assertEqual(
            EvidenceItemUpdate(evidence_date=None).model_dump(exclude_unset=True),
            {"evidence_date": None},
        )
        with self.assertRaises(ValidationError):
            EvidenceItemUpdate(title=None)

    def test_attachment_type_uses_file_signature(self) -> None:
        self.assertEqual(detect_attachment_type(b"%PDF-1.7"), ("application/pdf", ".pdf"))
        self.assertEqual(
            detect_attachment_type(b"\x89PNG\r\n\x1a\ncontent"),
            ("image/png", ".png"),
        )
        self.assertEqual(
            detect_attachment_type(b"RIFF\x00\x00\x00\x00WEBPcontent"),
            ("image/webp", ".webp"),
        )
        self.assertIsNone(detect_attachment_type(b"RIFF-not-webp"))
        self.assertIsNone(detect_attachment_type(b"plain text"))
        self.assertEqual(MAX_ATTACHMENT_BYTES, 10 * 1024 * 1024)


class MissionSchemaTests(TestCase):
    def test_mission_is_user_authored_and_status_is_explicit(self) -> None:
        mission = SkillMissionCreate(
            title="  Complete   SQL course ",
            status=MissionStatus.in_progress,
        )

        self.assertEqual(mission.title, "Complete SQL course")
        self.assertIs(mission.status, MissionStatus.in_progress)

    def test_mission_patch_rejects_null_required_fields(self) -> None:
        for payload in ({"title": None}, {"status": None}):
            with self.assertRaises(ValidationError):
                SkillMissionUpdate(**payload)


class UserSkillSchemaTests(TestCase):
    def test_skill_proficiency_matches_database_capacity(self) -> None:
        skill = UserSkillUpdate(
            proficiency_level=5,
            years_experience=Decimal("99.9"),
        )

        self.assertEqual(skill.years_experience, Decimal("99.9"))
        with self.assertRaises(ValidationError):
            UserSkillUpdate(years_experience=Decimal("100"))


class AccountSchemaTests(TestCase):
    def test_username_policy_and_sensitive_requests(self) -> None:
        self.assertEqual(UsernameUpdateRequest(username=" user.name ").username, "user.name")
        with self.assertRaises(ValidationError):
            UsernameUpdateRequest(username="invalid name")

        email = EmailChangeRequest(
            email="new@example.com",
            current_password="current-password",
        )
        deletion = DeleteAccountRequest(current_password="current-password")
        self.assertEqual(str(email.email), "new@example.com")
        self.assertEqual(deletion.current_password, "current-password")


class NonAiRouteTests(TestCase):
    def test_openapi_exposes_non_ai_feature_contracts(self) -> None:
        paths = app.openapi()["paths"]

        self.assertEqual(set(paths["/api/evidence"]), {"get", "post"})
        self.assertEqual(set(paths["/api/evidence/stats"]), {"get"})
        self.assertEqual(
            set(paths["/api/evidence/{evidence_id}"]), {"get", "patch", "delete"}
        )
        self.assertEqual(
            set(paths["/api/evidence/{evidence_id}/attachment"]), {"post", "delete"}
        )
        self.assertEqual(set(paths["/api/missions"]), {"get", "post"})
        self.assertEqual(set(paths["/api/missions/progress"]), {"get"})
        self.assertEqual(
            set(paths["/api/missions/{mission_id}"]), {"get", "patch", "delete"}
        )
        self.assertEqual(set(paths["/api/profile/skills"]), {"get"})
        self.assertEqual(
            set(paths["/api/profile/skills/{skill_id}"]), {"put", "delete"}
        )
        self.assertEqual(set(paths["/api/dashboard"]), {"get"})
        self.assertEqual(set(paths["/api/auth/username"]), {"patch"})
        self.assertEqual(set(paths["/api/auth/change-email"]), {"post"})
        self.assertEqual(set(paths["/api/auth/account"]), {"delete"})

    def test_openapi_exposes_deterministic_financial_extensions(self) -> None:
        paths = app.openapi()["paths"]

        self.assertEqual(set(paths["/api/financial/assets/summary"]), {"get"})
        self.assertEqual(set(paths["/api/financial/runway/preview"]), {"post"})
        self.assertEqual(set(paths["/api/financial/runway/trend"]), {"get"})
