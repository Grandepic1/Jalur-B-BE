# AI and scoring

Jalur B uses Gemini through the official Google Gen AI SDK for bounded classification
and Indonesian explanations. Numeric scores are calculated by backend code under
`career-resilience-v2`; the model never supplies final numeric scores. Every assessment
persists the `scoring_version` it was scored with, so assessments created under
`career-resilience-v1` keep the numbers and the formula they were created with.

## Provider

- Provider: Gemini Developer API through the Google Gen AI SDK
- Default model: `gemini-3.8-flash`
- Responses use JSON Schema mode and are validated again with Pydantic.
- Google may use unpaid-service prompts and responses to improve its products. Use a
  billing-enabled Gemini API project for Google's paid-service data protections.
- Prompt version: `career-analysis-v1`
- Provider failures do not create partial assessment snapshots.

Model knowledge is not a substitute for sourced live market data. Market-baseline refresh uses
Gemini's Google Search grounding and refuses to create a draft when the response contains no
grounded citations. Existing approved baselines remain usable. Assessments prefer matching
signals from the current approved
baseline and expose the immutable `market_baseline_version`; unmatched subjects remain model
estimates and do not claim grounding.

## Market baseline governance

- Set `MARKET_BASELINE_ADMIN_KEY` to protect management operations. Management calls also
  require a verified user access token so the creator and approver are auditable.
- `POST /api/market-baselines/refresh` uses Gemini Google Search grounding and requires at
  least one citation before it creates a draft.
- Review drafts with `GET /api/market-baselines?status=draft` and their citations.
- Approve with `POST /api/market-baselines/{id}/approve`, or reject with
  `POST /api/market-baselines/{id}/reject`. Approving archives the previous baseline and never
  mutates historical assessment snapshots.
- Authenticated clients can read the active source set through
  `GET /api/market-baselines/current`.
- Refresh scheduling is deliberately external to the API process so retries, alerts, and the
  desired monthly or quarterly cadence can be managed by the deployment platform.

## Category mappings

| Category | Score |
| --- | ---: |
| weak | 35 |
| moderate | 65 |
| strong | 85 |
| low exposure | 25 |
| medium exposure | 55 |
| high exposure | 80 |
| declining relevance | 35 |
| stable relevance | 65 |
| rising relevance | 90 |

## Formulas

Every weight lives in `app/core/scoring_config.py` with the reason for its value recorded
in a docstring. A weight group must sum to exactly 1.00, and no raw input may reach a final
score through two different paths; both invariants are enforced by
`tests/test_scoring_weights.py`.

AI Exposure is the arithmetic mean of classified activity exposure scores.

Skill Relevance is the arithmetic mean of the user's classified skill relevance scores.

```text
Career Risk =
  40% activity automation exposure
  + 25% market-demand risk
  + 20% skill-dependency risk
  + 15% industry-volatility risk
```

```text
Pivot Match =
  55% skill fit
  + 20% activity fit
  + 15% experience fit
  + 10% industry fit
```

Financial Readiness compares the exit-aware runway against the user's **personal** target,
not a flat six months:

```text
personal target (months) = T_prep(chosen pivot role) + T_search
exit runway (months)     = R_exit, from app/core/entitlements.py
Financial Readiness      = min(exit runway / personal target, 1) * 100
```

`T_search` is an explicit, visible, user-adjustable assumption (default three months); it is
never presented as measured data. A flat six-month line is still returned as
`reference_runway_months` for display, but it is never the scoring denominator.

The current Financial Readiness value is recalculated in the same transaction whenever the
financial profile, any asset, or the employment terms change. Existing layoff simulations
remain immutable snapshots.

```text
Career Readiness =
  30% performance and growth
  + 30% skill relevance
  + 20% adaptability
  + 20% mobility
```

```text
Overall Resilience =
  50% career readiness
  + 50% financial readiness
```

Career Readiness (formerly "Career Health") contains no financial component, and Overall
Resilience composes the two aggregates rather than re-listing their inputs. Financial
Readiness, Skill Relevance, and Mobility previously each reached Overall Resilience twice.

Health levels use `<60 low`, `60-74.99 medium`, and `>=75 high`. Risk and exposure levels
use `<40 low`, `40-69.99 medium`, and `>=70 high`.

Data Confidence measures availability of profile identity, responsibilities, skills,
evidence/performance context, and financial data. It is not prediction accuracy. A missing
component is never replaced by a placeholder value: `average([])` returns `None`, the
component is dropped and the remaining weights renormalized, Data Confidence is reduced,
and the component name is returned in `insufficient_data` so the client can show "data
belum cukup" rather than a number.

## Weight sensitivity

`uv run python scripts/scoring_sensitivity.py` shifts every weight by +/-10 percentage
points, renormalizes the group, and measures how much the pivot ranking moves. The headline
metric is the discordant-pair flip rate: over every pair of pivot roles whose relative order
can actually change, the share whose order reverses under a shift. Pairs in which one role
is at least as strong as the other on every dimension are excluded, because positive weights
can never reorder them; this removes the all-strong role that made the earlier top-role test
impossible to fail. The script exits non-zero when the worst shift flips more than 10% of
comparable pairs. Recorded result for `career-resilience-v2`: worst 9.0%, mean 7.4%.

## Exit-aware runway

`app/core/entitlements.py` is a pure, I/O-free module implementing PP 35/2021 Art. 40
(pesangon and UPMK tenure tables) and the exit-ground multipliers (PP 35/2021 Arts. 41–52),
JKP eligibility and cash benefit (PP 37/2021 as amended by PP 6/2025), the final PPh 21 on
severance (PP 68/2009), and PKWT compensation. It contains no LLM call at any point.

`POST /api/financial/exit-runway` accepts an `exit_type` and returns every stacked layer
(savings only, plus statutory rights, plus JKP, plus JHT) rather than one collapsed number,
along with the date the money runs out, the JKP claim deadline, and a Transition Gap per
pivot role. Each result stores `regulation_version` so a later change to the law never
rewrites history.

The bankruptcy ground defaults to treating pesangon and UPMK as not collectable, because
an insolvent estate frequently does not pay them; JKP is still counted. The user can
override this, and the override is recorded on the result.

## API workflow

- `POST /api/ai/assessments` creates one consistent F1-F4 snapshot bundle.
- `GET/PUT /api/financial/employment-terms` stores the wage, contract type, tenure, and
  BPJS/JKN facts the exit-aware runway depends on.
- `POST /api/financial/exit-runway` and `GET /api/financial/exit-runway/latest` compute and
  read the exit-aware runway with all statutory layers.
- `POST /api/ai-exposure`, `/api/career-risk`, `/api/career-pivot`, and
  `/api/career-health` run the same complete bundle and return one section.
- Each feature has a `/latest` read endpoint.
- `POST /api/layoff-simulations` consumes the latest F1-F4 and financial snapshots.
- `POST /api/evidence/assistant/draft` generates a reviewable Evidence draft.
- `POST /api/evidence/assistant` saves a reviewed AI-assisted Evidence item.
- `GET /api/ai/insights` returns a weekly cached insight and server-prioritized action.
- `POST /api/profile/cv/preview` extracts PDF or DOCX text locally, then returns a
  reviewable profile, skill, and career-history draft without changing account data.
- `POST /api/profile/cv/confirm` atomically applies the reviewed non-null profile fields,
  merges skills, and saves the reviewed career history. The frontend sends the
  user-edited values; the source CV file is not retained.
- Evidence `impact` is optional for both human and AI-assisted entries.

Assessment snapshots store the model, prompt version, scoring version, and factual input
snapshot. Historical scores are not recalculated when formulas or models change.

## Market baseline matching

Baseline subject names are normalized (case, punctuation, whitespace, and a small
synonym table) and matched by name equality or whole-word containment, so "Sales" matches
"Sales Executive". Exact lowercase equality previously meant near-identical names never
matched and the system fell back to the model silently.

Each assessment reports `baseline_coverage_percent`: the share of subjects (role, industry,
skills) matched from the approved baseline. Everything not matched is a model estimate and
is labelled "estimasi model" in the factor explanation. Role matching by ISCO-08 code is
not implemented yet; see `PLOT_HOLES_ARGUMENT.md`.

## Limitations

- Results are decision support, not employment predictions.
- User-authored facts can be incomplete or inaccurate.
- CV text sent through Gemini's unpaid service may be used to improve Google products. Use a
  billing-enabled project when paid-service data protections are required.
- Scanned PDFs require OCR and are rejected by the current text-only CV extractor.
- A signal is described as sourced only when its assessment includes a non-null approved
  `market_baseline_version`; unmatched subjects are explicitly model estimates and are
  labelled as such.
- AI Exposure classifications are still model output mapped to fixed anchors (25/55/80).
  They are not yet anchored to an external exposure index, so the exposure number remains
  unverifiable by a third party. This is the largest outstanding scoring weakness.
- The layoff simulation is now driven by the exit ground, not by a time choice: resignation,
  efficiency dismissal, PKWT expiry, and bankruptcy produce different runway and Transition
  Gap numbers. Action-item due dates are still scheduled from the exit ground rather than
  from a user-chosen date.
- Transition Gap depends on `T_prep`, which is estimated from the number of concrete skill
gaps. The estimate is a heuristic with no external source and is labelled as such.
