from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import engine
from app.api.auth import router as auth_router
from app.api.onboarding import router as onboarding_router
from app.api.profile import router as profile_router
from app.api.master import router as master_router
from app.api.financial import router as financial_router
from app.api.evidence import router as evidence_router
from app.api.missions import router as missions_router
from app.api.dashboard import router as dashboard_router
from app.api.ai_assessments import router as ai_assessments_router
from app.api.layoff_simulations import router as layoff_simulations_router
from app.api.ai_insights import router as ai_insights_router
from app.api.market_baselines import router as market_baselines_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    yield
    await engine.dispose()


app = FastAPI(
    title="Jalur B API",
    description="Career & financial resilience platform",
    version="0.1.0",
    debug=settings.debug,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.cors_allow_all else settings.allowed_frontend_origins,
    allow_origin_regex=None if settings.cors_allow_all else settings.cors_origin_regex,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(onboarding_router)
app.include_router(profile_router)
app.include_router(master_router)
app.include_router(financial_router)
app.include_router(evidence_router)
app.include_router(missions_router)
app.include_router(dashboard_router)
app.include_router(ai_assessments_router)
app.include_router(layoff_simulations_router)
app.include_router(ai_insights_router)
app.include_router(market_baselines_router)


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
