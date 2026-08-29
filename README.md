# Jalur B — Backend

Career & financial resilience platform: membantu pekerja mempersiapkan diri menghadapi PHK dan perubahan dunia kerja sebelum terjadi. See [Plan.md](Plan.md) for the full product spec and [erd.md](erd.md) for the database design.

## Stack

- **FastAPI** + **SQLAlchemy 2 (async)** + **asyncpg**
- **Alembic** for migrations
- **PostgreSQL** (Supabase pooler or local)
- **uv** as package manager

## Setup

```bash
# 1. Install dependencies
uv sync

# 2. Configure environment
cp .env.example .env
# edit DATABASE_URL to point at your Postgres instance

# 3. Run migrations
uv run alembic upgrade head

# 4. Start the dev server
uv run uvicorn main:app --reload
```

Health check: `GET http://localhost:8000/health`

## Database

Schema source of truth: `jalurB-v2.erd` (+ [erd.md](erd.md)). After changing anything under `app/models/`:

```bash
uv run alembic revision --autogenerate -m "describe change"
uv run alembic upgrade head
```

## Project structure

```
app/
├── api/        # route handlers (per-feature routers)
├── core/       # settings (.env), async engine & session factory
├── models/     # SQLAlchemy ORM models
└── schemas/    # Pydantic request/response schemas
alembic/        # migration environment (wired to app settings + Base.metadata)
main.py         # FastAPI app entrypoint
```

## Roadmap (features per Plan.md)

1. Career Health Score
2. Career Risk Scanner
3. AI Exposure + Skill Relevance
4. Career Pivot Map
5. Career Evidence Vault
6. Personal Runway
7. What If I Get Fired?

Auth (register/login) is planned next on top of the existing `users` table.

## Authentication

The API supports password registration/login and Google OAuth:

- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `POST /api/auth/verify-email`
- `POST /api/auth/resend-verification`
- `POST /api/auth/forgot-password`
- `POST /api/auth/reset-password`
- `POST /api/auth/change-password`
- `POST /api/auth/logout`
- `GET /api/auth/google/start`
- `GET /api/auth/google/callback`
- `POST /api/auth/google/exchange`

Google returns a short-lived, single-use exchange code to the frontend. Access tokens
are never included in the OAuth redirect URL. A verified Google identity is linked to
an existing account with the same normalized email only when Google is authoritative for
the address (`gmail.com` or a matching Google Workspace hosted domain). If that form
account was not email verified, its password is invalidated and previous tokens are
revoked during linking to prevent pre-registration account takeover.

Required production environment variables are documented in `.env.example`. Generate a
unique `JWT_SECRET_KEY`; never reuse the Google client secret as the JWT key.
Configure SMTP before enabling form registration so verification and password-reset links
can be delivered. In local `DEBUG=true` mode, email bodies are written to the backend log.
When SMTP is unset, `AUTH_DEV_AUTO_VERIFY_EMAIL=true` allows local form-auth testing by
auto-verifying new users; this switch is ignored unless `DEBUG=true`.

For a Vercel frontend and separately hosted API:

1. Set `FRONTEND_URL` and `CORS_ORIGINS` to the production Vercel/custom origin.
2. Set a project-specific `CORS_ORIGIN_REGEX` only if preview deployments need auth.
3. Set `BACKEND_URL` to the public API origin.
4. In Google Cloud, register this authorized redirect URI exactly:
   `https://<api-domain>/api/auth/google/callback`.
5. Add the frontend production and approved preview origins to Google OAuth's authorized
   JavaScript origins.

## Onboarding API

All onboarding routes require a verified bearer-token user:

- `GET /api/onboarding` returns completion state, profile, and selected skills.
- `PUT /api/onboarding` creates or replaces onboarding data idempotently.
- `GET /api/onboarding/options` returns career goals plus available industries and skills.

`PUT /api/onboarding` accepts canonical backend values:

```json
{
  "full_name": "Joan Orlando",
  "current_role_name": "Backend Engineer",
  "industry_name": "Technology",
  "work_duration_months": 24,
  "is_first_job": false,
  "daily_activities": "Build and maintain APIs",
  "career_goal": "level_up",
  "target_role_name": "Senior Engineer",
  "target_industry_name": "Technology",
  "skills": ["Python", "API Design"]
}
```

Career-goal values are `grow_current`, `level_up`, `change_role`, `change_industry`, and
`undecided`. Skill names are case-insensitively unique, and each user may submit 1–8.

## Profile API

Verified users who completed onboarding can use:

- `GET /api/profile` to retrieve account identity, career profile, and selected skills.
- `PATCH /api/profile` to update profile-owned fields.
- `GET /api/profile/skills` to list skill proficiency and experience.
- `PUT /api/profile/skills/{skill_id}` to add or replace proficiency data.
- `DELETE /api/profile/skills/{skill_id}` to remove a skill from the profile.

Email and username are intentionally not editable through the profile endpoint because
account identity changes require separate verification flows.

## Master Data API

Verified users can query paginated catalogs with `limit`, `offset`, and optional `q`:

- `GET /api/master/industries`
- `GET /api/master/roles` (`industry_id` filter supported)
- `GET /api/master/skills` (`category` and `market_trend` filters supported)
- `GET /api/master/tools`

Responses use `{ "items": [], "total": 0, "limit": 50, "offset": 0 }`.

## Financial API

All financial routes require a verified bearer-token user. Individual assets are the
source of truth for savings; profile settings only store monthly burn inputs.

- `GET /api/financial` returns settings, assets, totals, and the current runway preview.
- `PUT /api/financial` creates or replaces monthly expense, debt, dependent, and currency settings.
- `GET /api/financial/assets` lists assets.
- `POST /api/financial/assets` creates an asset.
- `GET /api/financial/assets/summary` returns deterministic type and liquidity totals.
- `GET /api/financial/assets/{asset_id}` returns one owned asset.
- `PATCH /api/financial/assets/{asset_id}` updates an owned asset.
- `DELETE /api/financial/assets/{asset_id}` deletes an owned asset.
- `GET /api/financial/runway` calculates a preview without saving it.
- `POST /api/financial/runway` saves an immutable calculation snapshot.
- `GET /api/financial/runway/latest` returns the latest saved snapshot.
- `GET /api/financial/runway/history` returns snapshot history with `limit` and `offset`.
- `POST /api/financial/runway/preview` evaluates unsaved user-supplied expense scenarios.
- `GET /api/financial/runway/trend` compares the latest two saved snapshots.

Runway is `liquid assets / (monthly essential expenses + monthly debt payment)`.
Assets marked `requires_process` or `illiquid` remain in total assets but do not count
toward runway. All assets must match the profile currency; currency changes are rejected
while assets exist because this API does not perform foreign-exchange conversion.

## Evidence API

Verified users can manage human-authored career evidence:

- `GET /api/evidence` supports type, text, date, `limit`, and `offset` filters.
- `POST /api/evidence` creates evidence and always records it as human-authored.
- `GET`, `PATCH`, and `DELETE /api/evidence/{evidence_id}` operate on owned evidence.
- `POST /api/evidence/{evidence_id}/attachment` optionally attaches one private file.
- `DELETE /api/evidence/{evidence_id}/attachment` removes the attached file.
- `GET /api/evidence/stats` returns factual counts by evidence type.

Creating evidence does not require an attachment. Attachments accept PDF, PNG, JPG, or
WEBP content up to 10 MB and are stored in the configured private Supabase Storage bucket.
Evidence responses contain a signed attachment URL that expires after 15 minutes.

## Mission API

Verified users can create and track their own skill missions:

- `GET /api/missions` supports status, skill, due-date, overdue, and pagination filters.
- `POST /api/missions` creates a user-authored mission.
- `GET`, `PATCH`, and `DELETE /api/missions/{mission_id}` operate on owned missions.
- `GET /api/missions/progress` returns status, overdue, and completion totals.

Links to pivot skill gaps are ownership checked. Missions are never generated automatically.

## Account API

- `PATCH /api/auth/username` updates a verified user's unique username.
- `POST /api/auth/change-email` verifies the current password and sends confirmation to the new address.
- `POST /api/auth/verify-email` applies a confirmed email change and revokes existing JWTs.
- `DELETE /api/auth/account` requires the current password and permanently deletes the account.

## Dashboard API

`GET /api/dashboard` returns only stored facts and deterministic arithmetic: account and
profile identity, onboarding state, skill counts, evidence totals, mission progress, and
current financial runway. Missing sections are returned as empty or `null`; no AI scores,
generated recommendations, or placeholder analysis are included.
