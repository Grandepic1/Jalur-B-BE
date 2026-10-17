# Jalur B — Plot Hole Response: What Was Fixed and What Still Needs a Decision

This document responds to *"Jalur B — Technical Plot Holes & Fix Spec (for Developers)"*.

It has three parts:

1. **Fixed** — the findings that were unambiguous and are now implemented.
2. **Argued** — the findings that are *not* clear, where the spec leaves a real decision
   open. Each one states the decision, the evidence, and what I recommend.
3. **Interpretation decisions** — places where the spec is internally ambiguous and I had to
   choose a reading. These are the ones most likely to be challenged, so the reasoning and
   the arithmetic are written out.

---

## 1. Fixed

| ID | Finding | Evidence it is fixed |
|---|---|---|
| T1 | Overall Resilience counted Financial Readiness, Skill Relevance, and Mobility twice | `CAREER_READINESS_WEIGHTS` has no financial component; `RESILIENCE_WEIGHTS` is exactly `{career_readiness 0.50, financial_readiness 0.50}`. `overall_resilience()` takes **only** those two arguments, so the double count is impossible by signature. `SCORE_VERSION` is now `career-resilience-v2`. |
| T2 | Runway ignored exit type and statutory rights | New pure module `app/core/entitlements.py` (PP 35/2021 Art. 40 tables, PP 37/2021/PP 6/2025 multipliers, JKP, PP 68/2009 final PPh 21, PKWT compensation). New `employment_terms` table, `POST /api/financial/exit-runway`, stacked layers, `regulation_version`. |
| T3 | Runway and pivot preparation time never compared; simulation took `max()` over all roles | New `app/core/transition.py`; `TG = R_exit − (T_prep(role) + T_search)`; preparation now comes from the selected role (default highest match score) via `select_preparation_role`. |
| T5 | `average()` silently returned 50 for empty input | `average()` returns `None`. `weighted_optional()` drops missing components and renormalizes. Unmeasurable components are reported in `insufficient_data` and lower Data Confidence. |
| T6 | Baseline matched on exact lowercase strings, fell back silently | Names are normalized (case, punctuation, whitespace, small synonym table) and matched by equality or whole-word containment, so "Sales" matches "Sales Executive". `baseline_coverage_percent` reports how much came from the baseline; everything else is labelled `estimasi model`. |
| T7 | Flat 6-month target for everyone | Personal target = `T_prep(chosen role) + T_search`. Six months survives only as `reference_runway_months` for display and is never the scoring denominator. |
| T8a | Time scenarios changed nothing but due dates | `LayoffSimulationRequest` now takes `exit_type`. All five exit grounds produce different runway **and** different Transition Gap values. |
| T9 | Pivot Match and Career Risk weights had no justification | All weights moved to `app/core/scoring_config.py` with a rationale per weight, plus `scripts/scoring_sensitivity.py` (±10pp sweep with a stability verdict). |
| T10 | `dependents` collected but unused | Used in `cost_of_living_warning()`: essential spend per person is compared against the BPS per-capita poverty line and a warning is returned when it looks under-reported, which is exactly when the runway would be too optimistic. |
| T14 | README stale | Title, English summary added at the top, broken `Plan.md` link removed, product URL added, roadmap split into implemented vs in-development. |

Test suite: **145 passing** (was 76). Migrations applied; three new tables plus six new
`layoff_simulations` columns verified present in the database.

---

## 2. Argued — findings that are not clear

### T4 — Anchoring AI Exposure to ILO WP140

**What the spec asks for.** Replace the fixed 25/55/80 anchors with the ILO *Generative AI and
Jobs: A Refined Global Index of Occupational Exposure* (Gmyrek et al., ILO Working Paper 140,
2025), using its 1–4 exposure gradient per ISCO-08 4-digit code, mapped through KBJI 2014.

**What I found.** The data does exist in publishable form. The ILO hosts the working paper with
an explicit annex titled *"Annex 1. Exposure by 4-digit ISCO-08 occupation"*
(<https://webapps.ilo.org/static/english/intserv/working-papers/wp140/index.html>), and the
paper reports scoring 4-digit ISCO-08 occupations into four progressively increasing exposure
gradients. So the spec's precondition — "make sure the gradient data per ISCO code is
available" — is satisfied in principle.

**Why I did not implement it now.**

1. **The annex is a rendered web page, not a dataset.** I could not confirm a
   machine-readable export (CSV/XLSX/JSON) of the per-ISCO gradient. Building the feature means
   either scraping a rendered annex or transcribing several hundred occupation rows by hand.
   Both are plausible, but neither is a decision I should make silently — a transcription error
   would corrupt the headline exposure number while looking authoritative.
2. **It is a chain of three lookups, and the weakest link is not the ILO data.** The chain is
   `free-text job title → ISCO-08 4-digit → ILO gradient → 0–100 score`. Steps one and two are
   now LLM classification plus user confirmation, which the spec itself acknowledges. Adding
   external grounding at step three does not make steps one and two verifiable. A judge who
   asks "how did you decide this person is a 2512?" still gets an LLM answer.
3. **It changes what the number means, and the UI would have to change with it.** Today the
   exposure score is an average over the user's *own activities*. The ILO index is an
   occupation-level gradient. Those are different quantities. Replacing one with the other is a
   product decision about what AI Exposure is supposed to represent, not a bug fix — and the
   spec is only half-way to that decision, because it keeps per-activity LLM classification as
   "explanation" without saying which number the user is shown as *the* score.

**Recommendation.** Implement it, but as an explicit two-number model rather than a swap:
`occupation_gradient` (sourced, verifiable, ILO-anchored) shown as the headline, and
`activity_exposure` (model-classified, useful for the action plan) shown as a breakdown. Label
the second as a model estimate, which T6's coverage reporting now already makes possible. Per
the spec's own instruction, this is written as **in development**, not as a claim.

**What is needed to unblock it.** One decision from the product owner: download or transcribe
the ILO 4-digit gradients, and confirm which of the two numbers is the headline.

### T6 (role half) — Matching roles by ISCO code

**Blocked on T4 by construction.** The spec's own fix for T6 is "match role via the ISCO code
from T4". Until role → ISCO codes are resolved and the ILO/ISCO table exists, there is no code
to match on. I implemented the half that is independent — skill normalization and coverage
reporting — because skill signal matching is where most of the silent fallback actually
happened (the user's skill list is much longer than one role name).

**The gap that remains.** Role and industry signals still match by name. Containment matching
makes "Sales" match "Sales Executive", but "Sales Executive" will *not* match "Account
Manager" even though both may be ISCO 3322. Coverage reporting means this is now visible
(`baseline_coverage_percent` will be low), but visible is not the same as correct.

### T11, T12, T13 — B-Credits, regulation versioning, UU PDP

The spec marks these **P2 — do not do now**, and I agree. Two notes:

- **T12 is already structurally done.** `regulation_version` is stored on every
  `exit_runway_calculations` row and on every `layoff_simulations` row, exactly as
  `scoring_version` is. When the new Manpower Law changes the pesangon tables, only
  `app/core/entitlements.py` needs updating; historical results stay attributable to the rules
  that produced them. The "build a versioning system" work item is mostly closed as a side
  effect of T2.
- **T13 is a claim I would not make yet.** `DELETE /api/auth/account` exists and the storage
  cleanup queue handles CV and evidence objects, but there is no explicit consent step before
  financial input, no documented retention period, and no financial-data-only deletion action.
  Grepping the repository for any mention of UU PDP returns nothing. Per the spec, one
  paragraph in the paper's Tech Stack section is the right scope for now — **but the paper
  should not claim PDP compliance.** "We store salary, savings, and debt data and describe our
  retention approach" is defensible; "we comply with UU PDP" is not, on this codebase.

### T15, T16 — Frontend labels and landing page

**Not in this repository.** The "Akurasi 100%" labels and the hero section live in the frontend,
which is a separate codebase. I cannot fix or verify them from here.

What the backend now provides so the frontend fix is a pure copy change:

- Data Confidence is documented as "availability of data, not prediction accuracy" in
  `AI_SCORING.md`, matching the proposal's own wording.
- `insufficient_data` is returned on the exposure, risk, and health responses, so "data belum
  cukup" is a real state the UI can render rather than a placeholder.
- `baseline_coverage_percent` distinguishes sourced signals from model estimates, so the
  "already grounded" claim can be made precisely or not at all.

**Recommendation for T15:** the label change is correct and cheap, but it should go further
than "Kelengkapan data" — the response already carries `baseline_coverage_percent`, so the UI
can say "How much of this came from a reviewed source: X%". That claim is checkable, which is
the whole point of T6.

---

## 3. Interpretation decisions

These are the places the spec could be read two ways. I picked a reading, implemented it, and
wrote the arithmetic down so it can be reversed cheaply.

### 3.1 Bankruptcy: the multiplier table and the persona table disagree

The spec's multiplier table gives bankruptcy `pesangon 0.5×`, `UPMK 1×`, `JKP yes`, with the
note *"Default konservatif: pesangon dianggap tidak cair; user bisa toggle"*. The persona table
then expects Rani's bankruptcy runway to be **5.00** months.

Those two do not reconcile. With savings 15jt, burn B = 6jt, JKP J = 3jt, benefit length n = 6:

| Treatment of normative rights | L | Runway |
|---|---:|---:|
| Pesangon illiquid, UPMK **liquid** (14jt) | 29jt | 6 + (29−18)/6 = **7.83** |
| Pesangon liquid (0.5× = 17.5jt), UPMK liquid | 46.5jt | 6 + (46.5−18)/6 = **10.75** |
| **Pesangon and UPMK both illiquid** | 15jt | 15 < 18, so 15/3 = **5.00** ✓ |

Only the last row reproduces the spec's own expected value. I implemented that, so the
conservative default treats **both** pesangon and UPMK as not collectable for bankruptcy, with
JKP still paid and a user toggle to override. The toggle is per calculation and is recorded on
the result.

The other four grounds reconcile exactly as written (2.50, 3.67, 10.75, 13.67 all verified).

### 3.2 Final PPh 21 applies to pesangon **plus** UPMK

The spec's boundary example is "pesangon Rp 60 jt → 5% on Rp 10 jt". That case is under three
years of service, where UPMK is zero, so it is consistent with either reading. I applied the
final tax to the combined severance lump sum, which matches Indonesian practice (UPMK forms
part of the severance tax base). If the intent was pesangon-only, `severance_final_tax()` takes
a single gross argument and the call site in `compute_exit_entitlements()` is the only line to
change.

### 3.3 New fields live in a new table, not on `financial_profiles`

The spec offers either. I chose a separate `employment_terms` table because:

- Employment facts (wage, contract type, BPJS participation) are governed by labour law;
  `financial_profiles` holds the user's budget. Mixing them makes the T13 privacy story
  harder, since financial data and employment data would then have the same deletion path.
- `regulation_version` belongs with the entitlements result, not the budget row.
- The repo already uses one-to-one satellites for `user_profiles` and `user_cvs`, so this
  follows an existing convention rather than introducing one.

### 3.4 `average()` returns `None`, and three call sites still hard-fail

The spec says missing components should be dropped and weights renormalized. I implemented
that. But three components are *guaranteed* present by the provider schema
(`activities` has `min_length=1`, `pivot_roles` has `min_length=1`, and the exact-skill-set
check guarantees matched skills). For those, `None` means the provider violated its own
contract, so the code raises `502` instead of quietly scoring. Silently dropping a component
that can never legitimately be missing would hide a real provider bug.

Genuinely optional components — no financial profile, no pivot analysis — *do* renormalize and
*do* report through `insufficient_data`.

### 3.5 Breaking API changes

These are deliberate and follow from the requested behaviour:

| Change | Effect |
|---|---|
| `HealthAssessmentResult.factors` drops from 5 to 4 entries | Financial Readiness is no longer a Career Readiness factor. Clients rendering a fixed 5-bar layout must be updated. |
| `LayoffSimulationRequest.scenario` → `exit_type` (+ `search_time_months`, `preferred_role_name`) | Existing clients sending `scenario` get a 422 (`extra="forbid"`). |
| `POST /api/layoff-simulations` now requires `employment_terms` | Added to the `missing` prerequisite list with the code `simulation_prerequisites_missing`. The frontend must collect wage and contract type before simulating. |
| `FinancialRunwayPreview.target_runway_months` changed meaning | It is now the personal target. `reference_runway_months` carries the old six-month value. |

Stored assessments are **not** recalculated. `_health_response` no longer recomputes the score
from breakdowns, because Career Readiness has no component that changes after creation —
recomputing would have silently rewritten `career-resilience-v1` history with v2 weights.

### 3.6 The BPS poverty line constant needs confirmation

`BPS_POVERTY_LINE_PER_CAPITA` is `595,242` tagged `bps-2024-09`. I could not verify the latest
published figure from here. It is surfaced to clients as `poverty_line_version` so a stale
threshold is visible rather than silent, but **someone should confirm it against the current
BPS release before the demo.**

### 3.7 `T_prep` is still a heuristic

`preparation_months_for_gap_count()` computes `clamp(round(gaps × 1.5), 1, 12)`. It is now in
one shared module used by both the pivot analysis and the Transition Gap, and it is documented
as a heuristic. It is still not sourced from any dataset — it is the same class of weakness as
T4, just smaller, and it now sits directly under the headline Transition Gap number. A judge
who asks "where does four months come from" gets an honest "from the number of skill gaps,
it is an estimate", which is better than the previous situation but not a strong answer.

---

## 4. Verification performed

| Check | Result |
|---|---|
| `uv run python -m unittest discover -s tests` | **145 passed** (was 76) |
| Rani persona, all five exit grounds, via `compute_exit_entitlements` + `runway_months` | 2.50 / 3.67 / 5.00 / 10.75 / 13.67 — exact match |
| Boundary cases (wage above Rp5jt, tenure exactly 36 months, 11 months of contributions, Rp60jt severance tax) | all pass |
| `alembic upgrade head` | applied; `alembic current` = `d4a7f0c23e54` |
| New tables/columns present in PostgreSQL via `information_schema` | `employment_terms`, `exit_runway_calculations` (33 cols), `simulation_role_transitions` (12 cols), 6 new `layoff_simulations` cols |
| OpenAPI contract for the new routes | `/api/financial/employment-terms` GET+PUT, `/api/financial/exit-runway` POST, `/exit-runway/latest` GET; request/response fields present |
| End-to-end through the endpoint against the real database (throwaway user: profile + asset + terms → `create_exit_runway` for all five grounds) | all five matched the spec's expected runway; 5 distinct values; layers stacked monotonically; JKP/net/tax/claim-deadline populated; the new contract-type guard rejected `pkwt_ends_on_schedule` for a PKWTT employee with 409 |
| `uv run python scripts/scoring_sensitivity.py` | STABLE — no ±10pp shift let another pivot role strictly outrank the leader |

Two test failures encountered during development were **my own wrong expectations**, not code
bugs (a fractional-month day count and a `weighted_optional` renormalization figure). Both were
corrected in the tests; the implementations were unchanged.

## 5. Could not verify

- **No authenticated HTTP round trip.** The end-to-end check called the endpoint function with a
  real `AsyncSession`; it did not go through JWT verification or the ASGI layer. The route
  contract is covered by the OpenAPI test, and auth is unchanged, but a live `curl` against a
  running server with a real token has not been done.
- **No frontend.** T15 and T16 cannot be verified or fixed from this repository.
- **ILO data not downloaded.** T4 remains unimplemented; the recommendation above is based on
  the annex being published, not on having the gradient values in hand.
- **BPS poverty line not confirmed** against the current release (see 3.6).
- **The ERD canvas layout is unverified.** `jalurB-v2.erd` was regenerated from the
  SQLAlchemy metadata by `scripts/generate_erd.py` (additive and idempotent): +3 tables,
  +67 columns, +3 relationships, +4 indexes, and 6 columns added to the existing
  `t-layoff-simulations`, with **zero entities removed or rewritten**. Cross-reference
  integrity was checked programmatically (no dangling column, table, relationship, or index
  references) and `--check` confirms the file matches the models. What I have *not* done is
  open the result in the ERD Editor to confirm the new tables do not overlap existing boxes
  on the canvas — I validated the data model, not the visual layout.
