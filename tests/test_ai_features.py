import json
from decimal import Decimal
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from pydantic import ValidationError

from app.api.ai_assessments import _load_context
from app.api.layoff_simulations import _naturalize_narrative
from app.core.ai import (
    AIProviderResponseError,
    GeminiProvider,
)
from app.core.config import settings
from app.core.scoring import (
    career_health,
    financial_readiness,
    health_level,
    risk_level,
    weighted,
)
from app.models.ai_features import (
    MAX_ASSESSMENT_SKILLS,
    CareerAnalysisAIResult,
    CareerAssessmentRequest,
    EvidenceAssistantDraft,
)
from app.models.market_baseline import (
    MarketBaselineAIResult,
    MarketBaselineRefreshRequest,
    MarketSignalDraft,
)
from main import app


class ScoringTests(TestCase):
    def test_financial_readiness_matches_six_month_target(self) -> None:
        self.assertEqual(
            financial_readiness(Decimal("3.1"), Decimal("6")),
            Decimal("51.67"),
        )

    def test_weighted_scores_are_bounded_and_rounded(self) -> None:
        self.assertEqual(
            weighted(
                [
                    (Decimal("80"), Decimal("0.25")),
                    (Decimal("60"), Decimal("0.75")),
                ]
            ),
            Decimal("65.00"),
        )
        self.assertEqual(health_level(Decimal("75")), "high")
        self.assertEqual(health_level(Decimal("60")), "medium")
        self.assertEqual(risk_level(Decimal("40")), "medium")
        self.assertEqual(risk_level(Decimal("70")), "high")

    def test_current_financial_readiness_changes_career_health(self) -> None:
        common = {
            "performance_growth": Decimal("80"),
            "skill_relevance": Decimal("80"),
            "adaptability": Decimal("80"),
            "mobility": Decimal("80"),
        }
        self.assertEqual(
            career_health(**common, financial_readiness_score=Decimal("50")),
            Decimal("74.00"),
        )
        self.assertEqual(
            career_health(**common, financial_readiness_score=Decimal("100")),
            Decimal("84.00"),
        )


class AiRouteContractTests(TestCase):
    def test_openapi_exposes_all_ai_features(self) -> None:
        paths = app.openapi()["paths"]
        expected = {
            "/api/ai/assessments": {"post"},
            "/api/ai-exposure": {"post"},
            "/api/ai-exposure/latest": {"get"},
            "/api/career-risk": {"post"},
            "/api/career-risk/latest": {"get"},
            "/api/career-pivot": {"post"},
            "/api/career-pivot/latest": {"get"},
            "/api/career-health": {"post"},
            "/api/career-health/latest": {"get"},
            "/api/layoff-simulations": {"post"},
            "/api/layoff-simulations/latest": {"get"},
            "/api/evidence/assistant/draft": {"post"},
            "/api/evidence/assistant": {"post"},
            "/api/ai/insights": {"get"},
            "/api/market-baselines": {"get"},
            "/api/market-baselines/current": {"get"},
            "/api/market-baselines/refresh": {"post"},
            "/api/market-baselines/{baseline_id}/approve": {"post"},
            "/api/market-baselines/{baseline_id}/reject": {"post"},
            "/api/profile/cv": {"get"},
            "/api/profile/cv/preview": {"post"},
            "/api/profile/cv/confirm": {"post"},
        }
        for path, methods in expected.items():
            self.assertIn(path, paths)
            self.assertEqual(set(paths[path]), methods)


class AssessmentContextTests(IsolatedAsyncioTestCase):
    async def test_rejects_profiles_beyond_the_supported_skill_limit(self) -> None:
        db = MagicMock()
        db.scalar = AsyncMock(
            return_value=SimpleNamespace(
                current_role_name="Engineer",
                industry_name="Technology",
                daily_activities="Maintain systems",
                work_duration_months=24,
            )
        )
        skill_result = MagicMock()
        skill_result.all.return_value = [
            SimpleNamespace(id=index, name=f"Skill {index}")
            for index in range(MAX_ASSESSMENT_SKILLS + 1)
        ]
        db.scalars = AsyncMock(return_value=skill_result)

        with self.assertRaisesRegex(HTTPException, "support at most") as raised:
            await _load_context(
                db,
                user_id=1,
                payload=CareerAssessmentRequest(),
            )

        self.assertEqual(raised.exception.status_code, 422)


class GeminiProviderTests(IsolatedAsyncioTestCase):
    def test_career_analysis_supports_cv_expanded_skill_profiles(self) -> None:
        schema = CareerAnalysisAIResult.model_json_schema()

        self.assertEqual(
            schema["properties"]["skills"]["maxItems"],
            MAX_ASSESSMENT_SKILLS,
        )
        self.assertGreaterEqual(MAX_ASSESSMENT_SKILLS, 28)

    def test_career_analysis_requires_substantive_text(self) -> None:
        schema = CareerAnalysisAIResult.model_json_schema()

        self.assertEqual(schema["properties"]["health_summary"]["minLength"], 80)
        self.assertEqual(
            schema["$defs"]["SignalResult"]["properties"]["reason"]["minLength"],
            40,
        )

    def test_layoff_narrative_hides_internal_identifiers(self) -> None:
        value = _naturalize_narrative(
            "Skenario one_month memiliki overall_resilience 75 dan "
            "financial_readiness kuat dengan runway_months 12. "
            "unknown_internal_field tidak boleh memakai garis bawah."
        )

        self.assertNotIn("_", value)
        self.assertIn("satu bulan", value)
        self.assertIn("ketahanan keseluruhan", value)
        self.assertIn("kesiapan finansial", value)
        self.assertIn("masa aman finansial", value)

    async def test_structured_response_is_validated(self) -> None:
        client = MagicMock()
        client.models.generate_content = AsyncMock(
            return_value=SimpleNamespace(
                text=json.dumps(
                    {
                        "title": "Migrasi platform",
                        "description": "Memigrasikan platform.",
                        "impact": "Dampak belum disebutkan.",
                    }
                ),
            )
        )

        with (
            patch.object(settings, "gemini_api_key", "test-key"),
            patch.object(settings, "gemini_model", "test-model"),
        ):
            result = await GeminiProvider(client).generate_structured(
                response_type=EvidenceAssistantDraft,
                system_instruction="Test",
                input_data={"story": "test"},
            )
        self.assertEqual(result.title, "Migrasi platform")
        request = client.models.generate_content.await_args.kwargs
        self.assertEqual(request["model"], "test-model")
        config = request["config"]
        self.assertEqual(config.temperature, 0.2)
        self.assertEqual(config.max_output_tokens, settings.gemini_max_output_tokens)
        self.assertEqual(config.response_mime_type, "application/json")
        schema = config.response_json_schema
        self.assertEqual(schema["required"], ["title", "description", "impact"])
        self.assertFalse(schema["additionalProperties"])
        self.assertIsNone(config.tools)

    async def test_invalid_json_is_rejected(self) -> None:
        client = MagicMock()
        client.models.generate_content = AsyncMock(
            return_value=SimpleNamespace(text="not json")
        )

        with (
            patch.object(settings, "gemini_api_key", "test-key"),
            patch.object(settings, "gemini_model", "test-model"),
            self.assertRaises(AIProviderResponseError),
        ):
            await GeminiProvider(client).generate_structured(
                response_type=EvidenceAssistantDraft,
                system_instruction="Test",
                input_data={},
            )

    async def test_empty_response_is_rejected(self) -> None:
        client = MagicMock()
        client.models.generate_content = AsyncMock(
            return_value=SimpleNamespace(text="")
        )

        with (
            patch.object(settings, "gemini_api_key", "test-key"),
            patch.object(settings, "gemini_model", "test-model"),
            self.assertRaisesRegex(AIProviderResponseError, "empty"),
        ):
            await GeminiProvider(client).generate_structured(
                response_type=EvidenceAssistantDraft,
                system_instruction="Test",
                input_data={},
            )

    async def test_grounded_generation_returns_search_provenance(self) -> None:
        grounding = SimpleNamespace(
            grounding_chunks=[
                SimpleNamespace(
                    web=SimpleNamespace(
                        title="BPS Indonesia", url=None, uri="https://bps.go.id/source"
                    )
                )
            ],
            model_dump=MagicMock(
                return_value={"webSearchQueries": ["Indonesia Python jobs"]}
            ),
        )
        client = MagicMock()
        client.models.generate_content = AsyncMock(
            return_value=SimpleNamespace(
                text=json.dumps(
                    {
                        "summary": "Permintaan tetap kuat.",
                        "signals": [
                            {
                                "subject_type": "skill",
                                "subject_name": "Python",
                                "signal_type": "skill_relevance",
                                "classification": "rising",
                                "rationale": "Digunakan luas di pasar kerja.",
                            }
                        ],
                    }
                ),
                candidates=[SimpleNamespace(grounding_metadata=grounding)],
            )
        )
        with (
            patch.object(settings, "gemini_api_key", "test-key"),
            patch.object(settings, "gemini_model", "test-model"),
        ):
            result = await GeminiProvider(client).generate_grounded_structured(
                response_type=MarketBaselineAIResult,
                system_instruction="Research",
                input_data={"country": "Indonesia"},
            )
        self.assertEqual(result.search_queries, ["Indonesia Python jobs"])
        self.assertEqual(
            result.citations,
            [{"title": "BPS Indonesia", "url": "https://bps.go.id/source"}],
        )
        config = client.models.generate_content.await_args.kwargs["config"]
        self.assertIsNotNone(config.tools[0].google_search)


class MarketBaselineSchemaTests(TestCase):
    def test_subjects_are_normalized_and_deduplicated(self) -> None:
        payload = MarketBaselineRefreshRequest(
            subjects=[
                {"subject_type": "skill", "name": " Python "},
                {"subject_type": "skill", "name": "python"},
            ]
        )
        self.assertEqual(len(payload.subjects), 1)
        self.assertEqual(payload.subjects[0].name, "python")

    def test_signal_type_and_classification_must_match_subject(self) -> None:
        with self.assertRaises(ValidationError):
            MarketSignalDraft(
                subject_type="role",
                subject_name="Engineer",
                signal_type="skill_relevance",
                classification="rising",
                rationale="Mismatch",
            )
        with self.assertRaises(ValidationError):
            MarketSignalDraft(
                subject_type="skill",
                subject_name="Python",
                signal_type="skill_relevance",
                classification="strong",
                rationale="Mismatch",
            )
