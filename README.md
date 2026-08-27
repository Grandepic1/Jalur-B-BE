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
