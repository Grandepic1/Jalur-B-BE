# AI and scoring

Jalur B uses Gemini for bounded classification and Indonesian explanations. Numeric scores
are calculated by backend code under `career-resilience-v1`; Gemini never supplies final
numeric scores.

## Provider

- Provider: Google Gemini API through Google AI Studio
- Default model: `gemini-3.5-flash-lite`
- Prompt version: `career-analysis-v1`
- Structured JSON is validated with Pydantic before any assessment is persisted.
- Provider failures do not create partial assessment snapshots.

Model knowledge is not a substitute for sourced live market data. Reviewed market baselines
use Gemini Google Search grounding, retain citation and grounding metadata, and remain drafts
until explicitly approved. Assessments prefer matching signals from the current approved
baseline and expose the immutable `market_baseline_version`; unmatched subjects remain model
estimates and do not claim grounding.

## Market baseline governance

- Set `MARKET_BASELINE_ADMIN_KEY` to protect management operations. Management calls also
  require a verified user access token so the creator and approver are auditable.
- A scheduled job can call `POST /api/market-baselines/refresh` with the complete role,
  industry, and skill subject catalog. Gemini must return Google Search grounding citations or
  the draft is rejected.
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

```text
Financial Readiness = min(runway months / 6 * 100, 100)
```

```text
Career Health =
  25% performance and growth
  + 25% skill relevance
  + 15% adaptability
  + 15% mobility
  + 20% financial readiness
```

```text
Overall Resilience =
  30% financial readiness
  + 30% career health
  + 20% skill relevance
  + 20% job mobility
```

Health levels use `<60 low`, `60-74.99 medium`, and `>=75 high`. Risk and exposure levels
use `<40 low`, `40-69.99 medium`, and `>=70 high`.

Data Confidence measures availability of profile identity, responsibilities, skills,
evidence/performance context, and financial data. It is not prediction accuracy.

## API workflow

- `POST /api/ai/assessments` creates one consistent F1-F4 snapshot bundle.
- `POST /api/ai-exposure`, `/api/career-risk`, `/api/career-pivot`, and
  `/api/career-health` run the same complete bundle and return one section.
- Each feature has a `/latest` read endpoint.
- `POST /api/layoff-simulations` consumes the latest F1-F4 and financial snapshots.
- `POST /api/evidence/assistant/draft` generates a reviewable Evidence draft.
- `POST /api/evidence/assistant` saves a reviewed AI-assisted Evidence item.
- `GET /api/ai/insights` returns a weekly cached insight and server-prioritized action.
- Evidence `impact` is optional for both human and AI-assisted entries.

Assessment snapshots store the model, prompt version, scoring version, and factual input
snapshot. Historical scores are not recalculated when formulas or models change.

## Limitations

- Results are decision support, not employment predictions.
- User-authored facts can be incomplete or inaccurate.
- A signal is described as sourced only when its assessment includes a non-null approved
  `market_baseline_version`; unmatched subjects are explicitly model estimates.
- The three layoff scenarios change timing and action due dates. They do not project savings
  before a layoff because the current financial profile does not store monthly income.
