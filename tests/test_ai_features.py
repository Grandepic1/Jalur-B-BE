import json
from decimal import Decimal
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

import httpx

from app.core.ai import AIProviderResponseError, GeminiProvider
from app.core.config import settings
from app.core.scoring import (
    financial_readiness,
    health_level,
    risk_level,
    weighted,
)
from app.models.ai_features import EvidenceAssistantDraft
from app.models.market_baseline import (
    MarketBaselineAIResult,
    MarketBaselineRefreshRequest,
    MarketSignalDraft,
)
from pydantic import ValidationError
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
        }
        for path, methods in expected.items():
            self.assertIn(path, paths)
            self.assertEqual(set(paths[path]), methods)


class GeminiProviderTests(IsolatedAsyncioTestCase):
    async def test_structured_response_is_validated(self) -> None:
        payload = {
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps(
                                    {
                                        "title": "Migrasi platform",
                                        "description": "Memigrasikan platform.",
                                        "impact": "Dampak belum disebutkan.",
                                    }
                                )
                            }
                        ]
                    },
                }
            ]
        }

        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.headers["x-goog-api-key"], "test-key")
            return httpx.Response(200, json=payload)

        with (
            patch.object(settings, "gemini_api_key", "test-key"),
            patch.object(settings, "gemini_model", "test-model"),
        ):
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(handler)
            ) as client:
                result = await GeminiProvider(client).generate_structured(
                    response_type=EvidenceAssistantDraft,
                    system_instruction="Test",
                    input_data={"story": "test"},
                )
        self.assertEqual(result.title, "Migrasi platform")

    async def test_invalid_json_is_rejected(self) -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "finishReason": "STOP",
                            "content": {"parts": [{"text": "not json"}]},
                        }
                    ]
                },
            )

        with (
            patch.object(settings, "gemini_api_key", "test-key"),
            patch.object(settings, "gemini_model", "test-model"),
        ):
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(handler)
            ) as client:
                with self.assertRaises(AIProviderResponseError):
                    await GeminiProvider(client).generate_structured(
                        response_type=EvidenceAssistantDraft,
                        system_instruction="Test",
                        input_data={},
                    )

    async def test_grounded_response_requires_and_returns_citations(self) -> None:
        output = {
            "summary": "Permintaan tetap kuat.",
            "signals": [
                {
                    "subject_type": "role",
                    "subject_name": "Software Engineer",
                    "signal_type": "market_demand",
                    "classification": "strong",
                    "rationale": "Didukung sumber pasar kerja terkini.",
                }
            ],
        }

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            self.assertEqual(body["tools"], [{"googleSearch": {}}])
            self.assertIn("responseJsonSchema", body["generationConfig"])
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "finishReason": "STOP",
                            "content": {"parts": [{"text": json.dumps(output)}]},
                            "groundingMetadata": {
                                "webSearchQueries": [
                                    "Indonesia software engineer jobs"
                                ],
                                "groundingChunks": [
                                    {
                                        "web": {
                                            "title": "Official source",
                                            "uri": "https://example.go.id/report",
                                        }
                                    }
                                ],
                            },
                        }
                    ]
                },
            )

        with (
            patch.object(settings, "gemini_api_key", "test-key"),
            patch.object(settings, "gemini_model", "test-model"),
        ):
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(handler)
            ) as client:
                result = await GeminiProvider(client).generate_grounded_structured(
                    response_type=MarketBaselineAIResult,
                    system_instruction="Research",
                    input_data={"country": "Indonesia"},
                )
        self.assertEqual(result.value.signals[0].classification, "strong")
        self.assertEqual(result.citations[0]["url"], "https://example.go.id/report")

    async def test_grounded_response_without_citations_is_rejected(self) -> None:
        output = {
            "summary": "Ringkasan.",
            "signals": [
                {
                    "subject_type": "skill",
                    "subject_name": "Python",
                    "signal_type": "skill_relevance",
                    "classification": "rising",
                    "rationale": "Relevan.",
                }
            ],
        }

        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "finishReason": "STOP",
                            "content": {"parts": [{"text": json.dumps(output)}]},
                            "groundingMetadata": {},
                        }
                    ]
                },
            )

        with (
            patch.object(settings, "gemini_api_key", "test-key"),
            patch.object(settings, "gemini_model", "test-model"),
        ):
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(handler)
            ) as client:
                with self.assertRaises(AIProviderResponseError):
                    await GeminiProvider(client).generate_grounded_structured(
                        response_type=MarketBaselineAIResult,
                        system_instruction="Research",
                        input_data={},
                    )


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
