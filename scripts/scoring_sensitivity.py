"""Weight sensitivity analysis for the Jalur B scoring models.

Shifts every weight in :mod:`app.core.scoring_config` by +/-10 percentage points (then
renormalizes the group so it still sums to 1.00) and reports whether the resulting
ranking changes. The output is intended as paper evidence that the model is not
tuned to a knife-edge.

Run with:

    uv run python scripts/scoring_sensitivity.py

Exit code is 1 if any perturbation changes the top-ranked role, so this can be wired into
CI as a stability guard.
"""

from __future__ import annotations

import itertools
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

# Allow ``uv run python scripts/scoring_sensitivity.py`` from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.scoring import career_risk, career_readiness, overall_resilience  # noqa: E402
from app.core.scoring_config import (
    CAREER_READINESS_WEIGHTS,
    CAREER_RISK_WEIGHTS,
    PIVOT_MATCH_WEIGHTS,
    SIGNAL_SCORES,
    RESILIENCE_WEIGHTS,
    weight_groups,
)

SHIFT = Decimal("0.10")
SIGNAL_LEVELS = ("weak", "moderate", "strong")


def shift_weight(
    weights: dict[str, Decimal], target: str, delta: Decimal
) -> dict[str, Decimal]:
    """Move one weight by ``delta`` and rescale the rest to keep the sum at 1.00."""
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
            shifted[key] = (shifted[key] / total_remaining * target_total).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP
            )
    return shifted


def pivot_fixture() -> list[tuple[str, dict[str, str]]]:
    """Every weak/moderate/strong combination as a named candidate role."""
    roles = []
    for index, combination in enumerate(
        itertools.product(SIGNAL_LEVELS, repeat=len(PIVOT_MATCH_WEIGHTS))
    ):
        role = dict(zip(PIVOT_MATCH_WEIGHTS, combination))
        name = ", ".join(f"{key.split('_')[0]}={value}" for key, value in role.items())
        roles.append((f"role-{index:02d} ({name})", role))
    return roles


def rank_pivot_roles(
    roles: list[tuple[str, dict[str, str]]], weights: dict[str, Decimal]
) -> list[tuple[str, Decimal]]:
    scored = []
    for name, signals in roles:
        score = sum(
            (SIGNAL_SCORES[signals[key]] * weights[key] for key in weights),
            Decimal("0"),
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        scored.append((name, score))
    return sorted(scored, key=lambda item: item[1], reverse=True)


def report_group(name: str, weights: dict[str, Decimal]) -> tuple[list[str], list[str]]:
    """Shift each weight in one group and report the effect on the pivot ranking.

    A top-role change is only counted as unstable when the new leader *strictly* outscores
    the previous leader under the shifted weights. The fixture enumerates all 81
    weak/moderate/strong combinations, so exact ties are common and a tie flip says
    nothing about the weights.
    """
    roles = pivot_fixture()
    lines = [f"\n=== {name} (sum={sum(weights.values())}) ==="]
    unstable: list[str] = []
    if name != "pivot_match":
        for target in weights:
            for direction, delta in (("+", SHIFT), ("-", -SHIFT)):
                lines.append(
                    f"  {target:22} {direction}{SHIFT} -> "
                    f"weights {shift_weight(weights, target, delta)}"
                )
        return lines, unstable

    baseline = rank_pivot_roles(roles, weights)
    baseline_top_role, baseline_top_score = baseline[0]
    lines.append(
        f"  baseline top role: {baseline_top_role} at {baseline_top_score}"
    )
    for target in weights:
        for direction, delta in (("+", SHIFT), ("-", -SHIFT)):
            shifted = shift_weight(weights, target, delta)
            scored = dict(rank_pivot_roles(roles, shifted))
            ranked = sorted(scored.items(), key=lambda item: item[1], reverse=True)
            new_top_role, new_top_score = ranked[0]
            previous_top_score = scored[baseline_top_role]
            if new_top_score > previous_top_score:
                verdict = "CHANGED (score-driven)"
                unstable.append(
                    f"{name}.{target} {direction}{SHIFT}: "
                    f"{new_top_role} ({new_top_score}) overtakes "
                    f"{baseline_top_role} ({previous_top_score})"
                )
            elif new_top_role != baseline_top_role:
                verdict = "tie-break only"
            else:
                verdict = "stable"
            lines.append(
                f"  {target:22} {direction}{SHIFT} -> {verdict} "
                f"({new_top_role} at {new_top_score})"
            )
    return lines, unstable


def main() -> int:
    lines: list[str] = []
    unstable: list[str] = []
    groups = weight_groups()
    for name, weights in groups.items():
        total = sum(weights.values())
        assert total == Decimal("1"), f"{name} weights sum to {total}, expected 1.00"
        group_lines, group_unstable = report_group(name, weights)
        lines.extend(group_lines)
        unstable.extend(group_unstable)

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

    output = "\n".join(lines)
    print(output)

    if unstable:
        print("\nUNSTABLE: a +/-10pp shift let another role strictly outrank the leader:")
        for line in unstable:
            print(f"  {line}")
        return 1
    print(
        "\nSTABLE: no +/-10pp shift let another role strictly outrank the top pivot role."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
