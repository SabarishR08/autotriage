from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import analytics, health, logs
from app.core.config import get_settings
from app.core.database import run_migrations

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Validate required config — exits with clear error if misconfigured
    settings.validate()
    # 2. Run Alembic migrations to head (safe to run on every startup)
    run_migrations()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "Agentless API observability platform. Ingest error logs, correlate "
        "them against a GitHub repo, and generate root-cause analysis and "
        "deploy-ready fixes — no SDK, no sidecar, just a REST endpoint."
    ),
    version="0.2.0",
    lifespan=lifespan,
    # Keep OpenAPI docs available — they expose no secrets and are useful
    # for integration. Disable only if you need to lock down the schema.
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key"],
)

app.include_router(health.router)
app.include_router(logs.router)
app.include_router(analytics.router)
