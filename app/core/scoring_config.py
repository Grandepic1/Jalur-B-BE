"""Versioned scoring weights for Jalur B.

Every numeric weight that reaches a user-facing score lives in this one module so a
change is reviewable in a single diff, and so the invariant tests in
``tests/test_scoring_weights.py`` can assert that each group sums to exactly 1.00 and
that every raw input has exactly one path to the final score.

Rule for this file: **no raw input may appear in more than one weight group along a
single scoring path.** Overall Resilience composes the two top-level scores rather than
re-listing their components, which is what removes the double counting described in the
T1 finding.

Changing a weight requires bumping ``SCORE_VERSION`` in ``app.core.scoring``.
Assessments persist the version they were scored with, so existing rows stay traceable
and are never silently recalculated with new weights.
"""

from decimal import Decimal

# ─── Career Readiness ────────────────────────────────────────────────
# Formerly "Career Health". Financial Readiness was removed: it is measured once, in
# Overall Resilience, and including it here gave it a second path to the same score.
CAREER_READINESS_WEIGHTS: dict[str, Decimal] = {
    # Documented outcomes and progression are the strongest evidence of a worker's own
    # trajectory, so this carries the largest single weight.
    "performance_growth": Decimal("0.30"),
    # Skill obsolescence is the most frequently cited driver of involuntary career
    # change, and skills are user-supplied facts rather than model inference.
    "skill_relevance": Decimal("0.30"),
    # Adaptability is derived from profile breadth and learning signals: real but weaker
    # evidence than documented outcomes, so it is weighted below them.
    "adaptability": Decimal("0.20"),
    # Mobility is the top pivot match score, which is a model classification over
    # user-supplied facts. It is the least direct evidence, so it gets the smallest share.
    "mobility": Decimal("0.20"),
}

# ─── Overall Resilience ──────────────────────────────────────────────
# Exactly two disjoint components: the career side and the financial side. Career
# Readiness already contains skill relevance and mobility, so they are deliberately not
# repeated here.
RESILIENCE_WEIGHTS: dict[str, Decimal] = {
    "career_readiness": Decimal("0.50"),
    "financial_readiness": Decimal("0.50"),
}

# ─── Career Risk ─────────────────────────────────────────────────────
CAREER_RISK_WEIGHTS: dict[str, Decimal] = {
    # Direct measurement of the user's own activities against AI capability.
    "activity_exposure": Decimal("0.40"),
    # Demand for the current role: an external market signal, so weaker than direct
    # activity exposure and therefore weighted below it.
    "market_demand": Decimal("0.25"),
    # Concentration risk in the user's skill set.
    "skill_dependency": Decimal("0.20"),
    # Industry volatility is the broadest and slowest-moving signal, so it gets the
    # smallest share.
    "industry_volatility": Decimal("0.15"),
}

# ─── Pivot Match ─────────────────────────────────────────────────────
PIVOT_MATCH_WEIGHTS: dict[str, Decimal] = {
    # Skill fit dominates because a pivot is only realistic when the user already holds
    # most of the required skills.
    "skill_fit": Decimal("0.55"),
    # Day-to-day activity fit: how similar the work itself is.
    "activity_fit": Decimal("0.20"),
    # Experience fit: seniority and duration alignment.
    "experience_fit": Decimal("0.15"),
    # Industry fit: transferable-sector bonus, the smallest adjustment.
    "industry_fit": Decimal("0.10"),
}

# ─── Signal bands ────────────────────────────────────────────────────
# These are classification anchors, not weights. They map an LLM classification to a
# number and carry no external grounding (see the T4 finding).
SIGNAL_SCORES: dict[str, Decimal] = {
    "weak": Decimal("35"),
    "moderate": Decimal("65"),
    "strong": Decimal("85"),
}
EXPOSURE_SCORES: dict[str, Decimal] = {
    "low": Decimal("25"),
    "medium": Decimal("55"),
    "high": Decimal("80"),
}
RELEVANCE_SCORES: dict[str, Decimal] = {
    "declining": Decimal("35"),
    "stable": Decimal("65"),
    "rising": Decimal("90"),
}

# ─── Panel result bands ──────────────────────────────────────────────
HEALTH_BANDS: dict[str, Decimal] = {
    "medium_min": Decimal("60"),
    "high_min": Decimal("75"),
}
RISK_BANDS: dict[str, Decimal] = {
    "medium_min": Decimal("40"),
    "high_min": Decimal("70"),
}


def weight_groups() -> dict[str, dict[str, Decimal]]:
    """Return every weight group, for invariant tests and sensitivity analysis."""
    return {
        "career_readiness": CAREER_READINESS_WEIGHTS,
        "resilience": RESILIENCE_WEIGHTS,
        "career_risk": CAREER_RISK_WEIGHTS,
        "pivot_match": PIVOT_MATCH_WEIGHTS,
    }


# Per-role weight ``PIVOT_MATCH_WEIGHTS`` maps onto the AI result. The AI classifies
# ``skill_fit``/``activity_fit``/``experience_fit``/``industry_fit``; this table only
# names the mapping so the sensitivity script can iterate it.
PIVOT_MATCH_SIGNALS: tuple[str, ...] = (
    "skill_fit",
    "activity_fit",
    "experience_fit",
    "industry_fit",
)

CAREER_RISK_SIGNALS: tuple[str, ...] = (
    "activity_exposure",
    "market_demand",
    "skill_dependency",
    "industry_volatility",
)
