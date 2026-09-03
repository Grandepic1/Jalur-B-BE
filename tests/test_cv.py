from datetime import UTC, datetime, timedelta
from hashlib import sha256
from io import BytesIO
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from docx import Document
from fastapi import HTTPException, UploadFile
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.cv import (
    _create_preview_token,
    _decode_preview_token,
    confirm_cv,
    preview_cv,
)
from app.core.config import settings
from app.core.cv_extraction import (
    DOCX_CONTENT_TYPE,
    MAX_CV_TEXT_CHARS,
    PDF_CONTENT_TYPE,
    CVExtractionError,
    detect_cv_type,
    extract_cv_text,
)
from app.models.cv import (
    CVExperience,
    CVExtractionAIResult,
    CVPreviewTokenData,
    UserCV,
)
from app.models.master import Skill
from app.models.profile import UserProfile


class CVExtractionTests(TestCase):
    def test_freelance_experience_can_omit_company_and_details(self) -> None:
        experience = CVExperience(
            role="Freelancer",
            company=None,
            start_date=None,
            end_date=None,
            description=None,
        )

        self.assertIsNone(experience.company)
        self.assertIsNone(experience.description)

    def test_profile_and_skills_are_normalized_for_preview(self) -> None:
        extraction = CVExtractionAIResult(
            profile={
                "full_name": "  Joan   Orlando ",
                "current_role_name": " Backend Engineer ",
                "industry_name": None,
                "work_duration_months": 24,
                "daily_activities": "  Membangun API dan menjaga layanan produksi. ",
            },
            skills=[" Python ", "python", " API Design "],
            experiences=[],
        )

        self.assertEqual(extraction.profile.full_name, "Joan Orlando")
        self.assertEqual(extraction.skills, ["Python", "API Design"])

    def test_preview_token_data_rejects_unknown_fields(self) -> None:
        with self.assertRaises(ValidationError):
            CVPreviewTokenData(
                preview_id=uuid4(),
                user_id=7,
                file_name="resume.pdf",
                file_size=10,
                content_type=PDF_CONTENT_TYPE,
                file_sha256="a" * 64,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
                profile={},
                skills=[],
                experiences=[],
                model="test-model",
                unknown="Untrusted override",
            )

    def test_experience_rejects_a_whitespace_only_role(self) -> None:
        with self.assertRaises(ValidationError):
            CVExperience(role="   ")

    def test_detects_supported_file_signatures(self) -> None:
        self.assertEqual(
            detect_cv_type(b"%PDF-1.7 content", "resume.PDF"),
            (PDF_CONTENT_TYPE, ".pdf"),
        )
        self.assertEqual(
            detect_cv_type(b"PK\x03\x04 content", "resume.docx"),
            (DOCX_CONTENT_TYPE, ".docx"),
        )
        self.assertIsNone(detect_cv_type(b"PK\x03\x04 content", "resume.doc"))
        self.assertIsNone(detect_cv_type(b"not a pdf", "resume.pdf"))

    def test_extracts_and_normalizes_docx_text(self) -> None:
        document = Document()
        document.add_heading("Riwayat Karier", level=1)
        document.add_paragraph(
            "Backend Engineer di Contoh Digital dari 2023 sampai sekarang."
        )
        document.add_paragraph(
            "Membangun API, menjaga layanan produksi, dan mempercepat deployment."
        )
        stream = BytesIO()
        document.save(stream)

        text = extract_cv_text(stream.getvalue(), DOCX_CONTENT_TYPE)

        self.assertIn("Backend Engineer di Contoh Digital", text)
        self.assertNotIn("  ", text)
        self.assertLessEqual(len(text), MAX_CV_TEXT_CHARS)

    def test_rejects_docx_without_meaningful_text(self) -> None:
        document = Document()
        document.add_paragraph("CV")
        stream = BytesIO()
        document.save(stream)

        with self.assertRaisesRegex(CVExtractionError, "too little readable text"):
            extract_cv_text(stream.getvalue(), DOCX_CONTENT_TYPE)

    def test_rejects_docx_that_expands_beyond_limit(self) -> None:
        document = Document()
        document.add_paragraph(
            "Backend Engineer dengan pengalaman membangun dan menjaga layanan produksi."
        )
        stream = BytesIO()
        document.save(stream)

        with (
            patch("app.core.cv_extraction.MAX_DOCX_UNCOMPRESSED_BYTES", 1),
            self.assertRaisesRegex(CVExtractionError, "safe limit"),
        ):
            extract_cv_text(stream.getvalue(), DOCX_CONTENT_TYPE)


class CVConfirmationTests(IsolatedAsyncioTestCase):
    async def test_preview_returns_signed_result_without_persisting(self) -> None:
        document = Document()
        document.add_paragraph(
            "Joan Orlando, Backend Engineer dengan pengalaman membangun API produksi."
        )
        stream = BytesIO()
        document.save(stream)
        upload = UploadFile(filename="resume.docx", file=BytesIO(stream.getvalue()))
        extraction = CVExtractionAIResult(
            profile={
                "full_name": "Joan Orlando",
                "current_role_name": "Backend Engineer",
                "industry_name": None,
                "work_duration_months": None,
                "daily_activities": "Membangun dan menjaga API produksi.",
            },
            skills=["API Design"],
            experiences=[],
        )
        provider = MagicMock(model="test-model")
        provider.generate_structured = AsyncMock(return_value=extraction)
        db = MagicMock(spec=AsyncSession)
        db.scalar = AsyncMock(side_effect=[11])
        db.rollback = AsyncMock()

        with patch.object(settings, "jwt_secret_key", "x" * 64):
            response = await preview_cv(
                upload,
                SimpleNamespace(id=7),
                db,
                provider,
            )

        with patch.object(settings, "jwt_secret_key", "x" * 64):
            token_data = _decode_preview_token(response.preview_token)
        self.assertEqual(response.profile.full_name, "Joan Orlando")
        self.assertEqual(response.skills, ["API Design"])
        self.assertEqual(token_data.preview_id, response.preview_id)
        self.assertEqual(token_data.file_name, "resume.docx")
        db.add.assert_not_called()

    async def test_confirmation_retry_returns_the_already_applied_result(self) -> None:
        now = datetime.now(UTC)
        preview_id = uuid4()
        content = b"%PDF-1.7 fake cv content"
        preview = CVPreviewTokenData(
            preview_id=preview_id,
            user_id=7,
            file_name="resume.pdf",
            file_size=len(content),
            content_type=PDF_CONTENT_TYPE,
            file_sha256=sha256(content).hexdigest(),
            expires_at=now + timedelta(hours=1),
            profile={},
            skills=[],
            experiences=[],
            model="test-model",
        )
        cv = UserCV(
            id=3,
            user_id=7,
            file_name="resume.pdf",
            file_size=len(content),
            content_type=PDF_CONTENT_TYPE,
            storage_object_path=f"users/7/cv/{preview_id.hex}.pdf",
            source_preview_id=preview_id,
            experiences=[],
            provider_model="test-model",
            uploaded_at=now,
        )
        profile = UserProfile(
            id=11,
            user_id=7,
            full_name="Joan Orlando",
            current_role_name="Backend Engineer",
            industry_name="Technology",
            work_duration_months=24,
            is_first_job=False,
            daily_activities="Membangun dan menjaga API produksi.",
            career_goal=None,
            target_role_name=None,
            target_industry_name=None,
            onboarding_completed_at=now,
            created_at=now,
            updated_at=now,
        )
        db = MagicMock(spec=AsyncSession)
        db.scalar = AsyncMock(side_effect=[SimpleNamespace(), cv, profile])
        db.scalars = AsyncMock(side_effect=[SimpleNamespace(all=lambda: [])])

        with patch.object(settings, "jwt_secret_key", "x" * 64):
            token = _create_preview_token(preview)
            response = await confirm_cv(
                token,
                UploadFile(filename="resume.pdf", file=BytesIO(content)),
                SimpleNamespace(id=7),
                db,
            )

        self.assertEqual(response.cv.file_name, "resume.pdf")
        db.commit.assert_not_called()

    async def test_consumed_superseded_preview_cannot_be_replayed(self) -> None:
        now = datetime.now(UTC)
        preview_id = uuid4()
        content = b"%PDF-1.7 fake cv content"
        preview = CVPreviewTokenData(
            preview_id=preview_id,
            user_id=7,
            file_name="resume.pdf",
            file_size=len(content),
            content_type=PDF_CONTENT_TYPE,
            file_sha256=sha256(content).hexdigest(),
            expires_at=now + timedelta(hours=1),
            profile={},
            skills=[],
            experiences=[],
            model="test-model",
        )
        current_cv = UserCV(
            id=3,
            user_id=7,
            file_name="new-resume.pdf",
            file_size=len(content),
            content_type=PDF_CONTENT_TYPE,
            storage_object_path="users/7/cv/newer.pdf",
            source_preview_id=uuid4(),
            experiences=[],
            provider_model="test-model",
            uploaded_at=now,
        )
        db = MagicMock(spec=AsyncSession)
        db.scalar = AsyncMock(side_effect=[SimpleNamespace(), current_cv])

        with (
            patch.object(settings, "jwt_secret_key", "x" * 64),
            self.assertRaises(HTTPException) as raised,
        ):
            token = _create_preview_token(preview)
            await confirm_cv(
                token,
                UploadFile(filename="resume.pdf", file=BytesIO(content)),
                SimpleNamespace(id=7),
                db,
            )

        self.assertEqual(raised.exception.status_code, 409)
        db.commit.assert_not_called()

    async def test_confirmation_applies_profile_skills_and_history_atomically(
        self,
    ) -> None:
        now = datetime.now(UTC)
        content = b"%PDF-1.7 fake cv content"
        preview = CVPreviewTokenData(
            preview_id=uuid4(),
            user_id=7,
            file_name="resume.pdf",
            file_size=len(content),
            content_type=PDF_CONTENT_TYPE,
            file_sha256=sha256(content).hexdigest(),
            profile={
                "full_name": "Joan Orlando",
                "current_role_name": "Backend Engineer",
                "industry_name": "Technology",
                "work_duration_months": 24,
                "daily_activities": "Membangun API dan menjaga layanan produksi.",
            },
            skills=["Python"],
            experiences=[
                {
                    "role": "Backend Engineer",
                    "company": "Contoh Digital",
                    "start_date": "2023",
                    "end_date": "Sekarang",
                    "description": "Membangun API dan menjaga layanan produksi.",
                }
            ],
            expires_at=now + timedelta(hours=1),
            model="test-model",
        )
        profile = UserProfile(
            id=11,
            user_id=7,
            full_name="Old Name",
            current_role_name="Old Role",
            industry_name="Old Industry",
            work_duration_months=1,
            is_first_job=False,
            daily_activities="Old activities",
            career_goal=None,
            target_role_name=None,
            target_industry_name=None,
            onboarding_completed_at=now,
            created_at=now,
            updated_at=now,
        )
        skill = Skill(
            id=5,
            name="Python",
            category="technical",
            market_trend="stable",
        )
        db = MagicMock(spec=AsyncSession)
        db.scalar = AsyncMock(
            side_effect=[None, 7, None, SimpleNamespace(), profile, None]
        )
        db.scalars = AsyncMock(
            side_effect=[
                SimpleNamespace(all=lambda: [skill]),
                SimpleNamespace(all=lambda: [skill]),
            ]
        )
        db.execute = AsyncMock()
        db.delete = AsyncMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        db.refresh = AsyncMock()
        db.flush = AsyncMock()
        storage = MagicMock()

        with (
            patch.object(settings, "jwt_secret_key", "x" * 64),
            patch("app.api.cv.get_private_storage", return_value=storage),
        ):
            token = _create_preview_token(preview)
            response = await confirm_cv(
                token,
                UploadFile(filename="resume.pdf", file=BytesIO(content)),
                SimpleNamespace(id=7),
                db,
            )

        self.assertEqual(profile.full_name, "Joan Orlando")
        self.assertEqual(profile.current_role_name, "Backend Engineer")
        self.assertEqual(response.cv.experiences[0].role, "Backend Engineer")
        self.assertEqual([item.name for item in response.skills], ["Python"])
        saved_cv = next(
            call.args[0]
            for call in db.add.call_args_list
            if isinstance(call.args[0], UserCV)
        )
        self.assertIsInstance(saved_cv, UserCV)
        self.assertTrue(
            saved_cv.storage_object_path.startswith(
                f"users/7/cv/staging/{preview.preview_id.hex}/"
            )
        )
        self.assertTrue(saved_cv.storage_object_path.endswith(".pdf"))
        self.assertEqual(saved_cv.source_preview_id, preview.preview_id)
        self.assertEqual(db.execute.await_count, 4)
        storage.upload.assert_called_once()
        self.assertEqual(db.commit.await_count, 2)
