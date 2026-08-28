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
