from decimal import Decimal, ROUND_HALF_UP


SCORE_VERSION = "career-resilience-v1"
PROMPT_VERSION = "career-analysis-v1"

SIGNAL_SCORES = {
    "weak": Decimal("35"),
    "moderate": Decimal("65"),
    "strong": Decimal("85"),
}
EXPOSURE_SCORES = {
    "low": Decimal("25"),
    "medium": Decimal("55"),
    "high": Decimal("80"),
}
RELEVANCE_SCORES = {
    "declining": Decimal("35"),
    "stable": Decimal("65"),
    "rising": Decimal("90"),
}
HEALTH_WEIGHTS = {
    "performance_growth": Decimal("0.25"),
    "skill_relevance": Decimal("0.25"),
    "adaptability": Decimal("0.15"),
    "mobility": Decimal("0.15"),
    "financial_readiness": Decimal("0.20"),
}


def score(value: Decimal | int | float | str) -> Decimal:
    return max(Decimal("0"), min(Decimal("100"), Decimal(str(value)))).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def average(values: list[Decimal], default: Decimal = Decimal("50")) -> Decimal:
    if not values:
        return score(default)
    return score(sum(values) / len(values))


def weighted(parts: list[tuple[Decimal, Decimal]]) -> Decimal:
    return score(sum(value * weight for value, weight in parts))


def health_level(value: Decimal) -> str:
    if value >= 75:
        return "high"
    if value >= 60:
        return "medium"
    return "low"


def risk_level(value: Decimal) -> str:
    if value >= 70:
        return "high"
    if value >= 40:
        return "medium"
    return "low"


def exposure_level(value: Decimal) -> str:
    if value >= 70:
        return "high"
    if value >= 40:
        return "medium"
    return "low"


def financial_readiness(runway_months: Decimal, target_months: Decimal) -> Decimal:
    if target_months <= 0:
        return Decimal("0.00")
    return score(runway_months / target_months * 100)


def career_health(
    *,
    performance_growth: Decimal,
    skill_relevance: Decimal,
    adaptability: Decimal,
    mobility: Decimal,
    financial_readiness_score: Decimal,
) -> Decimal:
    values = {
        "performance_growth": performance_growth,
        "skill_relevance": skill_relevance,
        "adaptability": adaptability,
        "mobility": mobility,
        "financial_readiness": financial_readiness_score,
    }
    return weighted([(values[key], weight) for key, weight in HEALTH_WEIGHTS.items()])
