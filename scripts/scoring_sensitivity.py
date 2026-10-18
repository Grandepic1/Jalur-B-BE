"""Weight sensitivity analysis for the Jalur B scoring models.

Shifts every weight in :mod:`app.core.scoring_config` by +/-10 percentage points (then
renormalizes the group so it still sums to 1.00) and measures how much the pivot ranking
moves. The headline metric is the *discordant-pair flip rate*: over every pair of pivot
roles whose relative order can actually change, the share that reverses under a shift.

Pairs in which one role is at least as strong as the other on every dimension are excluded,
because no set of positive weights can ever reorder them. This deliberately removes every
pair involving the all-strong role; the old top-role test could never beat that role under
any weights, so its "STABLE" verdict was vacuous.

Run with:

    uv run python scripts/scoring_sensitivity.py

Exit code is 1 when the worst perturbation flips more than ``MAX_FLIP_RATE`` of the
comparable pairs, so this can be wired into CI as a stability guard.
"""

from __future__ import annotations

import itertools
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

# Allow ``uv run python scripts/scoring_sensitivity.py`` from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.scoring import career_risk, career_readiness, overall_resilience  # noqa: E402
from app.core.scoring_config import (  # noqa: E402
    CAREER_READINESS_WEIGHTS,
    CAREER_RISK_WEIGHTS,
    PIVOT_MATCH_WEIGHTS,
    RESILIENCE_WEIGHTS,
    SIGNAL_SCORES,
    weight_groups,
)

SHIFT = Decimal("0.10")
SHIFT_FLOAT = float(SHIFT)
SIGNAL_LEVELS = ("weak", "moderate", "strong")
# The worst shift may reorder at most this share of comparable pivot-role pairs.
MAX_FLIP_RATE = Decimal("0.10")


def shift_weight(
    weights: dict[str, Decimal],
    target: str,
    delta: Decimal,
    *,
    quantize: bool = True,
) -> dict[str, Decimal]:
    """Move one weight by ``delta`` and rescale the rest to keep the sum at 1.00.

    ``quantize`` rounds the rescaled weights for display. The flip-rate metric uses its own
    float perturbation so its arithmetic matches the documented reference exactly.
    """
    shifted = dict(weights)
    shifted[target] = shifted[target] + delta
    remaining = [key for key in shifted if key != target]
    total_remaining = sum(shifted[key] for key in remaining)
    target_total = Decimal("1") - shifted[target]
    if total_remaining <= 0:
        # Nothing left to absorb the change; spread it evenly.
        share = target_total / Decimal(len(remaining)) if remaining else Decimal("0")
        for key in remaining:
            shifted[key] = share
    else:
        for key in remaining:
            value = shifted[key] / total_remaining * target_total
            shifted[key] = (
                value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
                if quantize
                else value
            )
    return shifted


def pivot_flip_report() -> tuple[list[str], Decimal, Decimal]:
    """Report the discordant-pair flip rate for each pivot weight perturbation.

    Returns the report lines, the worst flip rate, and the mean flip rate.
    """
    # Plain floats here so the perturbation arithmetic matches the documented reference
    # exactly. The result is a sign test over a fixed grid, so float noise at an exact tie
    # does not change what the metric is measuring.
    signal_scores = {level: float(SIGNAL_SCORES[level]) for level in SIGNAL_LEVELS}
    weights = {key: float(value) for key, value in PIVOT_MATCH_WEIGHTS.items()}
    roles = list(itertools.product(SIGNAL_LEVELS, repeat=len(weights)))

    def score(role: tuple[str, ...], active: dict[str, float]) -> float:
        return sum(
            (signal_scores[level] * active[key] for level, key in zip(role, active)),
            0.0,
        )

    baseline = {role: score(role, weights) for role in roles}
    pairs = list(itertools.combinations(roles, 2))
    valid = [
        pair for pair in pairs if abs(baseline[pair[0]] - baseline[pair[1]]) > 1e-9
    ]

    def dominates(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
        a_levels = [signal_scores[level] for level in a]
        b_levels = [signal_scores[level] for level in b]
        return all(x >= y for x, y in zip(a_levels, b_levels)) or all(
            x <= y for x, y in zip(a_levels, b_levels)
        )

    comparable = [pair for pair in valid if not dominates(*pair)]

    def shifted_weights(target: str, delta: float) -> dict[str, float]:
        shifted = dict(weights)
        shifted[target] = weights[target] + delta
        for key in weights:
            if key != target:
                shifted[key] = (
                    weights[key] * (1 - shifted[target]) / (1 - weights[target])
                )
        return shifted

    lines = [
        "\n=== pivot_match: discordant-pair flip rate ===",
        f"  roles: {len(roles)}  valid pairs: {len(valid)}  "
        f"comparable pairs: {len(comparable)}",
    ]
    rates: list[Decimal] = []
    for target in weights:
        for direction, delta in (("+", SHIFT_FLOAT), ("-", -SHIFT_FLOAT)):
            if weights[target] + delta <= 0:
                lines.append(
                    f"  {target:22} {direction}{SHIFT} -> skipped (weight would be <= 0)"
                )
                continue
            shifted = shifted_weights(target, delta)
            scores = {role: score(role, shifted) for role in roles}
            flips = sum(
                1
                for a, b in comparable
                if (baseline[a] - baseline[b]) * (scores[a] - scores[b]) < 0
            )
            rate = Decimal(flips) / Decimal(len(comparable))
            rates.append(rate)
            lines.append(
                f"  {target:22} {direction}{SHIFT} -> flips {flips:4d}  "
                f"{rate:.1%} of {len(comparable)}  "
                f"({Decimal(flips) / Decimal(len(valid)):.1%} of {len(valid)})"
            )

    worst = max(rates)
    mean = sum(rates) / len(rates)
    lines.append(f"  worst perturbation: {worst:.1%}   mean: {mean:.1%}")
    return lines, worst, mean


def main() -> int:
    lines: list[str] = []
    groups = weight_groups()
    for name, weights in groups.items():
        total = sum(weights.values())
        assert total == Decimal("1"), f"{name} weights sum to {total}, expected 1.00"
        if name == "pivot_match":
            continue
        lines.append(f"\n=== {name} (sum={total}) ===")
        for target in weights:
            for direction, delta in (("+", SHIFT), ("-", -SHIFT)):
                lines.append(
                    f"  {target:22} {direction}{SHIFT} -> "
                    f"weights {shift_weight(weights, target, delta)}"
                )

    pivot_lines, worst, mean = pivot_flip_report()
    lines.extend(pivot_lines)

    lines.append("\n=== Composite score sensitivity ===")
    baseline_readiness = career_readiness(
        performance_growth=Decimal("80"),
        skill_relevance=Decimal("70"),
        adaptability=Decimal("60"),
        mobility=Decimal("65"),
    )
    lines.append(f"  career_readiness baseline: {baseline_readiness}")
    for target in CAREER_READINESS_WEIGHTS:
        shifted = shift_weight(CAREER_READINESS_WEIGHTS, target, SHIFT)
        value = sum(
            (
                Decimal({"performance_growth": "80", "skill_relevance": "70", "adaptability": "60", "mobility": "65"}[key])
                * weight
                for key, weight in shifted.items()
            ),
            Decimal("0"),
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        lines.append(f"  {target:22} +{SHIFT} -> career_readiness {value}")

    baseline_risk = career_risk(
        activity_exposure=Decimal("70"),
        market_demand_risk=Decimal("50"),
        skill_dependency_risk=Decimal("60"),
        industry_volatility_risk=Decimal("40"),
    )
    lines.append(f"  career_risk baseline: {baseline_risk}")
    for target in CAREER_RISK_WEIGHTS:
        shifted = shift_weight(CAREER_RISK_WEIGHTS, target, SHIFT)
        values = {
            "activity_exposure": Decimal("70"),
            "market_demand": Decimal("50"),
            "skill_dependency": Decimal("60"),
            "industry_volatility": Decimal("40"),
        }
        value = sum(
            (values[key] * weight for key, weight in shifted.items()), Decimal("0")
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        lines.append(f"  {target:22} +{SHIFT} -> career_risk {value}")

    lines.append(f"  overall_resilience baseline: "
                 f"{overall_resilience(career_readiness_score=Decimal('70'), financial_readiness_score=Decimal('50'))}")
    for target in RESILIENCE_WEIGHTS:
        shifted = shift_weight(RESILIENCE_WEIGHTS, target, SHIFT)
        lines.append(f"  {target:22} +{SHIFT} -> weights {shifted}")

    print("\n".join(lines))

    if worst > MAX_FLIP_RATE:
        print(
            f"\nUNSTABLE: the worst +/-10pp shift flipped {worst:.1%} of comparable "
            f"pivot pairs, above the {MAX_FLIP_RATE:.0%} threshold."
        )
        return 1
    print(
        f"\nSTABLE: the worst +/-10pp shift flipped {worst:.1%} of comparable pivot "
        f"pairs (mean {mean:.1%}), within the {MAX_FLIP_RATE:.0%} threshold."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
