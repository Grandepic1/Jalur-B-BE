"""Transition Gap: runway measured against the time a pivot actually needs.

Runway alone answers "how long can I survive". It does not answer "do I have enough time
to get somewhere else". Transition Gap is the difference between the two, and it is the
headline number the product is built around:

    TG(role) = R_exit - (T_prep(role) + T_search)

* ``R_exit`` comes from :mod:`app.core.entitlements` and depends on how the job ends.
* ``T_prep(role)`` is the preparation time of the role the user actually chooses, not the
  worst case across every recommended role. Using the maximum made every user with one
  slow option look equally bad.
* ``T_search`` is an explicit, visible assumption rather than a hidden constant.

Pure module: no I/O, deterministic, no LLM.
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from app.core.entitlements import DEFAULT_SEARCH_TIME_MONTHS

ZERO = Decimal("0")


# ─── Preparation time ────────────────────────────────────────────────

# Preparation time is estimated from the number of concrete skill gaps, because skill
# gaps are the only quantified input the pivot analysis produces. This is a heuristic, not
# sourced data, so the basis is stored alongside the number and surfaced in the UI.
PREPARATION_MONTHS_PER_SKILL_GAP = Decimal("1.5")
MIN_PREPARATION_MONTHS = 1
MAX_PREPARATION_MONTHS = 12


def preparation_months_for_gap_count(gap_count: int) -> int:
    """Estimate months of preparation from the number of missing skills.

    Clamped to 1-12 months so a single gap is never instant and a long list never implies
    more than a year of preparation.
    """
    if gap_count <= 0:
        return MIN_PREPARATION_MONTHS
    raw = Decimal(gap_count) * PREPARATION_MONTHS_PER_SKILL_GAP
    months = int(raw.to_integral_value(rounding=ROUND_HALF_UP))
    return max(MIN_PREPARATION_MONTHS, min(MAX_PREPARATION_MONTHS, months))


def months_saved_by_closing_one_gap(gap_count: int) -> Decimal:
    """How much shorter preparation gets if one skill gap is closed first."""
    if gap_count <= 1:
        return ZERO
    current = preparation_months_for_gap_count(gap_count)
    improved = preparation_months_for_gap_count(gap_count - 1)
    return Decimal(max(current - improved, 0))


# ─── Transition Gap ──────────────────────────────────────────────────


@dataclass(frozen=True)
class RoleTransition:
    """Deterministic Transition Gap result for one pivot role."""

    role_name: str
    match_score: Decimal
    preparation_time_months: Decimal
    search_time_months: Decimal
    transition_months: Decimal
    transition_gap_months: Decimal
    status: str
    recommended_monthly_saving: Decimal
    months_saved_by_closing_one_gap: Decimal
    note: str


def transition_gap(
    *,
    role_name: str,
    match_score: Decimal,
    preparation_time_months: Decimal,
    exit_runway_months: Decimal,
    monthly_burn: Decimal,
    search_time_months: Decimal = DEFAULT_SEARCH_TIME_MONTHS,
    horizon_months: Decimal | None = None,
    gap_count: int = 0,
) -> RoleTransition:
    """Compute the gap between available runway and the time a role change needs.

    ``horizon_months`` is how long the user has to save before the money is needed. It is
    only used to turn a remaining deficit into a monthly saving target. When the exit date
    is unknown it falls back to the runway itself, which answers "can I close this gap from
    the savings I still have time to make".
    """
    transition = preparation_time_months + search_time_months
    gap = exit_runway_months - transition
    if gap >= 0:
        status = "surplus"
        deficit = ZERO
        note = "Masa aman finansial cukup untuk waktu transisi."
    else:
        status = "deficit"
        deficit = -gap
        note = "Masa aman finansial lebih pendek daripada waktu transisi."

    saving_target = ZERO
    savings_window = (
        horizon_months if horizon_months and horizon_months > 0 else exit_runway_months
    )
    if deficit > 0 and monthly_burn > 0 and savings_window > 0:
        saving_target = (deficit * monthly_burn / savings_window).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )

    return RoleTransition(
        role_name=role_name,
        match_score=match_score,
        preparation_time_months=preparation_time_months,
        search_time_months=search_time_months,
        transition_months=transition,
        transition_gap_months=gap,
        status=status,
        recommended_monthly_saving=saving_target,
        months_saved_by_closing_one_gap=months_saved_by_closing_one_gap(gap_count),
        note=note,
    )


def select_preparation_role(
    roles: list[tuple[str, Decimal, int]],
    *,
    preferred_role_name: str | None = None,
) -> tuple[str, Decimal, int]:
    """Pick the role whose preparation time feeds the Transition Gap.

    Defaults to the role with the highest match score, which is the role the pivot
    analysis already recommends first. An explicit ``preferred_role_name`` wins so the
    user can ask "what if I go for the other one".
    """
    if not roles:
        raise ValueError("at least one pivot role is required")
    if preferred_role_name:
        wanted = preferred_role_name.strip().lower()
        for role in roles:
            if role[0].strip().lower() == wanted:
                return role
    return max(roles, key=lambda role: role[1])


def horizon_months_until(day_of_layoff, today) -> Decimal:
    """Whole months between today and the assumed layoff date."""
    days = (day_of_layoff - today).days
    if days <= 0:
        return ZERO
    return (Decimal(days) / Decimal("30.44")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
