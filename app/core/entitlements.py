"""Statutory exit entitlements and exit-aware runway (Indonesian labour law).

Pure module: no database, no network, no LLM, no clock. Every function is deterministic
and takes plain values, so the whole Indonesian severance calculation is unit-testable
without touching Postgres or the AI provider.

Regulation basis
----------------
* ``PP 35/2021`` Art. 40(2) — severance (pesangon) months of wage by tenure.
* ``PP 35/2021`` Art. 40(3) — long-service award (UPMK) months of wage by tenure.
* ``PP 35/2021`` Art. 41 — the multiplier applied to pesangon and UPMK for each ground
  of termination.
* ``PP 68/2009`` — final PPh 21 on severance paid as a lump sum.
* ``PP 37/2021`` as amended by ``PP 6/2025`` — JKP (Jaminan Kehilangan Pekerjaan)
  eligibility and cash benefit.

``REGULATION_VERSION`` is stored on every exit-runway result so that if these tables
change (for example once the new Manpower Law replacing UU 13/2003 takes effect) old
results remain traceable to the rules that produced them.
"""

from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum as PyEnum

REGULATION_VERSION = "id-pp35-2021_pp6-2025"

# Time to find a new job after losing one. There is no public Indonesian dataset for
# re-employment duration after a layoff, so this is an explicit, visible, user-adjustable
# assumption rather than a hidden constant. It is never presented as measured data.
DEFAULT_SEARCH_TIME_MONTHS = Decimal("3")
SEARCH_TIME_ASSUMPTION_LABEL = "asumsi"

ZERO = Decimal("0")
ONE = Decimal("1")
MONTHS_PER_YEAR = Decimal("12")


# ─── Exit type ───────────────────────────────────────────────────────


class ExitType(str, PyEnum):
    """How the employment relationship ends. This drives every entitlement below."""

    efficiency_prevent_loss = "efficiency_prevent_loss"
    efficiency_due_to_loss = "efficiency_due_to_loss"
    closure_not_loss = "closure_not_loss"
    bankruptcy = "bankruptcy"
    pkwt_ends_on_schedule = "pkwt_ends_on_schedule"
    resign = "resign"


class EmploymentType(str, PyEnum):
    """PKWTT is a permanent employee; PKWT is a fixed-term contract."""

    pkwtt = "pkwtt"
    pkwt = "pkwt"


# ─── Termination multipliers ─────────────────────────────────────────


@dataclass(frozen=True)
class ExitRules:
    """Pesangon/UPMK multipliers and JKP eligibility for one ground of termination."""

    pesangon_multiplier: Decimal
    upmk_multiplier: Decimal
    jkp_eligible: bool
    pays_pkwt_compensation: bool
    # Conservatism switch. For bankruptcy the company's obligation to pay pesangon and
    # UPMK is frequently not met in practice, so those amounts default to *not* counting
    # as spendable cash while JKP still does. The user can turn this off.
    normative_illiquid_by_default: bool = False
    note: str = ""


# PP 35/2021 Art. 41.
EXIT_RULES: dict[ExitType, ExitRules] = {
    ExitType.efficiency_prevent_loss: ExitRules(
        pesangon_multiplier=Decimal("1.0"),
        upmk_multiplier=Decimal("1"),
        jkp_eligible=True,
        pays_pkwt_compensation=False,
        note="Efficiency to prevent losses: full pesangon and UPMK.",
    ),
    ExitType.efficiency_due_to_loss: ExitRules(
        pesangon_multiplier=Decimal("0.5"),
        upmk_multiplier=Decimal("1"),
        jkp_eligible=True,
        pays_pkwt_compensation=False,
        note="Efficiency caused by losses: pesangon halved, UPMK full.",
    ),
    ExitType.closure_not_loss: ExitRules(
        pesangon_multiplier=Decimal("1.0"),
        upmk_multiplier=Decimal("1"),
        jkp_eligible=True,
        pays_pkwt_compensation=False,
        note="Closure not caused by losses: full pesangon and UPMK.",
    ),
    ExitType.bankruptcy: ExitRules(
        pesangon_multiplier=Decimal("0.5"),
        upmk_multiplier=Decimal("1"),
        jkp_eligible=True,
        pays_pkwt_compensation=False,
        normative_illiquid_by_default=True,
        note=(
            "Bankruptcy: pesangon halved and UPMK full on paper, but the conservative "
            "default treats both as not collectable because the estate is insolvent. "
            "JKP is still paid."
        ),
    ),
    ExitType.pkwt_ends_on_schedule: ExitRules(
        pesangon_multiplier=ZERO,
        upmk_multiplier=ZERO,
        jkp_eligible=False,
        pays_pkwt_compensation=True,
        note="PKWT reaching its end date: compensation only, no JKP.",
    ),
    ExitType.resign: ExitRules(
        pesangon_multiplier=ZERO,
        upmk_multiplier=ZERO,
        jkp_eligible=False,
        pays_pkwt_compensation=False,
        note="Resignation: no pesangon, no UPMK, no JKP.",
    ),
}


# ─── Pesangon and UPMK tenure tables (PP 35/2021 Art. 40) ────────────

# (maximum tenure in months inclusive, months of wage)
_PESANGON_TABLE: tuple[tuple[int, Decimal], ...] = (
    (11, Decimal("1")),
    (23, Decimal("2")),
    (35, Decimal("3")),
    (47, Decimal("4")),
    (59, Decimal("5")),
    (71, Decimal("6")),
    (83, Decimal("7")),
    (95, Decimal("8")),
)

_UPMK_TABLE: tuple[tuple[int, Decimal], ...] = (
    (35, ZERO),
    (71, Decimal("2")),
    (107, Decimal("3")),
    (143, Decimal("4")),
    (179, Decimal("5")),
    (215, Decimal("6")),
    (251, Decimal("7")),
    (287, Decimal("8")),
)


def exit_type_consistency_error(
    exit_type: ExitType, employment_type: EmploymentType
) -> str | None:
    """Return a message when an exit ground cannot apply to this contract type.

    A permanent employee has no contract end date, so "the contract expired on schedule"
    is not a state that can exist. Allowing it produced a nonsensical PKWT compensation
    figure based on years of permanent service.
    """
    if (
        exit_type is ExitType.pkwt_ends_on_schedule
        and employment_type is not EmploymentType.pkwt
    ):
        return (
            "Kontrak berakhir sesuai jadwal hanya berlaku untuk karyawan PKWT; "
            "karyawan PKWTT tidak memiliki tanggal berakhir kontrak."
        )
    return None


def _lookup(table: tuple[tuple[int, Decimal], ...], tenure_months: int) -> Decimal:
    for upper_bound, months in table:
        if tenure_months <= upper_bound:
            return months
    return table[-1][1]


def pesangon_months(tenure_months: int) -> Decimal:
    """Months of wage owed as severance: 1 month under a year, +1 per year, cap 9."""
    if tenure_months < 0:
        raise ValueError("tenure_months cannot be negative")
    if tenure_months >= 96:
        return Decimal("9")
    return _lookup(_PESANGON_TABLE, tenure_months)


def upmk_months(tenure_months: int) -> Decimal:
    """Months of wage owed as the long-service award. Zero below three years."""
    if tenure_months < 0:
        raise ValueError("tenure_months cannot be negative")
    if tenure_months >= 288:
        return Decimal("10")
    return _lookup(_UPMK_TABLE, tenure_months)


# ─── JKP (PP 6/2025) ─────────────────────────────────────────────────

JKP_REPLACEMENT_RATE = Decimal("0.6")
JKP_INSURABLE_WAGE_CEILING = Decimal("5000000")
JKP_MAX_MONTHS = 6
JKP_MIN_CONTRIBUTIONS_IN_WINDOW = 12
JKP_WINDOW_MONTHS = 24
JKP_MIN_CONSECUTIVE_MONTHS = 6
JKP_MAX_AGE = 54
# Claim window: a claim must be filed within six months of the termination date.
JKP_CLAIM_WINDOW_MONTHS = 6


@dataclass(frozen=True)
class JkpEligibility:
    eligible: bool
    reasons: tuple[str, ...]
    monthly_benefit: Decimal
    months: int

    @property
    def total_benefit(self) -> Decimal:
        return self.monthly_benefit * self.months


def jkp_monthly_benefit(monthly_wage: Decimal) -> Decimal:
    """60% of wage, capped at an insurable wage of Rp 5,000,000.

    The wage ceiling means the benefit never exceeds Rp 3,000,000 per month.
    """
    if monthly_wage < 0:
        raise ValueError("monthly_wage cannot be negative")
    return (
        min(monthly_wage, JKP_INSURABLE_WAGE_CEILING) * JKP_REPLACEMENT_RATE
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def jkp_eligibility(
    *,
    exit_type: ExitType,
    monthly_wage: Decimal,
    bpjs_tk_active: bool,
    bpjs_contributions_last_24_months: int,
    bpjs_consecutive_months: int,
    age_years: int,
    jkn_active: bool,
) -> JkpEligibility:
    """Evaluate every JKP condition and return the benefit plus a plain-language reason.

    Every failing condition is reported, not just the first one, so the user can see
    exactly which requirement is unmet. A single failure sets the benefit to zero.
    """
    rules = EXIT_RULES[exit_type]
    reasons: list[str] = []
    if not rules.jkp_eligible:
        reasons.append("Jenis keluar ini tidak memenuhi syarat JKP.")
    if not bpjs_tk_active:
        reasons.append("Tidak terdaftar aktif di BPJS Ketenagakerjaan.")
    if bpjs_contributions_last_24_months < JKP_MIN_CONTRIBUTIONS_IN_WINDOW:
        reasons.append(
            f"Iuran kurang dari {JKP_MIN_CONTRIBUTIONS_IN_WINDOW} bulan dalam "
            f"{JKP_WINDOW_MONTHS} bulan terakhir."
        )
    if bpjs_consecutive_months < JKP_MIN_CONSECUTIVE_MONTHS:
        reasons.append(
            f"Iuran berturut-turut kurang dari {JKP_MIN_CONSECUTIVE_MONTHS} bulan."
        )
    if age_years >= JKP_MAX_AGE:
        reasons.append(f"Usia sudah mencapai {JKP_MAX_AGE} tahun atau lebih.")
    if not jkn_active:
        reasons.append("Tidak terdaftar aktif di JKN.")

    eligible = not reasons
    return JkpEligibility(
        eligible=eligible,
        reasons=tuple(reasons),
        monthly_benefit=jkp_monthly_benefit(monthly_wage) if eligible else ZERO,
        months=JKP_MAX_MONTHS if eligible else 0,
    )


# ─── Final PPh 21 on severance (PP 68/2009) ──────────────────────────

# (lower bound exclusive in rupiah, upper bound inclusive or None, rate)
_SEVERANCE_TAX_BRACKETS: tuple[tuple[Decimal, Decimal | None, Decimal], ...] = (
    (Decimal("50000000"), Decimal("0")),
    (Decimal("100000000"), Decimal("0.05")),
    (Decimal("500000000"), Decimal("0.15")),
    (None, Decimal("0.25")),
)


def severance_final_tax(gross_lump_sum: Decimal) -> Decimal:
    """Final PPh 21 on a severance lump sum, applied progressively per PP 68/2009.

    The brackets are marginal, not flat: the first Rp 50,000,000 is untaxed and only the
    amount above each threshold is taxed at that rate.
    """
    if gross_lump_sum <= 0:
        return Decimal("0.00")
    tax = ZERO
    lower = ZERO
    for upper, rate in _SEVERANCE_TAX_BRACKETS:
        if gross_lump_sum <= lower:
            break
        ceiling = upper if upper is not None else gross_lump_sum
        taxable = min(gross_lump_sum, ceiling) - lower
        if taxable > 0:
            tax += taxable * rate
        lower = ceiling
        if upper is None:
            break
    return tax.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ─── PKWT compensation ───────────────────────────────────────────────


def pkwt_compensation(monthly_wage: Decimal, months: int) -> Decimal:
    """PKWT compensation: (contract duration in months / 12) x monthly wage.

    The duration is the contract that is ending (see ``ExitTerms.contract_months``), not
    total service. A renewed PKWT is compensated for the running contract, whose earlier
    terms were settled when they ended.
    """
    if months < 0:
        raise ValueError("months cannot be negative")
    return (Decimal(months) / MONTHS_PER_YEAR * monthly_wage).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


# ─── Full exit breakdown ─────────────────────────────────────────────


@dataclass(frozen=True)
class ExitTerms:
    """Everything the calculation needs about how the job ends and what it pays."""

    exit_type: ExitType
    monthly_wage_base: Decimal
    tenure_months: int
    # Duration of the contract that is currently ending. Used only for PKWT compensation,
    # which covers the running contract rather than total service; ``tenure_months`` stays
    # the basis for pesangon and UPMK. ``None`` falls back to ``tenure_months`` so callers
    # without contract dates keep the previous behaviour.
    contract_months: int | None = None
    employment_type: EmploymentType = EmploymentType.pkwtt
    bpjs_tk_active: bool = False
    bpjs_contributions_last_24_months: int = 0
    bpjs_consecutive_months: int = 0
    age_years: int = 0
    jkn_active: bool = False
    jht_balance: Decimal = ZERO
    unused_leave_days: int = 0
    # User toggle for the bankruptcy default described in ExitRules.
    normative_rights_collectable: bool | None = None


@dataclass(frozen=True)
class ExitEntitlements:
    """Computed statutory entitlements. All amounts are gross/net rupiah."""

    exit_type: ExitType
    regulation_version: str
    pesangon_months: Decimal
    upmk_months: Decimal
    gross_lump_sum: Decimal
    severance_tax: Decimal
    net_lump_sum: Decimal
    normative_collectable: bool
    liquid_normative: Decimal
    jkp: JkpEligibility
    jht_balance: Decimal
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def liquid_lump_sum(self) -> Decimal:
        """Lump sum that can actually be spent during the transition."""
        return self.liquid_normative + self.jkp.total_benefit


def compute_exit_entitlements(terms: ExitTerms) -> ExitEntitlements:
    """Apply the exit rules to one set of employment terms."""
    rules = EXIT_RULES[terms.exit_type]
    pesangon = pesangon_months(terms.tenure_months) * rules.pesangon_multiplier
    upmk = upmk_months(terms.tenure_months) * rules.upmk_multiplier

    gross = ((pesangon + upmk) * terms.monthly_wage_base).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    if rules.pays_pkwt_compensation:
        compensation_months = (
            terms.contract_months
            if terms.contract_months is not None
            else terms.tenure_months
        )
        compensation = pkwt_compensation(terms.monthly_wage_base, compensation_months)
        gross += compensation
        notes = [
            "Kompensasi PKWT dihitung sebagai (durasi kontrak berjalan / 12) x upah, "
            "tanpa JKP.",
        ]
    else:
        notes = [rules.note]

    # PP 68/2009 applies the final PPh 21 to the whole severance lump sum, including UPMK.
    tax = severance_final_tax(gross)
    net = gross - tax

    jkp = jkp_eligibility(
        exit_type=terms.exit_type,
        monthly_wage=terms.monthly_wage_base,
        bpjs_tk_active=terms.bpjs_tk_active,
        bpjs_contributions_last_24_months=terms.bpjs_contributions_last_24_months,
        bpjs_consecutive_months=terms.bpjs_consecutive_months,
        age_years=terms.age_years,
        jkn_active=terms.jkn_active,
    )
    if rules.jkp_eligible and not jkp.eligible:
        notes.append("JKP tidak dibayarkan: " + " ".join(jkp.reasons))

    collectable = terms.normative_rights_collectable
    if collectable is None:
        collectable = not rules.normative_illiquid_by_default
    if not collectable:
        notes.append(
            "Hak normatif dianggap tidak cair sesuai asumsi konservatif. Ubah toggle "
            "jika pesangon dan UPMK benar-benar dibayarkan."
        )

    return ExitEntitlements(
        exit_type=terms.exit_type,
        regulation_version=REGULATION_VERSION,
        pesangon_months=pesangon,
        upmk_months=upmk,
        gross_lump_sum=gross,
        severance_tax=tax,
        net_lump_sum=net,
        normative_collectable=collectable,
        liquid_normative=net if collectable else ZERO,
        jkp=jkp,
        jht_balance=terms.jht_balance,
        notes=tuple(notes),
    )


# ─── Exit-aware runway ───────────────────────────────────────────────


def runway_months(
    *,
    liquid_assets: Decimal,
    monthly_burn: Decimal,
    jkp_monthly: Decimal = ZERO,
    jkp_months: int = JKP_MAX_MONTHS,
) -> Decimal:
    """Closed-form runway that accounts for a temporary benefit.

    ``B`` is monthly burn, ``L`` liquid funds, ``J`` the monthly benefit and ``n`` its
    duration. While the benefit runs, only ``B - J`` is drawn from savings; after it ends
    the full burn resumes:

    * ``J == 0``            -> ``L / B``
    * ``L < (B - J) * n``   -> ``L / (B - J)``  (benefit outlives the money)
    * otherwise             -> ``n + (L - (B - J) * n) / B``

    When the benefit covers the whole burn (``B <= J``) savings are not drawn at all
    during the benefit period, so the second branch is skipped to avoid dividing by zero.
    """
    if monthly_burn <= 0:
        raise ValueError("monthly_burn must be positive")
    if liquid_assets < 0:
        raise ValueError("liquid_assets cannot be negative")
    benefit_months = Decimal(jkp_months) if jkp_monthly > 0 else ZERO
    if jkp_monthly <= 0:
        months = liquid_assets / monthly_burn
    else:
        net_burn = monthly_burn - jkp_monthly
        if net_burn <= 0:
            months = benefit_months + liquid_assets / monthly_burn
        else:
            covered = net_burn * benefit_months
            if liquid_assets < covered:
                months = liquid_assets / net_burn
            else:
                months = benefit_months + (liquid_assets - covered) / monthly_burn
    return months.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class RunwayLayer:
    """One stacked layer shown to the user, from bare savings outward."""

    key: str
    label: str
    runway_months: Decimal
    liquid_funds: Decimal
    monthly_benefit: Decimal


def runway_layers(
    *,
    liquid_assets: Decimal,
    monthly_burn: Decimal,
    entitlements: ExitEntitlements,
) -> tuple[RunwayLayer, ...]:
    """Stack the runway from savings only up to retirement savings included.

    Each layer is reported separately rather than collapsed into one number, because the
    later layers depend on claims the user has to actively file and on money they may not
    want to spend.
    """
    layers = [
        RunwayLayer(
            key="savings_only",
            label="Tabungan saja",
            runway_months=runway_months(
                liquid_assets=liquid_assets, monthly_burn=monthly_burn
            ),
            liquid_funds=liquid_assets,
            monthly_benefit=ZERO,
        )
    ]
    normative_liquid = liquid_assets + entitlements.liquid_normative
    layers.append(
        RunwayLayer(
            key="with_normative_rights",
            label="+ hak normatif",
            runway_months=runway_months(
                liquid_assets=normative_liquid, monthly_burn=monthly_burn
            ),
            liquid_funds=normative_liquid,
            monthly_benefit=ZERO,
        )
    )
    with_jkp = runway_months(
        liquid_assets=normative_liquid,
        monthly_burn=monthly_burn,
        jkp_monthly=entitlements.jkp.monthly_benefit,
        jkp_months=entitlements.jkp.months,
    )
    layers.append(
        RunwayLayer(
            key="with_jkp",
            label="+ JKP",
            runway_months=with_jkp,
            liquid_funds=normative_liquid,
            monthly_benefit=entitlements.jkp.monthly_benefit,
        )
    )
    with_jht = normative_liquid + entitlements.jht_balance
    layers.append(
        RunwayLayer(
            key="with_jht",
            label="+ JHT (menggunakan dana pensiun)",
            runway_months=runway_months(
                liquid_assets=with_jht,
                monthly_burn=monthly_burn,
                jkp_monthly=entitlements.jkp.monthly_benefit,
                jkp_months=entitlements.jkp.months,
            ),
            liquid_funds=with_jht,
            monthly_benefit=entitlements.jkp.monthly_benefit,
        )
    )
    return tuple(layers)


# ─── Cost-of-living sanity check (T10) ───────────────────────────────

# National per-capita poverty line (garis kemiskinan) from BPS. Update this constant when
# BPS publishes a new figure; the version tag is surfaced to the client so a stale
# threshold is visible rather than silent. Confirm the figure against the latest BPS
# release before submission: the value below is the September 2024 national figure.
BPS_POVERTY_LINE_PER_CAPITA = Decimal("595242")
BPS_POVERTY_LINE_VERSION = "bps-2024-09"


def months_between(start: date, end: date) -> int:
    """Whole calendar months from ``start`` to ``end`` (floor, never negative).

    Used to measure the length of the PKWT that is currently ending.
    """
    if end <= start:
        return 0
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        months -= 1
    return max(months, 0)


def contract_duration_months(start: date | None, end: date | None) -> int | None:
    """Whole months covered by a PKWT, or ``None`` when either bound is missing."""
    if start is None or end is None:
        return None
    return months_between(start, end)


def add_months(start: date, months: Decimal) -> date:
    """Add a fractional month count to a date, calendar-aware on whole months.

    Whole months advance the calendar month so month lengths are respected, and the
    fractional remainder is converted to days at the average month length.
    """
    whole = int(months)
    remainder_days = int(
        ((months - whole) * Decimal("30.44")).to_integral_value(rounding=ROUND_HALF_UP)
    )
    month_index = start.month - 1 + whole
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    # Clamp to the last valid day so 31 Jan + 1 month does not overflow.
    day = min(start.day, monthrange(year, month)[1])
    return date(year, month, day) + timedelta(days=remainder_days)


def essential_expenses_per_person(
    monthly_essential_expenses: Decimal, dependents: int
) -> Decimal:
    """Essential spend per person supported, treating the user as one household member."""
    household = 1 + max(dependents, 0)
    return (monthly_essential_expenses / Decimal(household)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def cost_of_living_warning(
    monthly_essential_expenses: Decimal, dependents: int
) -> str | None:
    """Flag an implausibly low essential spend, which would inflate the runway.

    Compares spend per person against the national poverty line. A user reporting less
    than that per person is likely under-reporting expenses, which makes the runway
    look longer than it is.
    """
    per_person = essential_expenses_per_person(
        monthly_essential_expenses, dependents
    )
    if per_person >= BPS_POVERTY_LINE_PER_CAPITA:
        return None
    return (
        "Pengeluaran esensial per orang lebih rendah dari garis kemiskinan BPS "
        f"({BPS_POVERTY_LINE_VERSION}). Angka ini mungkin kurang lengkap, sehingga "
        "masa aman finansial bisa terlihat lebih panjang daripada kenyataan."
    )
