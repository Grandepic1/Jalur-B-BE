"""Deterministic scoring primitives.

The model never supplies final numeric scores; it only classifies into enums. Every
number below is produced by backend code from those classifications. Weights live in
:mod:`app.core.scoring_config` so they can be reviewed and sensitivity-tested in one
place.

``SCORE_VERSION`` is persisted on every assessment. Bumping it means new assessments use
new weights while historical rows keep the version they were scored with.
"""

from decimal import Decimal, ROUND_HALF_UP

from app.core.scoring_config import (
    CAREER_READINESS_WEIGHTS,
    CAREER_RISK_WEIGHTS,
    EXPOSURE_SCORES,
    HEALTH_BANDS,
    PIVOT_MATCH_WEIGHTS,
    RELEVANCE_SCORES,
    RESILIENCE_WEIGHTS,
    RISK_BANDS,
    SIGNAL_SCORES,
)

__all__ = [
    "SCORE_VERSION",
    "PROMPT_VERSION",
    "SIGNAL_SCORES",
    "EXPOSURE_SCORES",
    "RELEVANCE_SCORES",
    "CAREER_READINESS_WEIGHTS",
    "RESILIENCE_WEIGHTS",
    "CAREER_RISK_WEIGHTS",
    "PIVOT_MATCH_WEIGHTS",
    "score",
    "average",
    "weighted",
    "weighted_optional",
    "health_level",
    "risk_level",
    "exposure_level",
    "financial_readiness",
    "career_readiness",
    "overall_resilience",
    "career_risk",
    "pivot_match",
]


# ``career-resilience-v2`` rebalances Career Readiness and removes the double counting of
# Financial Readiness, Skill Relevance, and Mobility in Overall Resilience.
SCORE_VERSION = "career-resilience-v2"
PROMPT_VERSION = "career-analysis-v1"

ZERO = Decimal("0")
HUNDRED = Decimal("100")


def score(value: Decimal | int | float | str) -> Decimal:
    """Clamp to 0-100 and round half up to two decimals."""
    return max(ZERO, min(HUNDRED, Decimal(str(value)))).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def average(values: list[Decimal]) -> Decimal | None:
    """Mean of ``values``, or ``None`` when there is nothing to average.

    Returning ``None`` instead of a default is deliberate. A fabricated default such as
    50 makes a missing input look like a real measurement and leaks into every score that
    consumes it. Callers must decide explicitly what a missing component means: see
    :func:`weighted_optional`.
    """
    if not values:
        return None
    return score(sum(values) / len(values))


def weighted(parts: list[tuple[Decimal, Decimal]]) -> Decimal:
    """Weighted sum of ``(value, weight)`` pairs. Weights must sum to 1.00."""
    return score(sum(value * weight for value, weight in parts))


def weighted_optional(
    parts: list[tuple[Decimal | None, Decimal]],
) -> Decimal | None:
    """Weighted sum that drops missing components and renormalizes the rest.

    When one input is unavailable the remaining weights are rescaled so they still sum to
    1.00. This keeps the score on the same 0-100 scale instead of silently diluting it
    toward zero. Returns ``None`` only when every component is missing.
    """
    present = [(value, weight) for value, weight in parts if value is not None]
    if not present:
        return None
    total_weight = sum(weight for _, weight in present)
    if total_weight <= 0:
        return None
    return score(
        sum(value * (weight / total_weight) for value, weight in present if value is not None)
    )


def health_level(value: Decimal) -> str:
    if value >= HEALTH_BANDS["high_min"]:
        return "high"
    if value >= HEALTH_BANDS["medium_min"]:
        return "medium"
    return "low"


def risk_level(value: Decimal) -> str:
    if value >= RISK_BANDS["high_min"]:
        return "high"
    if value >= RISK_BANDS["medium_min"]:
        return "medium"
    return "low"


def exposure_level(value: Decimal) -> str:
    return risk_level(value)


def financial_readiness(runway_months: Decimal, target_months: Decimal) -> Decimal:
    """Share of the personal runway target already covered, capped at 100."""
    if target_months <= 0:
        return Decimal("0.00")
    return score(runway_months / target_months * HUNDRED)


def career_readiness(
    *,
    performance_growth: Decimal,
    skill_relevance: Decimal | None,
    adaptability: Decimal,
    mobility: Decimal | None,
) -> Decimal | None:
    """Career-side readiness. Contains no financial component.

    ``skill_relevance`` and ``mobility`` may be ``None`` when the underlying signal is
    unavailable; they are then dropped and the remaining weights renormalized rather than
    being replaced by a placeholder value.
    """
    values: dict[str, Decimal | None] = {
        "performance_growth": performance_growth,
        "skill_relevance": skill_relevance,
        "adaptability": adaptability,
        "mobility": mobility,
    }
    return weighted_optional(
        [(values[key], weight) for key, weight in CAREER_READINESS_WEIGHTS.items()]
    )


def overall_resilience(
    *,
    career_readiness_score: Decimal | None,
    financial_readiness_score: Decimal | None,
) -> Decimal | None:
    """Blend of the career and financial halves.

    Both inputs are aggregates, so no raw input has two paths into this number.
    """
    return weighted_optional(
        [
            (career_readiness_score, RESILIENCE_WEIGHTS["career_readiness"]),
            (financial_readiness_score, RESILIENCE_WEIGHTS["financial_readiness"]),
        ]
    )


def career_risk(
    *,
    activity_exposure: Decimal | None,
    market_demand_risk: Decimal | None,
    skill_dependency_risk: Decimal | None,
    industry_volatility_risk: Decimal | None,
) -> Decimal | None:
    values: dict[str, Decimal | None] = {
        "activity_exposure": activity_exposure,
        "market_demand": market_demand_risk,
        "skill_dependency": skill_dependency_risk,
        "industry_volatility": industry_volatility_risk,
    }
    return weighted_optional(
        [(values[key], weight) for key, weight in CAREER_RISK_WEIGHTS.items()]
    )


def pivot_match(
    *,
    skill_fit: Decimal,
    activity_fit: Decimal,
    experience_fit: Decimal,
    industry_fit: Decimal,
) -> Decimal:
    values = {
        "skill_fit": skill_fit,
        "activity_fit": activity_fit,
        "experience_fit": experience_fit,
        "industry_fit": industry_fit,
    }
    return weighted(
        [(values[key], weight) for key, weight in PIVOT_MATCH_WEIGHTS.items()]
    )
